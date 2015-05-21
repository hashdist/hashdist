import copy
from pprint import pprint
from . import package
from . import utils
from . import hook
from . import hook_api
from ..formats.marked_yaml import load_yaml_from_file
from ..core import BuildSpec, ArtifactBuilder
from .utils import to_env_var
from .exceptions import PackageError, ProfileError
from .package import PackageInstance


class ProfileBuilder(object):
    """
    What can be known of a profile when all referenced package specs are loaded.
    Used to maintain state during the building process.
    """
    def __init__(self, logger, source_cache, build_store, profile):
        self.logger = logger
        self.source_cache = source_cache
        self.build_store = build_store
        self.profile = profile

        self._built = set()  # cache for build_store
        self._in_progress = set()
        self._build_specs = {} # { pkgname : BuildSpec }
        self._init()

    def _init(self):
        self._load_packages()
        self._compute_specs()

    def _load_packages(self):
        # Loads PacakageSpec from YAML, resolves parameters to pass, and turns PackageSpec
        # into PackageInstance (binding the spec with chosen parameter values). The result
        # is put in self._packages.

        self._packages = {}  # name : PackageInstance
        visiting = set()

        def visit(pkgname):
            assert isinstance(pkgname, basestring)
            pkgname = str(pkgname)
            if pkgname in visiting:
                raise ProfileError(pkgname, 'dependency cycle between packages, '
                                   'including package "%s"' % pkgname)
            if pkgname in self._packages:
                return self._packages[pkgname]
            # Get the declaration in profile. This does not always exist, in which case
            # an empty dict represents the defaults.
            param_doc = self.profile.packages.get(pkgname, {})
            if 'use' in param_doc:
                if len(param_doc) != 1:
                    raise ProfileError(param_doc, 'If "use:" is provided, no other parameters should be provided')
                pkgname = param_doc['use']
                return visit(pkgname)

            visiting.add(pkgname)

            pkg_spec = self.profile.load_package(pkgname)

            # Now we want to complete the information in param_doc.

            # Step 1: Fill in default fallback values and replace string package params
            # with values of type PackageInstance
            param_values = dict(param_doc)
            for param in pkg_spec.parameters.values():
                if param.has_package_type():
                    # Package parameters default to other packages of the same
                    # name as the parameter in the profile. At this point we recurse
                    # to make sure that package is resolved, and a PackageInstance
                    # is present instead of str in param_values.

                    # We will include the package if and only if include ends up True.
                    # If not, we set it to None, and also it is never visited.
                    # Note: If *another* package requires it, we don't include it,
                    # only if it's explicitly listed, for now. Will write tests after
                    # list has decided what we want.
                    dep_name = param.name
                    if dep_name.startswith('_run_'):
                        dep_name = dep_name[len('_run_'):]
                    include = False
                    if dep_name in param_values:
                        include = True
                    # OK, not explicitly given. Is it present in profile though?
                    elif dep_name in self.profile.packages:
                        include = True
                    else:
                        # We do a tiny special case of constraint
                        # solving here; if there is a constraint saying exactly that the
                        # package must be included, we auto-include it. This constraint
                        # is generated in package.parse_deps. Obviously this is in anticipation
                        # of a better constraints system.
                        include = '%s is not None' % param.name in pkg_spec.constraints
                    inc_pkg = visit(param_doc.get(dep_name, dep_name)) if include else None
                    param_values[param.name] = inc_pkg
                elif param.name not in param_values:
                    if param.name in self.profile.parameters:
                        # Inherit from global profile parameters
                        param_values[param.name] = self.profile.parameters[param.name]
                    else:
                        # Use default value. If it is a required parameter, then default will
                        # be None and there will be a constraint that it is not None that will
                        # fail later.
                        param_values[param.name] = param.default

            # Step 2: Type-check and remove parameters that are not declared
            # (also according to when-conditions)
            param_values = pkg_spec.typecheck_parameter_set(param_values, node=param_doc)
            self._packages[pkgname] = result = pkg_spec.instantiate(param_values)
            visiting.remove(pkgname)
            return result

        for pkgname, args in self.profile.packages.items():
            visit(pkgname)


    def _compute_specs(self):
        """
        Do a depth first walk to compute build specs/artifact IDs/upload build scripts for
        each package, in order required (artifact ID of dependencies needed to compute
        build spec of dependants).

        We know at this point that there's no cycles.
        """
        python_path = self.profile.hook_import_dirs

        def process(pkg):
            with hook.python_path_and_modules_sandbox(python_path):
                ctx = self._load_package_build_context(pkg)
                self._build_specs[pkg] = pkg._impl.assemble_build_spec(
                    self.source_cache,
                    ctx,
                    lambda dep: self._build_specs[dep].artifact_id,
                    self.profile)
            # check whether package is already built, and update self._built
            if self.build_store.is_present(self._build_specs[pkg]):
                self._built.add(pkg)

        def traverse_depth_first(pkg):
            if pkg not in self._build_specs:
                for dep in pkg._impl.build_deps.values():
                    traverse_depth_first(dep)
                process(pkg)

        for pkg in self._packages.values():
            traverse_depth_first(pkg)

    def get_ready_dict(self):
        ready = {}
        for pkgname, pkg in self._packages.items():
            if pkg in self._built:
                continue
            if all(dep in self._built for dep in pkg._impl.build_deps.values()):
                ready[pkgname] = pkg
        return ready

    def get_build_spec(self, pkgname):
        return self._build_specs[pkgname]

    def get_build_script(self, pkgname):
        python_path = self.profile.hook_import_dirs
        with hook.python_path_and_modules_sandbox(python_path):
            ctx = self._load_package_build_context(pkgname, self._packages[pkgname])
            return self._packages[pkgname].assemble_build_script(ctx)

    def get_status_report(self):
        """
        Return ``{pkgname: (build_spec, is_built)}``.
        """
        report = dict((pkgname, (build_spec, pkgname in self._built))
                      for pkgname, build_spec in self._build_specs.iteritems())
        return report

    def get_profile_build_spec(self, link_type='relative', write_protect=True):
        profile_list = [{"id": build_spec.artifact_id} for build_spec in self._build_specs.values()]

        # Topologically sort by run-time dependencies
        def get_run_deps(pkgname):
            return self._packages[pkgname].doc.get('dependencies', {}).get('run', [])
        sorted_packages = utils.topological_sort(self._packages.keys(), get_run_deps)

        imports = []
        for pkgname in sorted_packages:
            imports.append({'ref': '%s' % to_env_var(pkgname),
                            'id': self._build_specs[pkgname].artifact_id})

        commands = []
        install_link_rules = []
        for pkgname in sorted_packages:
            pkg = self._packages[pkgname]
            commands += pkg.assemble_build_import_commands()
            install_link_rules += pkg.assemble_link_dsl('${ARTIFACT}', link_type)
        commands.extend([{"hit": ["create-links", "$in0"],
                          "inputs": [{"json": install_link_rules}]}])
        if write_protect:
            commands.extend([{"hit": ["build-postprocess", "--write-protect"]}])

        return BuildSpec({
            "name": "profile",
            "version": "n",
            "build": {
                "import": imports,
                "commands": commands,
                }
            })

    def build(self, pkgname, config, worker_count, keep_build='never', debug=False):
        pkg = self._packages[pkgname]
        pkg._impl.fetch_sources(self.source_cache)
        extra_env = {'HASHDIST_CPU_COUNT': str(worker_count)}
        self.build_store.ensure_present(self._build_specs[pkg], config, extra_env=extra_env,
                                        keep_build=keep_build, debug=debug)
        self._built.add(pkgname)

    def build_profile(self, config):
        profile_build_spec = self.get_profile_build_spec()
        return self.build_store.ensure_present(profile_build_spec, config)

    def build_profile_out(self, target, config, link_type, debug=False):
        """
        Build a profile intended for use/modification outside of the BuildStore
        """
        profile_build_spec = self.get_profile_build_spec(link_type, write_protect=False)
        extra_env = {}
        virtuals = {}
        builder = ArtifactBuilder(self.build_store, profile_build_spec, extra_env, virtuals, debug)
        builder.build_out(target, config)

    def _load_package_build_context(self, pkg):
        hook_files = [self.profile.resolve(fname) for fname in pkg._impl.hook_files]

        dep_vars = []
        parameters = {}
        for key, value in pkg._param_values.items():
            if isinstance(value, PackageInstance):
                if not key.startswith('_run_'):
                    dep_vars.append(to_env_var(key))
            else:
                parameters[key] = value

        ctx = hook_api.PackageBuildContext(pkg._spec.name, dep_vars, parameters)
        hook.load_hooks(ctx, hook_files)
        return ctx
