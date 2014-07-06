from pprint import pprint
from . import package
from . import utils
from . import hook
from . import hook_api
from ..formats.marked_yaml import load_yaml_from_file
from ..core import BuildSpec, ArtifactBuilder
from .utils import to_env_var
from .exceptions import PackageError, ProfileError


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

        self._load_packages()
        self._compute_specs()


    def _load_packages(self):
        self._package_specs = {}
        visiting = set()

        def visit(pkgname):
            if pkgname not in self._package_specs:
                if pkgname in visiting:
                    raise ProfileError(pkgname, 'dependency cycle between packages, '
                                       'including package "%s"' % pkgname)
                visiting.add(pkgname)
                spec = package.PackageSpec.load(self.profile, pkgname)
                self._package_specs[pkgname] = spec
                for dep in spec.build_deps + spec.run_deps:
                    visit(dep)
                visiting.remove(pkgname)

        for pkgname in self.profile.packages.keys():
            visit(pkgname)


    def _compute_specs(self):
        """
        Do a depth first walk to compute build specs/artifact IDs/upload build scripts for
        each package, in order required (artifact ID of dependencies needed to compute
        build spec of dependants).

        We know at this point that there's no cycles.
        """
        python_path = self.profile.hook_import_dirs

        def process(pkgname, pkgspec):
            with hook.python_path_and_modules_sandbox(python_path):
                ctx = self._load_package_build_context(pkgname, pkgspec)
                self._build_specs[pkgname] = pkgspec.assemble_build_spec(
                    self.source_cache,
                    ctx,
                    lambda dep_name: self._build_specs[dep_name].artifact_id,
                    self._package_specs,
                    self.profile)
            # check whether package is already built, and update self._built
            if self.build_store.is_present(self._build_specs[pkgname]):
                self._built.add(pkgname)

        def traverse_depth_first(pkgname):
            if pkgname not in self._build_specs:
                try:
                    pkgspec = self._package_specs[pkgname]
                except:
                    raise ProfileError(pkgname.start_mark, 'Package not found: %s' % pkgname)
                for depname in pkgspec.build_deps:
                    traverse_depth_first(depname)
                process(pkgname, pkgspec)

        for pkgname in self._package_specs:
            traverse_depth_first(pkgname)

    def get_ready_list(self):
        ready = []
        for name, pkg in self._package_specs.iteritems():
            if name in self._built:
                continue
            if all(dep_name in self._built for dep_name in pkg.build_deps):
                ready.append(name)
        return ready

    def get_build_spec(self, pkgname):
        return self._build_specs[pkgname]

    def get_build_script(self, pkgname):
        python_path = self.profile.hook_import_dirs
        with hook.python_path_and_modules_sandbox(python_path):
            ctx = self._load_package_build_context(pkgname, self._package_specs[pkgname])
            return self._package_specs[pkgname].assemble_build_script(ctx)

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
            return self._package_specs[pkgname].doc.get('dependencies', {}).get('run', [])
        sorted_packages = utils.topological_sort(self._package_specs.keys(), get_run_deps)

        imports = []
        for pkgname in sorted_packages:
            imports.append({'ref': '%s' % to_env_var(pkgname),
                            'id': self._build_specs[pkgname].artifact_id})

        commands = []
        install_link_rules = []
        for pkgname in sorted_packages:
            pkg = self._package_specs[pkgname]
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
        self._package_specs[pkgname].fetch_sources(self.source_cache)
        extra_env = {'HASHDIST_CPU_COUNT': str(worker_count)}
        self.build_store.ensure_present(self._build_specs[pkgname], config, extra_env=extra_env,
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

    def _load_package_build_context(self, pkgname, pkgspec):
        hook_files = [self.profile.resolve(fname) for fname in pkgspec.hook_files]
        dep_vars = [to_env_var(x) for x in self._package_specs[pkgname].build_deps]
        ctx = hook_api.PackageBuildContext(pkgname, dep_vars, pkgspec.parameters)
        hook.load_hooks(ctx, hook_files)
        return ctx
