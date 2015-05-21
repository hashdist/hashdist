"""
Package Loader

The loader is responsible for loading a package yaml file and
postprocessing it. Only the postprocessed document is stored, the
loader is discarded immediately.
"""
import re
import os
import collections
from os.path import join as pjoin
from .when import eval_condition
from ..formats.marked_yaml import yaml_dump, copy_dict_node, dict_like, list_node
from .utils import topological_sort
from .. import core
from .exceptions import ProfileError, PackageError
from . import when


class PackageLoaderBase(object):
    """
    Base class for :class:`PackageLoader`

    This base is used to traverse all parents. Any postprocessing that
    you want to apply to all package sources (including parents) goes
    here. Postprocessing that you only want to apply to the package
    source that is being loaded directly goes into
    :class:`PackageLoader`.
    """

    _STAGE_SECTIONS = ['build_stages', 'profile_links', 'when_build_dependency', 'post_process']
    """
    The sections to merge, see :meth:`merge_stages` and meth:`topo_order`
    """

    def __init__(self, spec, param_values):
        self.spec = spec
        self.param_values = param_values
        self.package_file = self.spec.get_yaml(param_values)
        self.doc = dict(self.package_file.doc)
        self.process_conditionals()
        self.load_parents()
        self.merge_stages()

    def process_conditionals(self):
        """
        Process "when" clauses.

        Clauses that do not apply are removed. For those that do
        apply, the "when" conditional is removed.
        """
        self.doc = when.recursive_process_conditionals(self.doc, self.param_values)

    def load_parents(self):
        """
        Load all parents

        The parents are specified in the profile under
        ``extends:``. The `extends` section is then removed.

        Raises:
        -------

        Diamond inheritance is not supported and raises a ``PackageError``.
        """
        self.all_parents = []
        self.direct_parents = []
        for parent_package_spec in self.spec.parents:
            parent_loader = PackageLoaderBase(parent_package_spec, self.param_values)
            self.all_parents[0:0] = parent_loader.all_parents + [parent_loader]
            self.direct_parents[0:0] = [parent_loader]

    def merge_stages(self):
        """
        Recursively merge in stages from the parents
        """
        for key in self._STAGE_SECTIONS:
            self.doc[key] = self._merged_stage(key)

    def _merged_stage(self, key):
        """
        Helper for :meth:`merge_stages`.

        Recursively merge in stages from the parents.

        Arguments:
        ----------

        key : string
            See ``_STAGE_SECTIONS``
        """
        stages = self.get_stages_with_names(key)
        parent_stages = [parent.get_stages_with_names(key)
                         for parent in self.direct_parents]
        return inherit_stages(stages, parent_stages)

    def get_stages_with_names(self, key):
        """
        Return stages with auto-generated names added if necessary.

        Arguments:
        ----------

        key : string
            Top-level key in the yaml document.

        Returns:
        --------

        list of dicts
            Returns a copy of ``stages``, where every stage without a
            ``'name'`` attribute is given a generated name which depends
            on the contents of the dict. This is used to give a stable
            ordering. The attributes ``'before'`` and ``'after'`` are not
            considered, as they should not lead to differences in
            actions/generated scripts from the stages.
        """
        anonymous_names = set()
        def process(stage):
            if 'name' not in stage:
                d = dict([k,v] for k,v in stage.items() if k not in ['before', 'after'])
                stage = dict(stage)
                name = '__' + core.hash_document('generated_stage_name', d)
                stage['name'] = name
                if name in anonymous_names:
                    raise PackageError(stage, 'Stages must be distinct (use "name:" to disambiguate)')
                anonymous_names.add(name)
            return stage
        return map(process, self.doc.get(key, []))

    def merge_dependencies(self):
        # Merge dependencies
        deps_section = self.doc.setdefault('dependencies', {})
        for key in ['build', 'run']:
            deps = set()
            for parent in self.all_parents:
                deps.update(parent.doc.get('dependencies', {}).get(key, []))
            lst = deps_section.get(key, [])
            if not isinstance(lst, list):
                raise PackageError(lst, 'Expected a list for "{0}:"'.format(key))
            deps.update(lst)
            deps_section[key] = sorted(deps)


class PackageLoader(PackageLoaderBase):
    """
    Ephemeral class to load and immediately postprocess the package
    yaml document(s)

    The output is available in the following two attributes:

    Attributes:
    -----------

    doc : dict
        The loaded and post-processed yaml document.
    """

    def __init__(self, package_spec, param_values):
        """
        Load package yaml and postprocess it.
        """
        super(PackageLoader, self).__init__(package_spec, param_values)
        self.override_requested_sources()
        self.expand_globs_in_build_stages_files()
        self.topo_order_stages()

    def override_requested_sources(self):
        """
        Allow profile to override sources in the package

        Supports "sources" and "github" param_values.
        """
        if 'sources' in self.param_values:
            self.doc['sources'] = self.param_values['sources']
        elif 'github' in self.param_values:
            # profile has requested a specific commit, overriding package defaults
            from urlparse import urlsplit
            import posixpath
            target_url = self.param_values['github']
            split_url = urlsplit(target_url)
            git_id = posixpath.split(split_url.path)[1]
            git_repo = target_url.rsplit('/commit/')[0] + '.git'
            sources = self.doc.get('sources', None)
            if sources is None:
                raise PackageError(self.doc, 'GitHub URL provided but no source to override')
            if len(sources) != 1:
                raise PackageError(sources, 'GitHub URL provided but only one source can be overriden')
            source = sources[0]
            source['url'] = git_repo
            source['key'] = 'git:' + git_id
            self.doc['sources'] = [source]

    def expand_globs_in_build_stages_files(self):
        """
        Expand globs in the ``files:`` section of build stages
        """
        import glob
        for stage in self.doc.get('build_stages', []):
            try:
                files = stage['files']
            except KeyError:
                continue
            if not self.package_file.in_directory:
                raise PackageError(files, 'Can only contain "files:" in a package directory')
            pkg_root = self.package_file.dirname
            def strip_pkg_root(path):
                assert path.startswith(pkg_root)
                return path[len(pkg_root) + 1:]
            expanded = []
            for f in files:
                fqn = f if os.path.isabs(f) else pjoin(pkg_root, f)
                if os.path.exists(fqn):
                    expanded.append(f)
                else:
                    matches = glob.glob(fqn)
                    expanded.extend(sorted(map(strip_pkg_root, matches)))
            stage['files'] = expanded

    def topo_order_stages(self):
        """
        List of stages in topo order.

        Topologically sort the stages in the sections build_stages,
        profile_links, when_build_dependency.  The name/before/after
        attributes are removed. In the case of 'build_stages', the
        'handler' attribute is set to 'name' if it doesn't exist.
        """
        doc = dict(self.doc)
        build_stages = doc.setdefault('build_stages', [])
        for i, stage in enumerate(build_stages):
            if 'handler' not in stage:
                build_stages[i] = d = copy_dict_node(stage)
                try:
                    name = d['name']
                except KeyError:
                    raise PackageError(build_stages,
                            'For every build stage, either handler or name must be provided')
                if name.startswith('__'):
                    raise PackageError(stage, 'Build stage lacks handler attribute')
                d['handler'] = name

        for key in self._STAGE_SECTIONS:
            doc[key] = topological_stage_sort(doc.get(key, []))
        self.doc = doc

    def get_hook_files(self):
        """
        Hook source files referenced from the package and its parents.

        Returns
        -------

        list of string
            The names of the hook files referenced by the package and
            its parents.
        """
        hook_files = []
        for loader in self.all_parents + [self]:
            hook = loader.package_file.hook_filename
            if hook:
                hook_files.append(hook)
        return hook_files


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
        raise PackageError(stages, 'more than one stage with the same name '
                           '(or anonymous stages with identical contents)')

    def get_stage_by_name(name):
        try:
            return stage_by_name[name]
        except KeyError:
            raise PackageError(name, 'stage "{0}" referred to, but '
                               'nowhere defined'.format(name))

    # convert 'before' to 'after'
    for stage in stages:
        for later_stage_name in stage['before']:
            later_stage = get_stage_by_name(later_stage_name)
            later_stage['after'] = later_stage['after'] + [stage['name']]  # copy

    # sort only using "after"
    ordered_stage_names = topological_sort(
        sorted(stage_by_name.keys()),
        lambda stage_name: sorted(get_stage_by_name(stage_name)['after']))
    ordered_stages = [get_stage_by_name(name) for name in ordered_stage_names]
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
                raise PackageError(stage['name'], '"%s" used as the name for a stage in two '
                                   'separate package ancestors' % stage['name'])
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
        elif mode == 'update':
            if name not in stages:
                raise PackageError(name, 'cannot use mode: update on an empty stage')
            x = stages[name]
            for node_name, node_value in stage.iteritems():
                if node_name not in x:
                    x[node_name] = node_value
                elif isinstance(node_value, dict):
                    x[node_name].update(node_value)
                elif isinstance(node_value, list):
                    x[node_name].extend(node_value)
        elif mode == 'replace':
            stages[name] = stage
        elif mode == 'remove':
            if name in stages:
                del stages[name]
        else:
            raise PackageError(name, 'illegal mode: %s' % mode)
    # We don't care about order, will be topologically sorted later...
    return stages.values()







