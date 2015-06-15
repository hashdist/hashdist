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

from ..formats.marked_yaml import load_yaml_from_file, is_null, marked_yaml_load, raw_tree
from ..formats import marked_yaml
from . import spec_ast
from .utils import substitute_profile_parameters
from .. import core
from .exceptions import ProfileError, PackageError


class _optional_package(object):
    """
    Marker object
    """
    def __init__(self, name):
        self.name = name


class Profile(object):
    """
    Profiles acts as nodes in a tree, with `extends` containing the
    parent profiles (which are child nodes in a DAG).
    """
    def __init__(self, logger, doc, checkouts_manager):
        self.logger = logger
        self.doc = doc
        self.file_resolver = FileResolver(checkouts_manager, doc.get('package_dirs', []))
        self.checkouts_manager = checkouts_manager
        self.hook_import_dirs = doc.get('hook_import_dirs', [])
        self._yaml_cache = {} # (filename: [list of documents, possibly with when-clauses])
        # Load parameters, when-transforming them individually
        self.parameters = {}
        for param_name, param_node in doc.get('parameters', {}).items():
            self.parameters[param_name] = spec_ast.when_transform_yaml(param_node)
        # Load package arguments, when-transforming them individually
        self.packages = {}
        for pkg_name, pkg_node in doc.get('packages', {}).items():
            pkg_params = marked_yaml.dict_like(pkg_node)
            for param_name, param_value in pkg_node.items():
                pkg_params[param_name] = spec_ast.when_transform_yaml(param_value)
            self.packages[pkg_name] = pkg_params


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

    def load_package(self, pkgname):
        """
        Search for the yaml sources and load them, resulting in an 'abstract
        package' (Package instance).

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

        In case of many matches:

        - The ``parameters`` section can only be present in the basename
          file, i.e., in ``pkgname.yaml``. This must declare any parameters
          required of any versions of the package.

        - The returned Package will pick the appropriate one to use
          during Package.instantiate, when parameters are available,
          going by the when clause.

        Parameters
        ----------

        pkgname : string
            Name of the package (excluding ``.yaml``).

        Returns
        -------

        A :class:`~hashdist.spec.package.Package` instance if successfull,
        which references ~hashdist.spec.package.PackageYAML instances with
        the package contents.

        Raises
        ------

        * class:`~hashdist.spec.exceptions.ProfileError`` is raised if
          there is no such package.

        * class:`~hashdist.spec.exceptions.PackageError`` is raised if
          a package conflicts with a previous one.
        """
        assert isinstance(pkgname, basestring)
        from .package import Package, PackageYAML

        use = self._use_for_package(pkgname)
        assert use == pkgname  # TODO must deprecate _use_for_package..
        yaml_files = self._yaml_cache.get(('package', use), None)
        if yaml_files is None:
            yaml_filename = use + '.yaml'
            matches = self.file_resolver.glob_files([yaml_filename,
                                                     pjoin(use, yaml_filename),
                                                     pjoin(use, use + '-*.yaml')],
                                                    match_basename=True)
            self._yaml_cache['package', use] = yaml_files = [
                PackageYAML(use, filename,
                            primary=os.path.basename(filename) == yaml_filename,
                            in_directory=(pattern != yaml_filename))
                for match, (pattern, filename) in matches.items()]
            self.logger.info('Resolved package %s to %s', pkgname,
                             [filename for match, (pattern, filename) in matches.items()])

        if len(yaml_files) == 0:
            raise ProfileError(use, 'No yaml file for package "{0}" found'.format(use))
        return Package.create_from_yaml_files(self, yaml_files)

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

    def apply_parameter_rules(self, package_params):
        """
        Insert the extra parameters `package_params` (typically per-package)
        and evaluate the ruleset specified in `self.parameters`. Returns
        the computed parameters.
        """
        # Refer to the parameter declarations in the YAML as 'rules'
        rules = dict(self.parameters)
        rules.update(package_params)
        visiting = set()
        result = {}

        def visit(param_name):
            if param_name in visiting:
                raise ProfileError(pkgname, 'dependency cycle between parameters, '
                                   'including parameter "%s"' % param_name)
            if param_name in result:
                return result[param_name]
            visiting.add(param_name)
            rule = rules[param_name]
            # Ensure all referenced parameters are in `result`.
            referenced = {}
            for ref in rule.references:
                referenced[ref] = visit(ref)
            x = result[param_name] = spec_ast.evaluate_doc(rule, referenced)
            visiting.remove(param_name)
            return x

        for param_name in rules.keys():
            visit(param_name)
        return result


    def resolve_parameters(self):
        """
        Figures out the explicit parameters to pass to each Package. The result
        is a dict of { name : PackageInstance }, where "name" is the name used
        in the profile of the package.

        This method automatically calls self.apply_parameter_rules for each
        package.
        """
        result = {}  # {name : (package spec, dict of parameters to pass)}
        visiting = set()

        def visit(pkgname):
            assert isinstance(pkgname, basestring)
            pkgname = str(pkgname)
            if pkgname in visiting:
                raise ProfileError(pkgname, 'dependency cycle between packages, '
                                   'including package "%s"' % pkgname)
            if pkgname in result:
                return result[pkgname]
            # Get the declaration in profile. This does not always exist, in which case
            # an empty dict represents the defaults.
            param_doc = self.packages.get(pkgname, {})
            if 'use' in param_doc:
                if len(param_doc) != 1:
                    raise ProfileError(param_doc, 'If "use:" is provided, no other parameters should be provided')
                pkgname = spec_ast.evaluate_doc(param_doc['use'], {})
                return visit(pkgname)

            visiting.add(pkgname)

            pkg_spec = self.load_package(pkgname)

            # Inherit defaults and do any expression processing. Note that this is
            # *after* checking that no extra parameters were provided..so it contains
            # extra parameters, we'll pull out the ones wanted below
            param_doc = self.apply_parameter_rules(param_doc)

            # Step 1: Produce param_values, which is the full set of parameters for the package. In essence this
            # is param_doc from the profile + default values + replace names of packages with Package instances.
            #
            # NOTE: For now, we do not resolve any optional dependencies. This is left to a second pass, because
            # we want all hard dependencies to be resolved first, then include whatever was pulled in in that pass
            # (globally) to be picked up for the optional dependencies.
            param_values = {}
            for param in pkg_spec.parameters.values():
                if param.name == 'package':
                    # Magic parameter
                    param_values['package'] = pkg_spec.name
                elif param.has_package_type():
                    dep_name = param.name
                    if dep_name.startswith('_run_'):
                        dep_name = dep_name[len('_run_'):]
                    dep_pkg = None  # if left None in the end, it is optional and we don't provide id

                    # Do some very basic matching on constraints; this is only likely to match our
                    # own auto-generate constraint, though it doesn't hurt if it matches user-provided
                    # constraints
                    required = ('%s is not None' % spec_ast.preprocess_package_name(param.name)
                                in [c.expr for c in pkg_spec.constraints])
                    if required or dep_name in param_values or dep_name in param_doc:
                        value = param_doc.get(dep_name, None) or dep_name  # take into account null as value
                        dep_pkg = visit(value)
                    else:
                        # Optional and not explicitly provided. Solve this in second pass
                        dep_pkg = _optional_package(dep_name)
                    param_values[param.name] = dep_pkg
                elif param.name in param_doc:
                    # Use explicitly specified parameter (either passed to package, or from parameters: section in prof)
                    param_values[param.name] = raw_tree(param_doc[param.name])
                else:
                    # Use default value. If it is a required parameter, then default will
                    # be None and there will be a constraint that it is not None that will
                    # fail later.
                    param_values[param.name] = param.default

            # Step 2: Type-check and remove parameters that are not declared
            # (also according to when-conditions)
            x = result[pkgname] = pkg_spec.pre_instantiate(param_values)
            visiting.remove(pkgname)
            return x

        # Pass 1: Resolve defaults and hard dependencies
        for pkgname, args in self.packages.items():
            visit(pkgname)

        # Pass 2: Fill in any optional dependencies (potentially causing cyclic references
        #         which is OK) and call init() on packages

        for pkg_name, pkg in result.items():
            for param_name, param_value in pkg._param_values.items():
                if isinstance(param_value, _optional_package):
                    pkg._param_values[param_name] = result.get(param_value.name, None)
            pkg._param_values = pkg._spec.typecheck_parameter_set(pkg._param_values, node=None)

        # Pass 3: Call pkg.init() which check constraints and initializes
        for pkg in result.values():
            pkg.init()

        return result


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
    node = doc.get('packages', doc)
    packages = marked_yaml.dict_node({}, node.start_mark, node.end_mark)
    for parent_doc in parents:
        for pkgname, settings in parent_doc.get('packages', {}).iteritems():
            packages.setdefault(pkgname, marked_yaml.dict_node({}, None, None)).update(settings)

    for pkgname, settings in doc.get('packages', {}).iteritems():
        if is_null(settings):
            settings = {}
        packages.setdefault(pkgname, marked_yaml.dict_node({}, None, None)).update(settings)

    for pkgname, settings in list(packages.items()):  # copy to avoid changes during iteration
        if settings.get('skip', False):
            del packages[pkgname]

    doc['packages'] = packages
    return doc

def load_profile(logger, checkout_manager, profile_file, override_parameters=None):
    doc = load_and_inherit_profile(checkout_manager, profile_file, None, override_parameters)
    return Profile(logger, doc, checkout_manager)
