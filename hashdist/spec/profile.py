"""

Not supported:

 - Diamond inheritance

"""
from pprint import pprint
import tempfile
import os
import shutil
from os.path import join as pjoin
import re

from ..formats.marked_yaml import load_yaml_from_file
from .utils import substitute_profile_parameters
from .. import core
from .exceptions import ProfileError

class ConflictingProfilesError(Exception):
    pass


class Profile(object):
    """
    Profiles acts as nodes in a tree, with `extends` containing the
    parent profiles (which are child nodes in a DAG).
    """
    def __init__(self, filename, doc, parents):
        self.filename = filename
        self.doc = doc
        self.parents = parents
        # for now, we require that bases have non-overlapping parameter keys
        self.parameters = {}
        for base in parents:
            for k, v in base.parameters.iteritems():
                if k in self.parameters:
                    raise ConflictingProfilesError('two base profiles set same parameter %s' % k)
                self.parameters[k] = v
        self.parameters.update(doc.get('parameters', {}))

        d = os.path.dirname(filename)
        self._packages_dir = os.path.abspath(pjoin(d, doc['packages_dir'])) if 'packages_dir' in doc else None
        self._base_dir = os.path.abspath(pjoin(d, doc['base_dir'])) if 'base_dir' in doc else None
        self._yaml_cache = {}

    def _find_resource_in_parents(self, resource_type, resource_getter_name, resource_name, *args):
        filename = None
        for parent in self.parents:
            parent_filename = getattr(parent, resource_getter_name)(resource_name, *args)
            if parent_filename is not None:
                if filename is not None:
                    raise ConflictingProfilesError('%s %s found in sibling included profiles' %
                                                   (resource_type, resource_name))
            filename = parent_filename
        return filename

    def load_package_yaml(self, pkgname):
        doc = self._yaml_cache.get(('package', pkgname), None)
        if doc is None:
            p = self.find_package_file(pkgname, pkgname + '.yaml')
            doc = load_yaml_from_file(p) if p is not None else None
            self._yaml_cache['package', pkgname] = doc
        return doc

    def load_base_yaml(self, pkgname):
        doc = self._yaml_cache.get(('base', pkgname), None)
        if doc is None:
            p = self.find_base_file(pkgname + '.yaml')
            doc = load_yaml_from_file(p) if p is not None else None
            self._yaml_cache['base', pkgname] = doc
        return doc        

    def find_package_file(self, pkgname, filename=None):
        if filename is None:
            filename = pkgname + '.yaml'
        # try pkgs/foo.yaml
        p = None
        if self._packages_dir is not None:
            p = pjoin(self._packages_dir, filename)
            if not os.path.exists(p):
                # try pkgs/foo/foo.yaml
                p = pjoin(self._packages_dir, pkgname, filename)
                if not os.path.exists(p):
                    p = None
        if p is None:
            # try included profiles; only allow it to come from one of them
            p = self._find_resource_in_parents('package', 'find_package_file', pkgname, filename)
        return p

    def find_base_file(self, name):
        filename = None
        if self._base_dir is not None:
            filename = pjoin(self._base_dir, name)
            if not os.path.exists(filename):
                filename = None
        if filename is None:
            filename = self._find_resource_in_parents('base file', 'find_base_file', name)
        return filename

    def get_python_path(self, path=None):
        """
        Constructs a list that can be inserted into sys.path to make
        .py-files in the base subdirectory of this profile and any
        base-profile available.
        """
        if path is None:
            path = []
        for base in self.parents:
            base.get_python_path(path)
        if self._base_dir is not None:
            path.insert(0, self._base_dir)
        return path

    def get_packages(self):
        def parse_package(pkg):
            if isinstance(pkg, basestring):
                return pkg, {}
            elif isinstance(pkg, dict):
                if len(pkg) != 1:
                    raise ValueError('package must be given as a single {name : attr-dict} dict')
                return pkg.keys()[0], pkg.values()[0]
            else:
                raise TypeError('Not a package: %s' % pkg)

        packages = {}
        # import from base
        for base in self.parents:
            for k, v in base.get_packages().iteritems():
                if k in packages:
                    raise ConflictingProfilesError('package %s found in two different base profiles')
                packages[k] = v
        # parse this profiles packages section
        lst = self.doc.get('packages', [])
        for entry in lst:
            name, settings = parse_package(entry)
            if settings.get('skip', False):
                if name in packages:
                    del packages[name]
                continue
            if name in packages:
                packages[name].update(settings)
            else:
                packages[name] = settings

        return packages

    def __repr__(self):
        return '<Profile %s>' % self.filename



class TemporarySourceCheckouts(object):
    """
    A context that holds a number of sources checked out to temporary directories
    until it is released.
    """
    REPO_NAME_PATTERN = re.compile(r'^<([^>]+)>(.*)')

    def __init__(self, source_cache):
        self.repos = {}  # name : (key, tmpdir)
        self.source_cache = source_cache

    def checkout(self, name, key, urls):
        if name in self.repos:
            existing_key, path = self.repos[name]
            if existing_key != key:
                raise ProfileError(name, 'Name "%s" used for two different commits within a profile' % name)
        else:
            if len(urls) != 1:
                raise ProfileError(urls, 'Only a single url currently supported')
            self.source_cache.fetch(urls[0], key, 'profile-%s' % name)
            path = tempfile.mkdtemp()
            try:
                self.source_cache.unpack(key, path)
            except:
                shutil.rmtree(path)
                raise
            else:
                self.repos[name] = (key, path)
        return path

    def close(self):
        for key, tmpdir in self.repos.values():
            shutil.rmtree(tmpdir)
        self.repos.clear()

    def resolve(self, path):
        """
        Expand path-names of the form ``<repo_name>/foo/bar``,
        replacing the ``<repo_name>`` part (where ``repo_name`` is
        given to `checkout`, and the ``<`` and ``>`` are literals)
        with the temporary checkout of the given directory.
        """
        m = self.REPO_NAME_PATTERN.match(path)
        if m:
            name = m.group(1)
            if name not in self.repos:
                raise ProfileError(path, 'No temporary checkouts are named "%s"' % name)
            key, tmpdir = self.repos[name]
            return tmpdir + m.group(2)
        else:
            return path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def load_profile(checkouts, include_doc, cwd=None):
    """
    Loads a Profile given an include document fragment, e.g.::

        file: ../foo/profile.yaml

    or::

        file: linux/profile.yaml
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

    if isinstance(include_doc, str):
        include_doc = {'file': include_doc}
    
    if 'key' in include_doc:
        # Check out git repo to temporary directory. cwd is relative to checked out root.
        cwd = checkouts.checkout(include_doc['name'], include_doc['key'], include_doc['urls'])

    profile = resolve_path(cwd, include_doc['file'])

    doc = load_yaml_from_file(profile)
    if doc is None:
        doc = {}
    if 'extends' in doc:
        new_cwd = os.path.dirname(profile)
        parents = [load_profile(checkouts, ancestor, cwd=new_cwd) for ancestor in doc['extends']]
        del doc['extends']
    else:
        parents = []
    return Profile(profile, doc, parents)
