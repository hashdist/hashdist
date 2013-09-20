from pprint import pprint
import os
from os.path import join as pjoin

from .marked_yaml import marked_yaml_load
from .utils import substitute_profile_parameters, topological_sort
from .. import core

_package_spec_cache = {}

class IllegalPackageSpecError(Exception):
    pass

class PackageSpec(object):
    """

    ancestor_docs: dict of {ancestor_name: document of ancestor}

    """
    def __init__(self, name, doc, ancestor_docs):
        self.name = name
        self.doc = dict(doc)  # copy, we want to modify it to remove processed stages

        # Extract ancestor docs
        self.ancestor_docs = {}
        extends = doc.get('extends', [])
        for name in extends:
            try:
                self.ancestor_docs[name] = ancestor_docs[name]
            except KeyError:
                raise ValueError('Missing "%s" in ancestor_docs' % name)

        deps = doc.get('dependencies', {})
        self.build_deps = deps.get('build', [])
        self.run_deps = deps.get('run', [])
        if not isinstance(self.build_deps, list) or not isinstance(self.run_deps, list):
            raise TypeError('dependencies must be a list')
        self._inherit()

    @staticmethod
    def load_from_file(name, filename):
        """
        Loads a single package from file; no ancestors (extends) allowed
        """
        filename = os.path.realpath(filename)
        obj = _package_spec_cache.get(filename, None)
        if obj is None:
            with open(filename) as f:
                doc = marked_yaml_load(f)
            if doc is None:
                doc = {}
            obj = _package_spec_cache[filename] = PackageSpec(name, doc, {})
        return obj

    def _inherit(self):
        """
        Merge build_stages and profile_links stages
        """
        for key in ['build_stages', 'profile_links']:
            self_stages = self.doc.get(key, [])
            if key in self.doc:
                del self.doc[key]
            ancestor_stages = [ancestor_doc.get(key, []) for ancestor_doc
                               in self.ancestor_docs.values()]
            combined_stages = inherit_stages(self_stages, ancestor_stages)
            sorted_stages = topological_stage_sort(combined_stages)
            setattr(self, key, sorted_stages)        

    def fetch_sources(self, source_cache):
        for source_clause in self.doc.get('sources', []):
            source_cache.fetch(source_clause['url'], source_clause['key'], self.name)

    def assemble_build_script(self, parameters):
        """
        Return build script (Bash script) that should be run to build package.
        """
        return assemble_build_script(self.build_stages, parameters)

    def assemble_build_spec(self, source_cache, parameters, dependency_id_map, dependency_packages):
        """
        Returns the build.json for building the package. Also, the build script (Bash script)
        that should be run to build the package is uploaded to the given source cache.
        """
        commands = []
        for dep_name in self.build_deps:
            dep_pkg = dependency_packages[dep_name]
            commands += dep_pkg.assemble_build_import_commands(parameters, ref=dep_name.upper())

        build_script = self.assemble_build_script(parameters)
        build_script_key = source_cache.put({'build.sh': build_script})
        build_spec = create_build_spec(self.name, self.doc, parameters, dependency_id_map,
                                       commands, [{'target': '.', 'key': build_script_key}])
        return build_spec

    def assemble_link_dsl(self, parameters, ref, target):
        """
        Creates the input document to ``hit create-links`` from the information in a package
        description.
        """
        rules = []
        for in_stage in self.profile_links:
            out_stage = {}
            if 'link' in in_stage:
                select = substitute_profile_parameters(in_stage["link"], parameters)
                rules.append({
                    "action": "relative_symlink",
                    "select": "${%s}/%s" % (ref, select),
                    "prefix": "${%s}" % ref,
                    "target": target,
                    "dirs": in_stage.get("dirs", False)})
            elif 'exclude' in in_stage:
                select = substitute_profile_parameters(in_stage["exclude"], parameters)
                rules.append({"action": "exclude",
                              "select": select})
            elif 'launcher' in in_stage:
                select = substitute_profile_parameters(in_stage["launcher"], parameters)
                rules.append({"action": "launcher",
                              "select": "${%s}/%s" % (ref, select),
                              "prefix": "${%s}" % ref,
                              "target": target})
            else:
                raise ValueError('Need either "link", "launcher" or "exclude" key in profile_links entries')
        return rules

    def assemble_build_import_commands(self, parameters, ref):
        return [_process_on_import(env_action, parameters, ref)
                for env_action in self.doc.get('when_build_dependency', [])]

class PackageSpecSet(object):
    """
    A dict-like representing a subset of packages, but they are lazily
    loaded
    """
    def __init__(self, resolver, packages):
        self.resolver = resolver
        self.packages = packages
        self._values = None

    def __getitem__(self, key):
        if key not in self.packages:
            raise KeyError('Package %s not found' % key)
        return self.resolver.parse_package(key)

    def values(self):
        if self._values is None:
            self._values = [self[key] for key in self.packages]
        return self._values

    def keys(self):
        return list(self.packages)

    def __repr__(self):
        return '<%s: %r>' % (self.__class__.__name__, self.packages)


class PackageSpecResolver(object):
    def __init__(self, path):
        self.path = path

    def parse_package(self, pkgname):
        filename = os.path.realpath(pjoin(self.path, pkgname, '%s.yaml' % pkgname))
        obj = _package_spec_cache.get(filename, None)
        if obj is None:
            with open(filename) as f:
                doc = marked_yaml_load(f)
            obj = _package_spec_cache[filename] = PackageSpec.load(doc, self)
        return obj


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
        raise ValueError('`stages` has entries with the same name')
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
    return ordered_stages


def assemble_build_script(stages, parameters):
    """
    Turns the complete set of build-stages (as a list of document fragments)
    and assembles them into the final build script, which is returned
    as a string.
    """
    lines = ['set -e']
    for stage in stages:
        assert stage['handler'] == 'bash' # for now
        snippet = stage['bash'].strip()
        snippet = substitute_profile_parameters(snippet, parameters)
        lines.append(snippet)
    return '\n'.join(lines) + '\n'


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
            if stage['name'] in stages:
                raise IllegalPackageSpecError('"%s" used as the name for a stage in two separate package ancestors' %
                                              stage['name'])
            stages[stage['name']] = stage
    # Move on to merge the descendant with the inherited stages. We remove the mode attribute.
    for stage in descendant_stages:
        name = stage['name']
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
            raise IllegalPackageSpecError('illegal mode: %s' % mode)
    # We don't care about order, will be topologically sorted later...
    return stages.values()

def _process_on_import(action, parameters, ref):
    action = dict(action)
    if not ('prepend_path' in action or 'append_path' in action or 'set' in action):
        raise ValueError('on_import action must be one of prepend_path, append_path, set')
    value = substitute_profile_parameters(action['value'], parameters)
    value = value.replace('${ARTIFACT}', '${%s}' % ref)
    if '$' in value.replace('${', ''):
        # a bit crude, but works for now -- should properly disallow non-${}-variables,
        # in order to prevent $ARTIFACT from cropping up
        raise IllegalPackageSpecError('Please use "${VAR}", not $VAR')
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
        imports.append({'ref': '%s' % dep_name.upper(), 'id': dependency_id_map(dep_name)})

    # sources
    sources = list(extra_sources)
    for source_clause in pkg_doc.get("sources", []):
        sources.append({"target": "src", "key": source_clause["key"]})

    # build commands
    commands = []
    commands.append({"set": "BASH", "nohash_value": parameters['BASH']})
    if 'PATH' in parameters:
        commands.append({"set": "PATH", "nohash_value": parameters['PATH']})
    commands.append({"chdir": "src"})
    commands.append({"cmd": ["$BASH", "../build.sh"]})

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

