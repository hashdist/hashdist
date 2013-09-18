import os
from os.path import join as pjoin

from .marked_yaml import marked_yaml_load
from .utils import substitute_profile_parameters, topological_sort
from .. import core

_package_spec_cache = {}

class PackageSpec(object):
    def __init__(self, name, doc):
        self.name = name
        self.doc = doc
        deps = doc.get('dependencies', {})
        self.build_deps = deps.get('build', [])
        self.run_deps = deps.get('run', [])
        if not isinstance(self.build_deps, list) or not isinstance(self.run_deps, list):
            raise TypeError('dependencies must be a list')


    @staticmethod
    def load_from_file(name, filename):
        filename = os.path.realpath(filename)
        obj = _package_spec_cache.get(filename, None)
        if obj is None:
            with open(filename) as f:
                doc = marked_yaml_load(f)
            if doc is None:
                doc = {}
            obj = _package_spec_cache[filename] = PackageSpec(name, doc)
        return obj

    def fetch_sources(self, source_cache):
        for source_clause in self.doc.get('sources', []):
            source_cache.fetch(source_clause['url'], source_clause['key'], self.name)

    def assemble_build_script(self, parameters):
        """
        Return build script (Bash script) that should be run to build package.
        """
        build_stages = self.doc.get('build_stages', [])
        return assemble_build_script(build_stages, parameters)

    def assemble_build_spec(self, source_cache, parameters, dependency_id_map):
        """
        Returns the build.json for building the package. Also, the build script (Bash script)
        that should be run to build the package is uploaded to the given source cache.
        """
        build_script = self.assemble_build_script(parameters)
        build_script_key = source_cache.put({'build.sh': build_script})
        build_spec = create_build_spec(self.name, self.doc, parameters, dependency_id_map,
                                       [{'target': '.', 'key': build_script_key}])
        return build_spec

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
    stages = normalize_stages(stages)
    stages = topological_stage_sort(stages)
    for stage in stages:
        assert stage['handler'] == 'bash' # for now
        snippet = stage['bash'].strip()
        snippet = substitute_profile_parameters(snippet, parameters)
        lines.append(snippet)
    return '\n'.join(lines) + '\n'


def _process_on_import(action, parameters):
    action = dict(action)
    if not ('prepend_path' in action or 'append_path' in action or 'set' in action):
        raise ValueError('on_import action must be one of prepend_path, append_path, set')
    action['value'] = substitute_profile_parameters(action['value'], parameters)
    return action


def create_build_spec(pkg_name, pkg_doc, parameters, dependency_id_map, extra_sources=()):
    if isinstance(dependency_id_map, dict):
        dependency_id_map = dependency_id_map.__getitem__
                  
    if 'BASH' not in parameters:
        raise ValueError('BASH must be provided in profile parameters')

    # dependencies
    on_import = [_process_on_import(env_action, parameters)
                 for env_action in pkg_doc.get('on_import', [])]
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

    # install
    install_link_rules = [
        {"action": "relative_symlink",
         "select": "$ARTIFACT/lib/python*/site-packages/*",
         "prefix": "$ARTIFACT",
         "target": "$PROFILE",
         "dirs": True},
        {"action": "exclude",
         "select": "$ARTIFACT/lib/python*/site-packages/**/*"},
        {"action": "relative_symlink",
         "select": "$ARTIFACT/*/**/*",
         "prefix": "$ARTIFACT",
         "target": "$PROFILE"}
        ]

    # assemble
    build_spec = {
        "name": pkg_name,
        "version": pkg_doc.get("version", "na"),
        "build": {
            "import": imports,
            "commands": commands,
            },
        "sources": sources,
        "on_import": on_import,
        "profile_install": {
            "commands": [{"hit": ["create-links", "$in0"],
                          "inputs": [{"json": install_link_rules}]}],
            }
        }
        
    return core.BuildSpec(build_spec)
