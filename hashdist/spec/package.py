import sys
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
    def __init__(self, name, doc, hook_files, parameters):
        self.name = name
        self.doc = doc
        self.hook_files = hook_files
        deps = doc.get('dependencies', {})
        self.build_deps = deps.get('build', [])
        self.run_deps = deps.get('run', [])
        self.parameters = parameters
        if not isinstance(self.build_deps, list) or not isinstance(self.run_deps, list):
            raise TypeError('dependencies must be a list')

    @staticmethod
    def load(profile, name):
        """
        Loads a single package from a profile.

        Includes ancestors, which are merged in as appropriate. This
        involves a transform pipeline to put the spec on a simple
        format where all information in ancestors is inlined, and
        stages are ordered.

        Parameters
        ----------

        profile : :class:`~hashdist.spec.profile.Profile`
            The profile, which defines parameters to be used.

        name : str
            The package name. This may be different from the name of
            the yaml file if you override ``pkg_name: {use:
            alternate_name}`` in the profile.
        """
        package_parameters = defaultdict(str, profile.parameters)
        package_parameters.update(profile.packages.get(name, {}))
        package_parameters['package'] = name
        from package_loader import PackageLoader
        loader = PackageLoader(name, package_parameters,
                               load_yaml=profile.load_package_yaml)
        return PackageSpec(name, loader.stages_topo_ordered(),
                           loader.get_hook_files(), loader.parameters)

    def fetch_sources(self, source_cache):
        for source_clause in self.doc.get('sources', []):
            source_cache.fetch(source_clause['url'], source_clause['key'], self.name)

    def assemble_build_script(self, ctx):
        """
        Return the build script.

        As a side effect, all referenced files are stored in the build
        context.

        Returns:
        --------

        String. A bash script that should be run to build the package.
        """
        lines = ['set -e', 'export HDIST_IN_BUILD=yes']
        for stage in self.doc['build_stages']:
            lines += ctx.dispatch_build_stage(stage)
        return '\n'.join(lines) + '\n'

    def assemble_build_spec(self, source_cache, ctx, dependency_id_map, dependency_packages, profile):
        """
        Return the ``build.json`` buildspec.

        As a side effect, the build script (see
        :meth:`assemble_build_script`) that should be run to build the
        package is uploaded to the given source cache.

        Arguments:
        ----------

        source_cache : :class:`hashdist.core.source_cache.SourceCache`
            The source cache where the build script is to be stored.

        ctx : :class:`hashdist.spec.hook_api.PackageBuildContext`
            Part of the hook api

        Returns:
        --------

        The ``build.json`` for building the package.
        """
        assert ctx.parameters == self.parameters  # TODO: why duplicate the parameters?

        if isinstance(dependency_id_map, dict):
            dependency_id_map = dependency_id_map.__getitem__
        imports = []
        build_deps = self.doc.get('dependencies', {}).get('build', [])
        for dep_name in build_deps:
            imports.append({'ref': '%s' % to_env_var(dep_name), 'id': dependency_id_map(dep_name)})

        dependency_commands = []
        for dep_name in self.build_deps:
            dep_pkg = dependency_packages[dep_name]
            dependency_commands += dep_pkg.assemble_build_import_commands()

        build_script_key = self._store_files(source_cache, ctx, profile)
        build_spec = self._create_build_spec(imports,
            dependency_commands, self._postprocess_commands(),
            [{'target': '.', 'key': build_script_key}])
        return build_spec

    def _store_files(self, source_cache, ctx, profile):
        """
        Store all referenced files in the source cache

         Arguments:
        ----------

        source_cache : :class:`hashdist.core.source_cache.SourceCache`
            The source cache where the build script and files are stored.

        ctx : :class:`hashdist.spec.hook_api.PackageBuildContext`
            Part of the hook api

        profile : :class:`hashdist.spec.profile.Profile`
            The profile, which knows how to find files that are
            referenced in the package.

        Returns:
        --------

        The key associated to the files in the source cache.
        """
        build_script = self.assemble_build_script(ctx)
        files = {}
        for to_name, from_name in ctx._bundled_files.iteritems():
            p = profile.find_package_file(self.name, from_name)
            if p is None:
                raise ProfileError(from_name, 'file "%s" not found' % from_name)
            with open(profile.resolve(p)) as f:
                files['_hashdist/' + to_name] = f.read()
        files['_hashdist/build.sh'] = build_script
        return source_cache.put(files)

    def assemble_link_dsl(self, target, link_type='relative'):
        """
        Creates the input document to ``hit create-links`` from the information in a package
        description.
        """
        link_action_map = {'relative':'relative_symlink',
                           'absolute':'absolute_symlink',
                           'copy':'copy'}

        ref = to_env_var(self.name)
        rules = []
        for in_stage in self.doc['profile_links']:
            if 'link' in in_stage:
                select = substitute_profile_parameters(in_stage["link"], self.parameters)
                rules.append({
                    "action": link_action_map[link_type],
                    "select": "${%s_DIR}/%s" % (ref, select),
                    "prefix": "${%s_DIR}" % ref,
                    "target": target,
                    "dirs": in_stage.get("dirs", False)})
            elif 'exclude' in in_stage:
                select = substitute_profile_parameters(in_stage["exclude"], self.parameters)
                rules.append({"action": "exclude",
                              "select": select})
            elif 'launcher' in in_stage:
                select = substitute_profile_parameters(in_stage["launcher"], self.parameters)
                if link_type != 'copy':
                    rules.append({"action": "launcher",
                                  "select": "${%s_DIR}/%s" % (ref, select),
                                  "prefix": "${%s_DIR}" % ref,
                                  "target": target})
            elif 'copy' in in_stage:
                select = substitute_profile_parameters(in_stage["copy"], self.parameters)
                rules.append({"action": "copy",
                    "select": "${%s_DIR}/%s" % (ref, select),
                    "prefix": "${%s_DIR}" % ref,
                    "target": target,
                    "dirs": in_stage.get("dirs", False)})
            else:
                raise ValueError('Need either "copy", "link", "launcher" or "exclude" '
                                 'key in profile_links entries')
        return rules

    def assemble_build_import_commands(self):
        """
        Return the ``when_build_dependency`` commands from dependencies.
        """
        cmds = [self._process_when_build_dependency(env_action)
                for env_action in self.doc.get('when_build_dependency', [])]
        return cmds

    def _process_when_build_dependency(self, action):
        action = dict(action)
        if not ('prepend_path' in action or 'append_path' in action or 'set' in action):
            raise ValueError('when_build_dependency action must be one of '
                             'prepend_path, append_path, set')
        value = substitute_profile_parameters(action['value'], self.parameters)
        value = value.replace('${ARTIFACT}', '${%s_DIR}' % to_env_var(self.name))
        if '$' in value.replace('${', ''):
            # a bit crude, but works for now -- should properly disallow non-${}-variables,
            # in order to prevent $ARTIFACT from cropping up
            raise ProfileError(action['value'].start_mark, 'Please use "${VAR}", not $VAR')
        action['value'] = value
        return action

    def _create_build_spec(self, imports,
                          dependency_commands, postprocess_commands,
                           extra_sources=()):
        parameters = self.parameters
        if 'BASH' not in parameters:
            raise ProfileError(self.doc, 'BASH must be provided in profile parameters')

        # sources
        sources = list(extra_sources)
        for source_clause in self.doc.get("sources", []):
            target = source_clause.get("target", ".")
            sources.append({"target": target, "key": source_clause["key"]})

        # build commands
        commands = list(dependency_commands)
        commands.append({"set": "BASH", "nohash_value": parameters['BASH']})
        if 'PATH' in parameters:
            commands.insert(0, {"set": "PATH", "nohash_value": parameters['PATH']})
        commands.append({"cmd": ["$BASH", "_hashdist/build.sh"]})
        commands.extend(postprocess_commands)

        # assemble
        build_spec = {
            "name": self.name,
            "build": {
                "import": imports,
                "commands": commands,
                },
            "sources": sources,
            }
        return core.BuildSpec(build_spec)

    def _postprocess_commands(self):
        hit_args = []
        for stage in self.doc.get('post_process', []):
            for arg in stage.get('hit', []):
                hit_args.append('--' + arg)
        if len(hit_args) == 0:
            return []
        return [{'hit': ['build-postprocess'] + hit_args}]
