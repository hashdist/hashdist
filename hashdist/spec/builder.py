import copy
from pprint import pprint
from . import package
from . import utils
from . import hook
from . import hook_api
from ..formats.marked_yaml import load_yaml_from_file
from ..formats import marked_yaml
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
        self._packages = self.profile.resolve_parameters()

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

    def get_ready_list(self):
        return self.get_ready_dict().keys()

    def get_build_spec(self, pkgname):
        return self._build_specs[self._packages[pkgname]]

    def get_build_script(self, pkgname):
        python_path = self.profile.hook_import_dirs
        with hook.python_path_and_modules_sandbox(python_path):
            pkg = self._packages[pkgname]
            ctx = self._load_package_build_context(pkg)
            return package.assemble_build_script(pkg._impl.doc, ctx)

    def get_status_report(self):
        """
        Return ``{pkgname: (build_spec, is_built)}``.
        """
        report = dict((pkgname, (build_spec, pkgname in self._built))
                      for pkgname, build_spec in self._build_specs.iteritems())
        return report

    def get_profile_build_spec(self, link_type='relative', write_protect=True):
        profile_list = [{"id": build_spec.artifact_id} for build_spec in self._build_specs.values()]


        # Should topologically sort by run-time dependencies, uniquely
        # by package instance (so can't have name anywhere but must use
        # key arg to topological_sort), finally we just have to generate
        # package names because we could have two differently compiled
        # packages with the same name really....
        def get_run_deps(dep):
            return [dep for dep_name, dep in dep._param_values.items()
                    if dep is not None and dep_name.startswith('_run_')]
        sorted_packages = utils.topological_sort(self._packages.values(), get_run_deps, key=lambda p: p._spec.name)

        imports = []
        for i, dep in enumerate(sorted_packages):
            dep_name = 'PKG%d' % i
            imports.append({'ref': '%s' % to_env_var(dep_name),
                            'id': self._build_specs[dep].artifact_id})

        commands = []
        install_link_rules = []
        for i, pkg in enumerate(sorted_packages):
            pkgname = 'PKG%d' % i
            commands += pkg._impl.assemble_build_import_commands(pkgname)
            install_link_rules += pkg._impl.assemble_link_dsl(pkgname, '${ARTIFACT}', link_type)
        commands.extend([{"hit": ["create-links", "$in0"],
                          "inputs": [{"json": install_link_rules}]}])
        if write_protect:
            commands.extend([{"hit": ["build-postprocess", "--write-protect"]}])

        return BuildSpec({
            "name": "profile",
            "version": "n",
            "build": {
                "import": marked_yaml.raw_tree(imports),
                "commands": marked_yaml.raw_tree(commands),
                }
            })

    def build(self, pkgname, config, worker_count, keep_build='never', debug=False):
        pkg = self._packages[pkgname]
        pkg._impl.fetch_sources(self.source_cache)
        extra_env = {'HASHDIST_CPU_COUNT': str(worker_count)}
        self.build_store.ensure_present(self._build_specs[pkg], config, extra_env=extra_env,
                                        keep_build=keep_build, debug=debug)
        self._built.add(pkg)

    def build_profile(self, config, keep_build='never'):
        profile_build_spec = self.get_profile_build_spec()
        return self.build_store.ensure_present(profile_build_spec, config, keep_build=keep_build)

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
        for key, value in pkg._param_values.items():
            if isinstance(value, PackageInstance) and not key.startswith('_run_'):
                dep_vars.append(to_env_var(key))
        parameters = dict(pkg._param_values)

        ctx = hook_api.PackageBuildContext(pkg._spec.name, dep_vars, parameters)
        hook.load_hooks(ctx, hook_files)
        return ctx
