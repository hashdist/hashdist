import sys

from .. import core
from ..hdist_logging import colorize

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
        source_cache.fetch(self.url, self.key)
                        
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
    
    """

    
    def __init__(self, name, version, source_fetches=(), dependencies=None,
                 env=None, is_virtual=False, in_profile=True, **kw):
        self.name = name
        self.version = version
        self.source_fetches = source_fetches
        self.is_virtual = is_virtual
        if is_virtual:
            in_profile = False
        self.in_profile = in_profile

        dependencies = dict(dependencies) if dependencies is not None else {}
        env = dict(env) if env is not None else {}

        # parse kw to mean dependency if Recipe, or env entry otherwise
        for key, value in kw.iteritems():
            if isinstance(value, Recipe):
                dependencies[key] = value
            elif isinstance(value, (str, int, float)):
                env[key] = value
            else:
                raise TypeError('Meaning of passing argument %s of type %r not understood' %
                                (key, type(value)))


        self.dependencies = dependencies
        self.env = env
        self._build_spec = None
        self.is_initialized = False

    def initialize(self, logger, cache):
        """Initializes the object and its dependencies.

        Any recipe initialization which either a) takes a significant
        amount of time or b) requires interaction with the host system
        should be done after construction in this method. This is so
        that declaration of a Recipe is fast, and so that one can
        declare many dependencies in scripts without actually using
        them.

        Before this method is called, no other methods can be called (only the
        constructor). This method is free to modify any attribute, including
        dependencies.

        Existing entries in ``self.dependencies`` (passed to the constructor)
        will have initialize() called prior to ``self`` being constructed.
        Any new entries added to ``self.dependencies`` should already
        have been initialized.

        After calling this method, ``self`` is considered immutable.

        Subclasses should override _construct.

        Parameters
        ----------

        logger : Logger instance
            Used for logging when interacting with the host system. The recipe
            should not hold on to this after initialization.

        cache : Cache instance
            See :mod:`hashdist.core.cache`. The recipe should not hold on to
            this after initialization.
        """
        if self.is_initialized:
            return
        for dep_name, dep in self.dependencies.iteritems():
            dep.initialize(logger, cache)
        self._initialize(logger, cache)
        self.is_initialized = True

    def get_build_spec(self):
        """
        Returns
        -------

        build_spec : BuildSpec
        
        """
        # the build spec is cached; this is important when fetching dependency
        # artifact IDs
        if self._build_spec is None:
            self._build_spec = self._assemble_build_spec()
        return self._build_spec

    def get_artifact_id(self):
        if self.is_virtual:
            return 'virtual:%s/%s' % (self.name, self.version)
        else:
            return self.get_real_artifact_id()

    def get_real_artifact_id(self):
        return self.get_build_spec().artifact_id

    def get_display_name(self):
        if self.is_virtual:
            return self.get_artifact_id()
        else:
            return core.shorten_artifact_id(self.get_artifact_id()) + '..'

    def fetch_sources(self, source_cache):
        for fetch in self.source_fetches:
            fetch.fetch_into(source_cache)

    def format_tree(self, build_store=None, use_colors=True):
        lines = []
        self._format_tree(lines, {}, 0, build_store, use_colors)
        return '\n'.join(lines)

    def _format_tree(self, lines, visited, level, build_store, use_colors):
        indent_str = '  '
        indent = indent_str * level
        build_spec = self.get_build_spec()
        artifact_id = build_spec.artifact_id
        short_artifact_id = core.shorten_artifact_id(artifact_id) + '..'

        def add_line(left, right):
            lines.append('%-70s%s' % (left, right))

        if build_store is None:
            status = ''
        else:
            status = (colorize(' [ok]', 'bold-blue', use_colors)
                      if build_store.is_present(build_spec)
                      else colorize(' [needs build]', 'bold-red', use_colors))
        
        if artifact_id in visited:
            display_name = visited[artifact_id]
            desc = '%s%s (see above)' % (indent, display_name)
        elif self.is_virtual:
            display_name = self.get_artifact_id()
            desc = '%s%s (=%s)' % (indent, display_name, short_artifact_id)
        else:
            display_name = short_artifact_id
            desc = '%s%s' % (indent, display_name)
        add_line(desc, status)

        visited[artifact_id] = display_name
        
        # bin all repeated artifacts on their own line
        repeated = []
        for dep_name, dep in sorted(self.dependencies.items()):
            if dep.get_real_artifact_id() in visited:
                repeated.append(dep.get_display_name())
            else:
                dep._format_tree(lines, visited, level + 1, build_store, use_colors)
        if repeated:
            add_line(indent + indent_str + ','.join(repeated),
                     colorize(' (see above)', 'yellow', use_colors))

    def __repr__(self):
        return '<Recipe for %s>' % self.get_artifact_id()

    def _assemble_build_spec(self):
        sources = []
        for fetch in self.source_fetches:
            sources.append(fetch.get_spec())

        dep_specs = self.get_dependencies_spec()

        commands = self.get_commands()
        files = self.get_files()
        parameters = self.get_parameters()
        env = self.get_env()
        
        doc = dict(name=self.name, version=self.version, sources=sources, env=env,
                   commands=commands, files=files, dependencies=dep_specs,
                   parameters=parameters)
        build_spec = core.BuildSpec(doc)
        return build_spec

    # Subclasses may override the following
    def _initialize(self, logger, cache):
        pass

    def get_dependencies_spec(self):
        dep_specs = []
        all_dependencies = get_total_dependencies(self)
        dependencies_ids = [dep.get_artifact_id() for dep in all_dependencies.values()]
        for dep_name, dep in all_dependencies.iteritems():
            dep_id = dep.get_artifact_id()
            before_ids = [b.get_artifact_id() for b in dep.dependencies.values()]
            dep_specs.append({"ref": dep_name, "id": dep_id, "in_path": True,
                              "in_hdist_compiler_paths": True,
                              "before": before_ids})
        return dep_specs
    
    def get_commands(self):
        return []

    def get_files(self):
        return []

    def get_parameters(self):
        return {}

    def get_env(self):
        return {}

def get_total_dependencies(recipe, result=None):
    """Find total dependencies.
    """
    if result is None:
        result = {}
    for dep_name, dep in recipe.dependencies.iteritems():
        if dep_name in result:
            if dep is not result[dep_name]:
                raise ValueError("two recipes with the same name conflicting")
            continue
        result[dep_name] = dep
        get_total_dependencies(dep, result)
    return result

def find_dependency_in_spec(spec, ref):
    """Utility to return the dict corresponding to the given ref
    in a dependency build spec document fragment
    """
    for item in spec:
        if item['ref'] == ref:
            return item

class HdistTool(Recipe):
    def __init__(self):
        Recipe.__init__(self, core.HDIST_CLI_ARTIFACT_NAME, core.HDIST_CLI_ARTIFACT_VERSION,
                        is_virtual=True)

    def _assemble_build_spec(self):
        return core.hdist_cli_build_spec()

hdist_tool = HdistTool()
HDIST_TOOL_VIRTUAL = 'virtual:%s/%s' % (core.HDIST_CLI_ARTIFACT_NAME, core.HDIST_CLI_ARTIFACT_VERSION)


def build_recipes(build_store, source_cache, recipes, **kw):
    built = set() # artifact_id
    virtuals = {} # virtual_name -> artifact_id

    def _depth_first_build(recipe):
        for dep_name, dep_pkg in recipe.dependencies.iteritems():
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
    
