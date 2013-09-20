from pprint import pprint
from . import package
from . import utils
from . import hook
from .marked_yaml import marked_yaml_load
from ..core import BuildSpec

class IllegalProfileError(Exception):
    pass


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
        self._ancestor_docs = {}

        self._load_packages()
        self._compute_specs()
        

    def _load_packages(self):
        package_includes = self.profile.get_packages()
        self._package_specs = {}
        for pkgname, settings in package_includes.iteritems():
            filename = self.profile.find_package_file(pkgname)
            if filename is None:
                raise IllegalProfileError('no spec found for package %s' % pkgname)
            with open(filename) as f:
                doc = marked_yaml_load(f)
                if doc is None:
                    doc = {}
            for ancestor in doc.get('extends', []):
                self._load_ancestor_doc(ancestor)
            self._package_specs[pkgname] = package.PackageSpec(pkgname, doc, self._ancestor_docs)

    def _load_ancestor_doc(self, pkgname):
        if pkgname not in self._ancestor_docs:
            filename = self.profile.find_base_file(pkgname + '.yaml')
            with open(filename) as f:
                doc = marked_yaml_load(f)
            self._ancestor_docs[pkgname] = doc

    def _compute_specs(self):
        """
        Do a depth first walk to compute build specs/artifact IDs/upload build scripts for
        each package, in order required.
        """
        def df(pkgname):
            if pkgname not in self._build_specs:
                # depth-first traversal logic
                if pkgname in visiting:
                    raise IllegalProfileError('dependency cycle between packages')
                visiting.add(pkgname)
                pkgspec = self._package_specs[pkgname]
                for depname in pkgspec.build_deps:
                    df(depname)
                visiting.remove(pkgname)
                # generate build.json
                self._build_specs[pkgname] = pkgspec.assemble_build_spec(
                    self.source_cache,
                    self.profile.parameters,
                    lambda dep_name: self._build_specs[dep_name].artifact_id,
                    self._package_specs)
                # check whether package is already built, and update self._built
                if self.build_store.is_present(self._build_specs[pkgname]):
                    self._built.add(pkgname)

        visiting = set()
        for pkgname in self._package_specs:
            df(pkgname)

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
        return self._package_specs[pkgname].assemble_build_script(self.profile.parameters)

    def get_status_report(self):
        """
        Return {pkgname: (artifact_id, is_built)}.
        """
        report = dict((pkgname, (build_spec.artifact_id, pkgname in self._built))
                      for pkgname, build_spec in self._build_specs.iteritems())
        return report

    def build(self, pkgname, config):
        self._package_specs[pkgname].fetch_sources(self.source_cache)
        self.build_store.ensure_present(self._build_specs[pkgname], config)
        self._built.add(pkgname)

    def build_profile(self, config):
        profile_list = [{"id": build_spec.artifact_id} for build_spec in self._build_specs.values()]

        # Topologically sort by run-time dependencies
        def get_run_deps(pkgname):
            return self._package_specs[pkgname].doc.get('dependencies', {}).get('run', [])
        sorted_packages = utils.topological_sort(self._package_specs.keys(), get_run_deps)

        imports = []
        for pkgname in sorted_packages:
            imports.append({'ref': '%s' % pkgname.upper(), 'id': self._build_specs[pkgname].artifact_id})

        commands = []
        install_link_rules = []
        for pkgname in sorted_packages:
            pkg = self._package_specs[pkgname]
            ref = '%s_DIR' % pkgname.upper()
            commands += pkg.assemble_build_import_commands(self.profile.parameters, ref)
            install_link_rules += pkg.assemble_link_dsl(self.profile.parameters, ref, '${ARTIFACT}')
        commands.extend([{"hit": ["create-links", "$in0"],
                          "inputs": [{"json": install_link_rules}]},
                         {"hit": ["build-postprocess", "--write-protect"]}])

        profile_build_spec = BuildSpec({
            "name": "profile",
            "version": "n",
            "build": {
                "import": imports,
                "commands": commands,
                }
            })
        return self.build_store.ensure_present(profile_build_spec, config)
        
    def _load_hooks(self, pkgname):
        hook_files = []
        for ancestor in self._package_specs[pkgname].extends:
            py = self.profile.find_base_file(ancestor + '.py')
            if py:
                hook_files.append(py)
        py = self.profile.find_package_file(pkgname, '.py')
        if py:
            hook_files.append(py)
        return hook.load_hooks(hook_files, self.profile.get_python_path())
