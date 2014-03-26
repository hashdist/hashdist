import re
from pprint import pprint
import os
from os.path import join as pjoin
from collections import defaultdict

from ..formats.marked_yaml import load_yaml_from_file, copy_dict_node, dict_like, list_node
from .utils import substitute_profile_parameters, topological_sort, to_env_var
from .. import core
from .exceptions import ProfileError

_STAGE_SECTIONS = ['build_stages', 'profile_links', 'when_build_dependency']

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
        doc, hook_files = load_and_inherit_package(profile, name, package_parameters)
        doc = transform_requested_sources(doc, package_parameters)
        doc = order_package_stages(doc)

        return PackageSpec(name, doc, hook_files)

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
            out_stage = {}
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



def _extend_list(to_insert, lst):
    """Removes items from `lst` that can be found in `to_insert`, and then
    returns a list with `to_insert` at the front and `lst` at the end.
    """
    lst = [x for x in lst if x not in to_insert]
    return to_insert + lst


def name_anonymous_stages(stages):
    """
    Returns a copy of stages (a list of dicts), where every stage without a 'name'
    attribute is given a generated name which depends on the contents of the
    dict. This is used to give a stable ordering. The attributes 'before' and 'after'
    are not considered, as they should not lead to differences in actions/generated
    scripts from the stages.
    """
    def process(stage):
        if 'name' not in stage:
            d = dict(stage)
            for key in ['before', 'after']:
                if key in d:
                    del d[key]
            stage = dict(stage)
            stage['name'] = '__' + core.hash_document('generated_stage_name', d)
        return stage
    return [process(stage) for stage in stages]


def load_and_inherit_package(profile, package_name, parameters, encountered=None):
    """
    Loads a package from the given profile, and transforms the package spec to
    include the parts of the spec inherited through the `extends` section.
    The `extends` section is removed.

    Returns ``(spec_doc, hook_files)``. `hook_files` is a list of
    Python hooks to load; max. one per package/proto-package involved
    """
    if encountered is None:
        encountered = set()
    if package_name in encountered:
        raise ProfileError(package_name, 'Diamond-pattern inheritance not yet supported, package "%s" shows up'
                           'twice when traversing parents' % package_name)
    encountered.add(package_name)
    hook_files = []
    doc = profile.load_package_yaml(package_name, parameters)
    if doc is None:
        raise ProfileError(package_name, 'Package specification not found: %s' % package_name)
    hook = profile.find_package_file(package_name, package_name + '.py')
    if hook is not None:
        hook_files.append(hook)

    doc = dict(doc)  # shallow copy

    # Process when clauses. The top-level when to select the doc already done by
    # profile.load_package_yaml.
    if 'when' in doc:
        del doc['when']

    doc = process_conditionals(doc, parameters)

    # Since we don't support diamond inheritance so far, we simply merge again for every
    # level. This strategy must be changed if we want to support diamond inheritance.
    parent_docs = []
    for parent_name in sorted(doc.get('extends', [])):
        parent_doc, parent_hook_files = load_and_inherit_package(
            profile, parent_name, parameters, encountered=encountered)
        parent_docs.append(parent_doc)
        hook_files[0:0] = parent_hook_files


    # Merge stages lists
    for key in _STAGE_SECTIONS:
        stages = name_anonymous_stages(doc.get(key, []))
        parent_stages = [name_anonymous_stages(parent_doc.get(key, [])) for parent_doc in parent_docs]
        combined_stages = inherit_stages(stages, parent_stages)
        doc[key] = combined_stages

    # Merge dependencies
    deps_section = doc.setdefault('dependencies', {})
    for key in ['build', 'run']:
        deps = set()
        for parent_doc in parent_docs:
            deps.update(parent_doc.get('dependencies', {}).get(key, []))
        lst = deps_section.get(key, [])
        if not isinstance(lst, list):
            raise ProfileError(lst, 'Expected a list')
        deps.update(lst)
        deps_section[key] = sorted(deps)

    if 'extends' in doc:
        del doc['extends']
    return doc, hook_files

def transform_requested_sources(doc, package_parameters):
    '''Allow user to directly inject sources into profiles

    Supports "sources" and "github" parameters
    '''
    
    if 'sources' in package_parameters:
        doc['sources'] = package_parameters['sources']
    elif 'github' in package_parameters:
        # profile has requested a specific commit, overriding package defaults
        from urlparse import urlsplit
        import posixpath
        target_url = package_parameters['github']
        split_url = urlsplit(target_url)
        git_id = posixpath.split(split_url.path)[1]
        git_repo = target_url.rsplit('/commit/')[0] + '.git'
        sources = doc.get('sources', [])
        if len(sources) != 1:
            raise ProfileError('GitHub URL provided but only one source can be overriden')
        source = sources[0]
        source['url'] = git_repo
        source['key'] = 'git:' + git_id
        doc['sources'] = [source]
    return doc


def order_package_stages(package_spec):
    """
    Topologically sort the stages in the sections build_stages,
    profile_links, when_build_dependency.  The name/before/after
    attributes are removed. In the case of 'build_stages', the
    'handler' attribute is set to 'name' if it doesn't exist.
    """
    package_spec = dict(package_spec)
    build_stages = package_spec.setdefault('build_stages', [])
    for i, stage in enumerate(build_stages):
        if 'handler' not in stage:
            build_stages[i] = d = copy_dict_node(stage)
            try:
                name = d['name']
            except KeyError:
                raise ProfileError(build_stages, 'For every build stage, either handler or name must be provided')
            if name.startswith('__'):
                raise ProfileError(stage, 'Build stage lacks handler attribute')
            d['handler'] = name

    for key in _STAGE_SECTIONS:
        package_spec[key] = topological_stage_sort(package_spec.get(key, []))
    return package_spec


def normalize_stages(stages):
    """
    Given a list of 'stages' (dicts with before/after keys), make sure every stage
    has both before/after and that they are lists (a string is made into
    a 1-length list).
    """
    def normalize_stage(stage):
        # turn before/after into lists
        stage = dict(stage)
        for key in ['before', 'after']:
            if key not in stage:
                stage[key] = []
            elif isinstance(stage[key], basestring):
                stage[key] = [stage[key]]
        return stage
    return [normalize_stage(stage) for stage in stages]


def topological_stage_sort(stages):
    """
    Turns a list of stages with keys name/before/after and turns it
    into an ordered list of stages. Every stage must have a unique
    name. The topological sort visits multiple dependent stages
    alphabetically.
    """
    # note that each stage is shallow-copied for modification below
    stages = normalize_stages(stages)
    stage_by_name = dict((stage['name'], dict(stage)) for stage in stages)
    if len(stage_by_name) != len(stages):
        raise ProfileError(stages, 'more than one stage with the same name '
                           '(or anonymous stages with identical contents)')
    # convert 'before' to 'after'
    for stage in stages:
        for later_stage_name in stage['before']:
            try:
                later_stage = stage_by_name[later_stage_name]
            except:
                raise ValueError('stage "%s" referred to, but not available' % later_stage_name)
            later_stage['after'] = later_stage['after'] + [stage['name']]  # copy

    visited = set()
    visiting = set()
    ordered_stage_names = topological_sort(
        sorted(stage_by_name.keys()),
        lambda stage_name: sorted(stage_by_name[stage_name]['after']))
    ordered_stages = [stage_by_name[stage_name] for stage_name in ordered_stage_names]
    for stage in ordered_stages:
        del stage['after']
        del stage['before']
        del stage['name']
    return ordered_stages



def inherit_stages(descendant_stages, ancestors):
    """
    Merges together stage-lists from several ancestors and a single descendant.
    `descendant_stages` is a single list of stages, while `ancestors` is a list
    of lists of stages, one for each ancestor.
    """
    # First make sure ancestors do not conflict; that is, stages in
    # ancestors are not allowed to have the same name. Merge them all
    # together in a name-to-stage dict.
    stages = {} # { name : stage_list }
    for ancestor_stages in ancestors:
        for stage in ancestor_stages:
            stage = dict(stage) # copy from ancestor
            if stage['name'] in stages:
                raise ProfileError(stage['name'],
                                   '"%s" used as the name for a stage in two separate package ancestors' % stage['name'])
            stages[stage['name']] = stage

    # Move on to merge the descendant with the inherited stages. We remove the mode attribute.
    for stage in descendant_stages:
        name = stage.get('name', None)
        if 'mode' in stage:
            mode = stage['mode']
            stage = dict(stage)
            del stage['mode']
        else:
            mode = 'override'

        if mode == 'override':
            x = stages.get(name, {})
            x.update(stage)
            stages[name] = x
        elif mode == 'replace':
            stages[name] = stage
        elif mode == 'remove':
            if name in stages:
                del stages[name]
        else:
            raise ProfileError(mode, 'illegal mode: %s' % mode)
    # We don't care about order, will be topologically sorted later...
    return stages.values()

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


CONDITIONAL_RE = re.compile(r'^when (.*)$')

GLOBALS_LST = [len]
GLOBALS = dict((entry.__name__, entry) for entry in GLOBALS_LST)

def eval_condition(expr, parameters):
    try:
        return bool(eval(expr, GLOBALS, parameters))
    except NameError as e:
        raise ProfileError(expr, "parameter not defined: %s" % e)

def process_conditional_dict(doc, parameters):
    result = dict_like(doc)

    for key, value in doc.items():
        m = CONDITIONAL_RE.match(key)
        if m:
            if eval_condition(m.group(1), parameters):
                if not isinstance(value, dict):
                    raise ProfileError(value, "'when' dict entry must contain another dict")
                to_merge = process_conditional_dict(value, parameters)
                for k, v in to_merge.items():
                    if k in result:
                        raise ProfileError(k, "key '%s' conflicts with another key of the same name "
                                           "in another when-clause" % k)
                    result[k] = v
        else:
            result[key] = process_conditionals(value, parameters)
    return result

def process_conditional_list(lst, parameters):
    if hasattr(lst, 'start_mark'):
        result = list_node([], lst.start_mark, lst.end_mark)
    else:
        result = []
    for item in lst:
        if isinstance(item, dict) and len(item) == 1:
            # lst the form [..., {'when EXPR': BODY}, ...]
            key, value = item.items()[0]
            m = CONDITIONAL_RE.match(key)
            if m:
                if eval_condition(m.group(1), parameters):
                    if not isinstance(value, list):
                        raise ProfileError(value, "'when' clause within list must contain another list")
                    to_extend = process_conditional_list(value, parameters)
                    result.extend(to_extend)
            else:
                result.append(process_conditionals(item, parameters))
        elif isinstance(item, dict) and 'when' in item:
            # lst has the form [..., {'when': EXPR, 'sibling_key': 'value'}, ...]
            if eval_condition(item['when'], parameters):
                item_copy = copy_dict_node(item)
                del item_copy['when']
                result.append(process_conditionals(item_copy, parameters))
        else:
            result.append(process_conditionals(item, parameters))
    return result

def process_conditionals(doc, parameters):
    if isinstance(doc, dict):
        return process_conditional_dict(doc, parameters)
    elif isinstance(doc, list):
        return process_conditional_list(doc, parameters)
    else:
        return doc

