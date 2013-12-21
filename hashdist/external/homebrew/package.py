from ...spec.package import PackageSpec
from ...spec.package import create_build_spec
import os

class HomebrewPackage(PackageSpec):
    """
    Wraps a hashdist-local homebrew command to provide homebrew builds as
    hashdist packages
    """
    def __init__(self, name, doc, store_path):
        self.name = name
        self.doc = doc
        self.hook_files = []
        deps = doc.get('dependencies', {})
        self.build_deps = deps.get('build', [])
        self.run_deps = deps.get('run', [])
        self.store_path = store_path

        if not isinstance(self.build_deps, list) or not isinstance(self.run_deps, list):
            raise TypeError('dependencies must be a list')


    def assemble_build_spec(self, source_cache, ctx, dependency_id_map, dependency_packages, profile):
        """
        Returns the build.json for building the package. Also, the build script (Bash script)
        that should be run to build the package is uploaded to the given source cache.
        """
        commands = [{"set": "HOME", "nohash_value": os.path.expanduser('~')}]

        for dep_name in self.build_deps:
            dep_pkg = dependency_packages[dep_name]
            commands += dep_pkg.assemble_build_import_commands(ctx.parameters, ref=to_env_var(dep_name))
        build_script = self.assemble_build_script(ctx)

        files = {'_hashdist/build.sh': build_script}
        build_script_key = source_cache.put(files)
        build_spec = create_build_spec(self.name, self.doc, ctx.parameters, dependency_id_map,
                                       commands, [{'target': '.', 'key': build_script_key}])
        return build_spec


    def assemble_link_dsl(self, parameters, ref, target, link_type='relative'):
        """
        Creates the input document to ``hit create-links`` from the information in a package
        description.
        """

        rules = [{"action": "homebrew_link",
                  "store": self.store_path,
                  "keg": to_homebrew_keg(ref),
                  "target": target}]
        return rules


def to_homebrew_keg(ref):
    return ref.lower()