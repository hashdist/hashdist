import sys

from .. import core

class BaseSourceFetch(object):
    def __init__(self, key, target, strip=0):
        self.key = key
        self.target = target
        self.strip = strip
        
    def get_spec(self):
        return {'key': self.key,
                'target': self.target,
                'strip': self.strip}

class FetchSourceCode(BaseSourceFetch):
    def __init__(self, url, key, target='.', strip=0):
        BaseSourceFetch.__init__(self, key, target, strip)
        self.url = url

    def fetch_into(self, source_cache):
        source_cache.fetch_archive(self.url, self.key)
                        
class PutScript(BaseSourceFetch):
    def __init__(self, files, target='.'):
        key = hdist_pack(files)
        BaseSourceFetch.__init__(self, key, target)
        self.files = files

    def fetch_into(self, source_cache):
        source_cache.put(self.files)


class Recipe(object):

    """

    Each recipe can be constructable/pickleable without any actions taken
    or the build spec assembled; i.e., a recipe object should be lazy.
    
    Parameters
    ----------

    
    """

    
    def __init__(self, name, version, source_fetches=(), dependencies=None,
                 env=None, is_virtual=False, **kw):
        self.name = name
        self.version = version
        self.source_fetches = source_fetches
        self.is_virtual = is_virtual

        dependencies = dict(dependencies) if dependencies is not None else {}
        env = dict(env) if env is not None else {}

        # parse kw to mean dependency if Recipe, or env entry otherwise
        for key, value in kw.iteritems():
            if isinstance(value, (Recipe, Virtual)):
                dependencies[key] = value
            elif isinstance(value, (str, int, float)):
                env[key] = value
            else:
                raise TypeError('Meaning of passing argument %s of type %r not understood' %
                                (key, type(value)))


        self.dependencies = dependencies
        self.env = env
        self._build_spec = None

    def get_build_spec(self):
        """
        Returns
        -------

        build_spec : BuildSpec
        
        """
        # the build spec is cached; this is important when fetching dependency
        # artifact IDs
        if self._build_spec is not None:
            return self._build_spec
        else:
            return self._assemble_build_spec()

    def _assemble_build_spec(self):
        sources = []
        for fetch in self.source_fetches:
            sources.append(fetch.get_spec())

        dep_specs = []
        for dep_name, dep in self.dependencies.iteritems():
            dep_id = dep.get_artifact_id()
            dep_specs.append({"ref": dep_name, "id": dep_id})
        dep_specs.sort(key=lambda spec: spec['ref'])

        commands = self.get_commands()
        files = self.get_files()
        parameters = self.get_parameters()
        env = self.get_env()
        
        doc = dict(name=self.name, version=self.version, sources=sources, env=env,
                   commands=commands, files=files, dependencies=dep_specs,
                   parameters=parameters)
        return core.BuildSpec(doc)

    def get_artifact_id(self):
        if self.is_virtual:
            return 'virtual:%s' % self.name
        else:
            return self.get_build_spec().artifact_id

    def fetch_sources(self, source_cache):
        for fetch in self.source_fetches:
            fetch.fetch_into(source_cache)

    def format_tree(self, build_store=None):
        lines = []
        self._format_tree(lines, {}, 0, build_store)
        return '\n'.join(lines)

    def _format_tree(self, lines, visited, level, build_store):
        indent = '  ' * level
        build_spec = self.get_build_spec()
        artifact_id = build_spec.artifact_id
        short_artifact_id = core.shorten_artifact_id(artifact_id, 6) + '..'

        if build_store is None:
            status = ''
        else:
            status = ' [OK]' if build_store.is_present(build_spec) else ' [NEEDS BUILD]'
        
        if artifact_id in visited:
            display_name = visited[artifact_id]
            desc = '%s%s (see above)' % (indent, display_name)
        elif self.is_virtual:
            display_name = self.get_artifact_id()
            desc = '%s%s (=%s)' % (indent, display_name, short_artifact_id)
        else:
            display_name = short_artifact_id
            desc = '%s%s' % (indent, display_name)
        lines.append('%-70s%s' % (desc, status))
        visited[artifact_id] = display_name
        for dep in self.dependencies.values():
            dep._format_tree(lines, visited, level + 1, build_store)

    def __repr__(self):
        return '<Recipe for %s>' % self.get_artifact_id()

    # Subclasses should override the following
    
    def get_commands(self):
        return []

    def get_files(self):
        return []

    def get_parameters(self):
        return {}

    def get_env(self):
        return {}


class Virtual(object):
    def __init__(self, virtual_name, wrapped_recipe):
        self.virtual_name = 'virtual:' + virtual_name
        self.wrapped_recipe = wrapped_recipe

    def get_artifact_id(self):
        return self.virtual_name

    def __repr__(self):
        return '<%s -> %s>' % (self.virtual_name, self.wrapped_recipe.get_artifact_id())

class HdistTool(Recipe):
    def __init__(self):
        Recipe.__init__(self, core.HDIST_CLI_ARTIFACT_NAME, core.HDIST_CLI_ARTIFACT_VERSION,
                        is_virtual=True)

    def _assemble_build_spec(self):
        return core.hdist_cli_build_spec()

hdist_tool = HdistTool()


def build_recipes(build_store, source_cache, recipes, **kw):
    built = set() # artifact_id
    virtuals = {} # virtual_name -> artifact_id

    def _depth_first_build(recipe):
        for dep_pkg in recipe.dependencies.values():
            # recurse
            _depth_first_build(dep_pkg)

        recipe.fetch_sources(source_cache)

        build_spec = recipe.get_build_spec()
        if not build_spec.artifact_id in built:
            # todo: move to in-memory cache in BuildStore
            build_store.ensure_present(build_spec, source_cache, virtuals=virtuals,
                                       **kw)
            built.add(build_spec.artifact_id)

        if recipe.is_virtual:
            virtuals[recipe.get_artifact_id()] = build_spec.artifact_id

    
    for recipe in recipes:
        _depth_first_build(recipe)    
    
