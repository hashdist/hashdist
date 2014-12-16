"""
:mod:`hashdist.spec.profile` --- HashDist Profiles
==================================================

Not supported:

 - Diamond inheritance

"""

import collections
import tempfile
import os
import shutil
from os.path import join as pjoin
import re
import glob
from urlparse import urlsplit
from urllib import urlretrieve
import posixpath

from ..formats.marked_yaml import load_yaml_from_file, is_null, marked_yaml_load
from .utils import substitute_profile_parameters
from .. import core
from .exceptions import ProfileError, PackageError


GLOBALS_LST = [len]
GLOBALS = dict((entry.__name__, entry) for entry in GLOBALS_LST)

def eval_condition(expr, parameters):
    try:
        return bool(eval(expr, GLOBALS, parameters))
    except NameError as e:
        raise ProfileError(expr, "parameter not defined: %s" % e)


class PackageYAML(object):
    """
    Holds content of a package yaml file

    The content is unmodified except for `{{VAR}}` variable expansion.

    Attributes
    ----------

    doc : dict
        The deserialized yaml source

    in_directory : boolean
        Whether the yaml file is in its private package directory that
        may contain other files.

    parameters : dict of str
        Parameters with the defaults from the package yaml file applied

    filename : str
        Full qualified name of the package yaml file

    hook_filename : str or ``None``
        Full qualified name of the package ``.py`` hook file, if it
        exists.
    """

    def __init__(self, used_name, filename, parameters, in_directory):
        """
        Constructor

        Parameters
        ----------

        used_name : str
            The actual package name (as overridden by ``use:``, if
            present. E.g. ``mpich``, and not the virtual package
            name``mpi``).

        filename : str
            Full qualified name of the package yaml file

        parameters : dict
            The parameters to use for `{{VAR}}` variable
            expansion. Will be supplemented by the ``defaults:`
            section in the package yaml.

        in_directory : boolean
            Whether the package yaml file is in its own directory.
        """
        self.filename = filename
        self._init_load(filename, parameters)
        self.in_directory = in_directory
        hook = os.path.abspath(pjoin(os.path.dirname(filename), used_name + '.py'))
        self.hook_filename = hook if os.path.exists(hook) else None

    def _init_load(self, filename, parameters):
        # To support the defaults section we first load the file, read defaults,
        # then load file again (since parameter expansion is currently done on
        # stream level not AST level).
        doc = load_yaml_from_file(filename, collections.defaultdict(str))
        defaults = doc.get('defaults', {})
        all_parameters = collections.defaultdict(str, defaults)
        all_parameters.update(parameters)
        self.parameters = all_parameters
        self.doc = load_yaml_from_file(filename, all_parameters)

    def __repr__(self):
        return self.filename

    @property
    def dirname(self):
        """
        Name of the package directory.

        Returns
        -------

        String, full qualified name of the directory containing the
        yaml file.

        Raises
        ------

        A ``ValueError`` is raised if the package is a stand-alone
        yaml file, that is, there is no package directory.
        """
        if self.in_directory:
            return os.path.dirname(self.filename)
        else:
            raise ValueError('stand-alone package yaml file')


class Profile(object):
    """
    Profiles acts as nodes in a tree, with `extends` containing the
    parent profiles (which are child nodes in a DAG).
    """
    def __init__(self, logger, doc, checkouts_manager):
        self.logger = logger
        self.doc = doc
        self.parameters = dict(doc.get('parameters', {}))
        self.file_resolver = FileResolver(checkouts_manager, doc.get('package_dirs', []))
        self.checkouts_manager = checkouts_manager
        self.hook_import_dirs = doc.get('hook_import_dirs', [])
        self.packages = doc['packages']
        self._yaml_cache = {} # (filename: [list of documents, possibly with when-clauses])

    def resolve(self, path):
        """Turn <repo>/path into /tmp/foo-342/path"""
        return self.checkouts_manager.resolve(path)

    def _use_for_package(self, pkgname):
        """
        Return the actual package name (yaml file).

        Parameters
        ----------

        pkgname : str
            The name of the package

        Returns
        -------

        If there is a ``name: {use: alternate_name}`` section in the
        profile, then this method will return the alternate
        name. Otherwise, ``pkgname`` is returned.
        """
        try:
            return self.packages[pkgname]['use']
        except KeyError:
            return pkgname

    def load_package_yaml(self, pkgname, parameters):
        """
        Search for the yaml source and load it.

        Load the source for ``pkgname`` (after substitution by a
        ``use:`` profile section, if any) from either

        * ``$pkgs/pkgname.yaml``,
        * ``$pkgs/pkgname/pkgname.yaml``, or
        * ``$pkgs/pkgname/pkgname-*.yaml``

        by searching through the paths in the ``package_dirs:``
        profile setting. The paths are searched order, and only the
        first match per basename is used. That is,
        ``$pkgs/foo/foo.yaml`` overrides ``$pkgs/foo.yaml``. And
        ``$pkgs/foo/foo-bar.yaml`` is returned in addition.

        In case of many matches, any when'-clause is evaluated on
        `parameters` and a single document should result, otherwise an
        exception is raised. A document without a when-clause is
        overridden by those with a when-clause.

        Parameters
        ----------

        pkgname : string
            Name of the package (excluding ``.yaml``).

        parameters : dict
            The profile parameters.

        Returns
        -------

        A :class:`PackageYAML` instance if successfull.

        Raises
        ------

        * class:`~hashdist.spec.exceptions.ProfileError`` is raised if
          there is no such package.

        * class:`~hashdist.spec.exceptions.PackageError`` is raised if
          a package conflicts with a previous one.
        """
        use = self._use_for_package(pkgname)
        yaml_files = self._yaml_cache.get(('package', use), None)
        if yaml_files is None:
            yaml_filename = use + '.yaml'
            matches = self.file_resolver.glob_files([yaml_filename,
                                                     pjoin(use, yaml_filename),
                                                     pjoin(use, use + '-*.yaml')],
                                                    match_basename=True)
            self._yaml_cache['package', use] = yaml_files = [
                PackageYAML(use, filename, parameters, pattern != yaml_filename)
                for match, (pattern, filename) in matches.items()]
            self.logger.info('Resolved package %s to %s', pkgname,
                             [filename for match, (pattern, filename) in matches.items()])
        no_when_file = None
        with_when_file = None
        for pkg in yaml_files:
            if 'when' not in pkg.doc:
                if no_when_file is not None:
                    raise PackageError(pkg.doc, "Two specs found for package %s without"
                                       " a when-clause to discriminate" % use)
                no_when_file = pkg
                continue
            doc_when = pkg.doc['when']
            if eval_condition(doc_when, parameters):
                if with_when_file is not None:
                    raise PackageError(doc_when, "Selected parameters for package %s matches both '%s' and '%s'" %
                                       (use, doc_when, with_when_file))
                with_when_file = pkg
        result = with_when_file if with_when_file is not None else no_when_file
        if result is None:
            raise ProfileError(use, 'No yaml file for package "{0}" found'.format(use))
        return result

    def find_package_file(self, pkgname, filename):
        """
        Find a package resource file.

        Search for the file at:

        * ``$pkgs/filename``,

        * ``$pkgs/pkgname/filename``,

        in this order.

        Parameters
        ----------

        pkgname : string
            Name of the package (excluding ``.yaml``).

        filename : string
            File name to look for.

        Returns
        -------

        The full qualifiedfilename as a string, or ``None`` if no file
        is found.
        """
        use = self._use_for_package(pkgname)
        return self.file_resolver.find_file([filename, pjoin(use, filename)])

    def __repr__(self):
        return 'Profile containing ' + ', '.join(
            key[1] for key in self._yaml_cache.keys() if key[0] == 'package')


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

class FileResolver(object):
    """
    Find spec files in an overlay-based filesystem, consulting many
    search paths in order.  Supports the
    ``<repo_name>/some/path``-convention.
    """
    def __init__(self, checkouts_manager, search_dirs):
        self.checkouts_manager = checkouts_manager
        self.search_dirs = search_dirs

    def find_file(self, filenames):
        """
        Search for a file.

        Search for a file with the given filename/path relative to the
        root of each of ``self.search_dirs``.

        Parameters
        ----------

        filenames : list of strings
            Filenames to seach for. The entire list will be searched
            before moving on to the next layer/overlay.

        Returns
        -------

        Returns the found file (in the
        ``<repo_name>/some/path``-convention), or None if no file was
        found.
        """
        if isinstance(filenames, basestring):
            filenames = [filenames]
        for overlay in self.search_dirs:
            for p in filenames:
                filename = pjoin(overlay, p)
                if os.path.exists(self.checkouts_manager.resolve(filename)):
                    return filename
        return None

    def glob_files(self, patterns, match_basename=False):
        """
        Match file globs.

        Like ``find_file``, but uses a set of patterns and tries to match each
        pattern against the filesystem using ``glob.glob``.

        Parameters
        ----------

        patterns : list of strings
            Glob patterns

        match_basename : boolean
            If ``match_basename`` is set, only the basename of the file
            is compared (i.e., one file with each basename will be
            returned).

        Returns
        -------

        The result is a dict mapping the "matched name" to a pair
        (pattern, full qualified path).

        * The matched name is a path relative to root of overlay
          (required to be unique) or just the basename, depending on
          ``match_basename``.

        * The pattern returned is the pattern that whose match gave
          rise to the "matched path" key.

        * The full qualified name is the filename that was mattched by
          the pattern.
        """
        if isinstance(patterns, basestring):
            patterns = [patterns]
        result = {}
        # iterate from bottom and up, so that newer matches overwrites older ones in dict
        for overlay in self.search_dirs[::-1]:
            basedir = self.checkouts_manager.resolve(overlay)
            for p in patterns:
                for match in glob.glob(pjoin(basedir, p)):
                    assert match.startswith(basedir)
                    if match_basename:
                        match_relname = os.path.basename(match)
                    else:
                        match_relname = match[len(basedir) + 1:]
                    result[match_relname] = (p, match)
        return result


def load_and_inherit_profile(checkouts, include_doc, cwd=None, override_parameters=None):
    """
    Loads a Profile given an include document fragment, e.g.::

        file: ../foo/profile.yaml

    or::

        file: linux/profile.yaml
        urls: [git://github.com/hashdist/hashstack.git]
        key: git:5aeba2c06ed1458ae4dc5d2c56bcf7092827347e

    The load happens recursively, including fetching any remote
    dependencies, and merging the result into this document.

    `cwd` is where to interpret `file` in `include_doc` relative to
    (if it is not in a temporary checked out source).  It can use the
    format of TemporarySourceCheckouts, ``<repo_name>/some/path``.
    """
    if cwd is None:
        cwd = os.getcwd()

    def resolve_profile(cwd, p):
        split_url = urlsplit(p)
        if split_url.scheme != '':
            base_name = posixpath.basename(split_url.path)
            urlretrieve(p, base_name)
            p = pjoin(cwd, base_name)
        elif not os.path.isabs(p):
            p = pjoin(cwd, p)
        return p

    def resolve_path(profile_file):
        return os.path.dirname(profile_file)

    if isinstance(include_doc, str):
        include_doc = {'file': include_doc}

    if 'key' in include_doc:
        # This profile is included through a source cache
        # reference/"git import".  We check out sources to a temporary
        # directory and set the repo name expansion pattern as `cwd`.
        # (The purpose of this is to give understandable error
        # messages.)
        checkouts.checkout(include_doc['name'], include_doc['key'], include_doc['urls'])
        cwd = '<%s>' % include_doc['name']

    profile_file = resolve_profile(cwd, include_doc['file'])
    new_cwd = resolve_path(profile_file)

    doc = load_yaml_from_file(checkouts.resolve(profile_file))
    if doc is None:
        doc = {}

    if 'extends' in doc:
        parents = [load_and_inherit_profile(checkouts, parent_include_doc, cwd=new_cwd)
                   for parent_include_doc in doc['extends']]
        del doc['extends']
    else:
        parents = []

    for section in ['package_dirs', 'hook_import_dirs']:
        lst = doc.get(section, [])
        doc[section] = [resolve_profile(new_cwd, p) for p in lst]

    # Merge package_dirs, hook_import_dirs with those of parents
    for section in ['package_dirs', 'hook_import_dirs']:
        for parent_doc in parents:
            doc[section].extend(parent_doc.get(section, []))

    # Merge parameters. Can't have the same parameter from more than one parent
    # *unless* it's overridden by this document or command line, in which case it's OK.

    if override_parameters is not None:
        doc.setdefault('parameters', {}).update(override_parameters)
    parameters = doc.setdefault('parameters', {})

    overridden = parameters.keys()
    for parent_doc in parents:
        for k, v in parent_doc.get('parameters', {}).iteritems():
            if k not in overridden:
                if k in parameters:
                    raise ProfileError(doc, 'two base profiles set same parameter %s, please set it '
                                       'explicitly in descendant profile')
                parameters[k] = v

    # Merge packages section
    packages = {}
    for parent_doc in parents:
        for pkgname, settings in parent_doc.get('packages', {}).iteritems():
            packages.setdefault(pkgname, {}).update(settings)

    for pkgname, settings in doc.get('packages', {}).iteritems():
        if is_null(settings):
            settings = {}
        packages.setdefault(pkgname, {}).update(settings)

    for pkgname, settings in list(packages.items()):  # copy to avoid changes during iteration
        if settings.get('skip', False):
            del packages[pkgname]

    doc['packages'] = packages
    return doc

def load_profile(logger, checkout_manager, profile_file, override_parameters=None):
    doc = load_and_inherit_profile(checkout_manager, profile_file, None, override_parameters)
    return Profile(logger, doc, checkout_manager)
