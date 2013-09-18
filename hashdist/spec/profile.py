"""

Not supported:

 - Diamond inheritance

"""

import tempfile
import os
import shutil
from os.path import join as pjoin

from .marked_yaml import marked_yaml_load
from .utils import substitute_profile_parameters
from .. import core

class ConflictingProfilesError(Exception):
    pass

class FileNotFoundError(Exception):
    def __init__(self, msg, relname):
        Exception.__init__(self, msg)
        self.relname = relname

class FileResolver(object):
    """
    Represents a tree of directories containing profile information.
    Is used to resolve which file to load things from.
    """
    def __init__(self, children):
        self.children = children


class DirectoryRemover(object):
    """
    Removes a directory once nothing references this object any longer
    """
    def __init__(self, path):
        self.path = path

    def __del__(self):
        if self.path:
            shutil.rmtree(self.path)
            self.path = None


class Profile(object):
    """
    Profiles acts as nodes in a tree, with `extends` containing the
    parent profiles (which are child nodes in a DAG).

    Other nodes in the DAG are PackageFiles and BaseFiles.
    """
    def __init__(self, filename, doc, includes, hold_ref_to=None):
        self.filename = filename
        self.doc = doc
        self.includes = includes
        self._hold_ref_to = hold_ref_to
        # for now, we require that bases have non-overlapping parameter keys
        self.parameters = {}
        for base in includes:
            for k, v in base.parameters.iteritems():
                if k in self.parameters:
                    raise ConflictingProfilesError('two base profiles set same parameter %s' % k)
                self.parameters[k] = v
        self.parameters.update(doc.get('parameters', {}).get('global', {}))

        d = os.path.dirname(filename)
        self._packages_dir = os.path.abspath(pjoin(d, doc['packages_dir'])) if 'packages_dir' in doc else None
        self._base_dir = os.path.abspath(pjoin(d, doc['base_dir'])) if 'base_dir' in doc else None

    def _find_resource_in_includes(self, resource_type, resource_getter_name, resource_name):
        filename = None
        for child in self.includes:
            child_filename = getattr(child, resource_getter_name)(resource_name)
            if child_filename is not None:
                if filename is not None:
                    raise ConflictingProfilesError('%s %s found in sibling included profiles' %
                                                   (resource_type, resource_name))
            filename = child_filename
        return filename

    def find_package_file(self, name):
        # try pkgs/foo.yaml
        filename = None
        if self._packages_dir is not None:
            filename = pjoin(self._packages_dir, name + '.yaml')
            if not os.path.exists(filename):
                # try pkgs/foo/foo.yaml
                filename = pjoin(self._packages_dir, name, name + '.yaml')
                if not os.path.exists(filename):
                    filename = None

        if filename is None:
            # try included profiles; only allow it to come from one of them
            filename = self._find_resource_in_includes('package', 'find_package_file', name)
        return filename

    def find_base_file(self, name):
        filename = None
        if self._base_dir is not None:
            filename = pjoin(self._base_dir, name)
            if not os.path.exists(filename):
                filename = None
        if filename is None:
            filename = self._find_resource_in_includes('base file', 'find_base_file', name)
        return filename

    def get_python_path(self, path=None):
        """
        Constructs a list that can be inserted into sys.path to make
        .py-files in the base subdirectory of this profile and any
        base-profile available.
        """
        if path is None:
            path = []
        for base in self.extends:
            base.get_python_path(path)
        path.insert(0, pjoin(self.basedir, 'base'))
        return path

    def get_packages(self):
        """
        Returns a dict of package includeded in the profile, including
        processing of package specs by base profiles.

        The key is the 'virtual' name of the package within the
        profile. The value is a tuple ``(name, variant)``, where
        variant is `None` if none is given. As a special case,
        'package/skip' removes a package from the dict (which may have
        been added by an ancestor profile).
        """
        def parse_entry(s):
            parts = s.split('/')
            if len(parts) == 1:
                return (parts[0], None)
            elif len(parts) == 2:
                return tuple(parts)
            else:
                raise ValueError('Too many slashes in package name: %s' % s)

        packages = {}
        # import from base
        for base in self.extends:
            for k, v in base.get_packages().iteritems():
                if k in packages:
                    raise ConflictingProfilesError('package %s found in two different base profiles')
                packages[k] = v
        # parse this profiles packages section
        lst = self.doc.get('packages', [])
        for entry in lst:
            if isinstance(entry, basestring):
                name, variant = parse_entry(entry)
                vname = name
            elif len(entry) != 1:
                raise ValueError('each package specification dict should have a single key only')
            else:
                vname, s = entry.items()[0]
                name, variant = parse_entry(s)

            if variant == 'skip':
                if vname in packages:
                    del packages[vname]
                continue
            packages[vname] = (name, variant)

        return packages

    def __repr__(self):
        return '<Profile %s>' % self.filename


def load_profile(source_cache, include_doc, cwd=None):
    """
    Loads a Profile given an include document fragment, e.g.::

        profile: ../foo/profile.yaml

    or::

        profile: linux/profile.yaml
        urls: [git://github.com/hashdist/hashstack.git]
        key: git:5aeba2c06ed1458ae4dc5d2c56bcf7092827347e

    The load happens recursively, including fetching any remote
    dependencies.
    """
    def resolve_path(cwd, p):
        if not os.path.isabs(p):
            if cwd is None:
                cwd = os.getcwd()
            p = os.path.abspath(pjoin(cwd, p))
        return p
    
    if 'key' in include_doc:
        # Check out git repo to temporary directory. cwd is relative to checked out root.
        assert len(include_doc['urls']) == 1
        cwd = tempfile.mkdtemp()
        dir_remover = DirectoryRemover(cwd)
        source_cache.fetch(include_doc['urls'][0], include_doc['key'], 'stack-desc')
        source_cache.unpack(include_doc['key'], cwd)
    else:
        dir_remover = None

    profile = resolve_path(cwd, include_doc['profile'])

    with open(profile) as f:
        doc = marked_yaml_load(f)
    if doc is None:
        doc = {}
    if 'include' in doc:
        new_cwd = os.path.dirname(profile)
        includes = [load_profile(source_cache, include, cwd=new_cwd) for include in doc['include']]
        del doc['include']
    else:
        includes = []
    return Profile(profile, doc, includes, hold_ref_to=dir_remover)
