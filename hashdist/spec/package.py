from collections import defaultdict

from .utils import substitute_profile_parameters, to_env_var
from .. import core
from .exceptions import ProfileError


class PackageSpec(object):
    """
    Wraps a package spec document to provide some facilities (act on it/understand it).

    The document provided to the constructor should be a complete stand-alone
    specification. The `load` staticmethod is available to load a package spec
    from a profile, this includes pre-preprocessing to assemble together the
    package spec with its ancestor specifications (given in the `extends` clause).
    """
    def __init__(self, name, doc, hook_files):
        self.name = name
        self.doc = doc
        self.hook_files = hook_files
        deps = doc.get('dependencies', {})
        self.build_deps = deps.get('build', [])
        self.run_deps = deps.get('run', [])
        if not isinstance(self.build_deps, list) or not isinstance(self.run_deps, list):
            raise TypeError('dependencies must be a list')

    @staticmethod
    def load(profile, name):
        """
        Loads a single package from a profile, including ancestors. This involves
        a transform pipeline to put the spec on a simple format where all information
        in ancestors is inlined, and stages are ordered.
        """
        package_parameters = defaultdict(str, profile.parameters)
        package_parameters.update(profile.packages.get(name, {}))
        from package_loader import PackageLoader
        loader = PackageLoader(name, package_parameters,
                               load_yaml=profile.load_package_yaml,
                               find_file=profile.find_package_file)
        return PackageSpec(name, loader.stages_topo_ordered(), loader.get_hook_files())

    def fetch_sources(self, source_cache):
        for source_clause in self.doc.get('sources', []):
            source_cache.fetch(source_clause['url'], source_clause['key'], self.name)

    def assemble_build_script(self, ctx):
        """
        Return build script (Bash script) that should be run to build package.
        """
        lines = ['set -e', 'export HDIST_IN_BUILD=yes']
        for stage in self.doc['build_stages']:
            lines += ctx.dispatch_build_stage(stage)
        return '\n'.join(lines) + '\n'

    def assemble_build_spec(self, source_cache, ctx, dependency_id_map, dependency_packages, profile):
        """
        Returns the build.json for building the package. Also, the build script (Bash script)
        that should be run to build the package is uploaded to the given source cache.
        """
        commands = []
        for dep_name in self.build_deps:
            dep_pkg = dependency_packages[dep_name]
            commands += dep_pkg.assemble_build_import_commands(ctx.parameters, ref=to_env_var(dep_name))
        build_script = self.assemble_build_script(ctx)

        files = {}
        for to_name, from_name in ctx._bundled_files.iteritems():
            p = profile.find_package_file(self.name, from_name)
            if p is None:
                raise ProfileError(from_name, 'file "%s" not found' % from_name)
            with open(profile.resolve(p)) as f:
                files['_hashdist/' + to_name] = f.read()
        files['_hashdist/build.sh'] = build_script
        build_script_key = source_cache.put(files)
        build_spec = create_build_spec(self.name, self.doc, ctx.parameters, dependency_id_map,
                                       commands, [{'target': '.', 'key': build_script_key}])
        return build_spec

    def assemble_link_dsl(self, parameters, ref, target, link_type='relative'):
        """
        Creates the input document to ``hit create-links`` from the information in a package
        description.
        """

        link_action_map = {'relative':'relative_symlink',
                           'absolute':'absolute_symlink',
                           'copy':'copy'}

        rules = []
        for in_stage in self.doc['profile_links']:
            if 'link' in in_stage:
                select = substitute_profile_parameters(in_stage["link"], parameters)
                rules.append({
                    "action": link_action_map[link_type],
                    "select": "${%s_DIR}/%s" % (ref, select),
                    "prefix": "${%s_DIR}" % ref,
                    "target": target,
                    "dirs": in_stage.get("dirs", False)})
            elif 'exclude' in in_stage:
                select = substitute_profile_parameters(in_stage["exclude"], parameters)
                rules.append({"action": "exclude",
                              "select": select})
            elif 'launcher' in in_stage:
                select = substitute_profile_parameters(in_stage["launcher"], parameters)
                if link_type != 'copy':
                    rules.append({"action": "launcher",
                                  "select": "${%s_DIR}/%s" % (ref, select),
                                  "prefix": "${%s_DIR}" % ref,
                                  "target": target})
            elif 'copy' in in_stage:
                select = substitute_profile_parameters(in_stage["copy"], parameters)
                rules.append({"action": "copy",
                    "select": "${%s_DIR}/%s" % (ref, select),
                    "prefix": "${%s_DIR}" % ref,
                    "target": target,
                    "dirs": in_stage.get("dirs", False)})

            else:
                raise ValueError('Need either "copy", "link", "launcher" or "exclude" key in profile_links entries')
        return rules

    def assemble_build_import_commands(self, parameters, ref):
        cmds = [_process_when_build_dependency(env_action, parameters, ref)
                for env_action in self.doc.get('when_build_dependency', [])]
        return cmds


def create_build_spec(pkg_name, pkg_doc, parameters, dependency_id_map,
                      dependency_commands, extra_sources=()):
    if isinstance(dependency_id_map, dict):
        dependency_id_map = dependency_id_map.__getitem__

    if 'BASH' not in parameters:
        raise ValueError('BASH must be provided in profile parameters')

    # dependencies
    imports = []
    build_deps = pkg_doc.get('dependencies', {}).get('build', [])
    for dep_name in build_deps:
        imports.append({'ref': '%s' % to_env_var(dep_name), 'id': dependency_id_map(dep_name)})

    # sources
    sources = list(extra_sources)
    for source_clause in pkg_doc.get("sources", []):
        target = source_clause.get("target", ".")
        sources.append({"target": target, "key": source_clause["key"]})

    # build commands
    commands = list(dependency_commands)
    commands.append({"set": "BASH", "nohash_value": parameters['BASH']})
    if 'PATH' in parameters:
        commands.insert(0, {"set": "PATH", "nohash_value": parameters['PATH']})
    commands.append({"cmd": ["$BASH", "_hashdist/build.sh"]})
    commands.append({"hit": ["build-postprocess", "--shebang=multiline", "--write-protect"]})
    # assemble
    build_spec = {
        "name": pkg_name,
        "build": {
            "import": imports,
            "commands": commands,
            },
        "sources": sources,
        }

    return core.BuildSpec(build_spec)


def _process_when_build_dependency(action, parameters, ref):
    action = dict(action)
    if not ('prepend_path' in action or 'append_path' in action or 'set' in action):
        raise ValueError('when_build_dependency action must be one of prepend_path, append_path, set')
    value = substitute_profile_parameters(action['value'], parameters)
    value = value.replace('${ARTIFACT}', '${%s_DIR}' % ref)
    if '$' in value.replace('${', ''):
        # a bit crude, but works for now -- should properly disallow non-${}-variables,
        # in order to prevent $ARTIFACT from cropping up
        raise ProfileError(action['value'].start_mark, 'Please use "${VAR}", not $VAR')
    action['value'] = value
    return action
