"""
:mod:`hashdist.core.build_store` --- Build artifact store
=========================================================

Principles
----------

The build store is the very core of Hashdist: Producing build artifacts
identified by hash-IDs. It's important to have a clear picture of just
what the build store is responsible for and not.

Nix takes a pure approach where an artifact hash is guaranteed to
identify the resulting binaries (up to anything inherently random in
the build process, like garbage left by compilers). In contrast,
Hashdist takes a much more lenient approach where the strictness is
configurable. The primary goal of Hashdist is to make life simpler
by reliably triggering rebuilds when software components are updated,
not total control of the environment (in which case Nix is likely
the better option).

The *only* concern of the build store is managing the result of a
build.  So the declared dependencies in the build-spec are not the
same as "package dependencies" found in higher-level distributions;
for instance, if a pure Python package has a NumPy dependency, this
should not be declared in the build-spec because NumPy is not needed
during the build; indeed, the installation can happen in
parallel. Assembing artifacts together in a usable run-time system is
the job of :mod:`hashdist.core.profile`.


Artifact IDs
------------

A Hashdist artifact ID has the form ``name/hash``, e.g.,
``zlib/4niostz3iktlg67najtxuwwgss5vl6k4``.

For the artifact paths on disk, a shortened form (4-char hash) is used
to make things more friendly to the human user. If there is a
collision, the length is simply increased for the one that comes
later. Thus, the example above could be stored on disk as
``~/.hdist/opt/zlib/4nio``, or ``~/.hdist/opt/zlib/1.2.7/4nios``
in the (rather unlikely) case of a collision. There is a symlink
from the full ID to the shortened form. See also Discussion below.

Build specifications and inferring artifact IDs
-----------------------------------------------

The fundamental object of the build store is the JSON build
specification.  If you know the build spec, you know the artifact ID,
since the former is the hash of the latter. The key is that both
`dependencies` and `sources` are specified in terms of their hashes.

An example build spec:

.. code-block:: python
    
    {
        "name" : "<name of piece of software>",
        "version" : "<version>",
        "description": "<what makes this build special>",
        "build": {
            "import" : [
                 {"ref": "bash", "id": "virtual:bash"},
                 {"ref": "make", "id": "virtual:gnu-make/3+"},
                 {"ref": "zlib", "id": "zlib/1.2.7/fXHu+8dcqmREfXaz+ixMkh2LQbvIKlHf+rtl5HEfgmU"},
                 {"ref": "unix", "id": "virtual:unix"},
                 {"ref": "gcc", "id": "gcc/host-4.6.3/q0VSL7JmzH1P17meqITYc4kMbnIjIexrWPdlAlqPn3s", "before": ["virtual:unix"]},
             ],
             "script" : [
                 ["hdist", "build-unpack-sources"],
                 ["hdist", "build-write-files"],
                 ["bash", "build.sh"]
             ],
         },
         "sources" : [
             {"key": "git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3"},
             {"key": "tar.bz2:RB1JbykVljxdvL07mN60y9V9BVCruWRky2FpK2QCCow", "target": "sources", "strip": 1},
             {"key": "files:5fcANXHsmjPpukSffBZF913JEnMwzcCoysn-RZEX7cM"}
         ],
         "files" : [
             { "target": "build.sh",
               "text": [
                 "set -e",
                 "./configure --prefix=\\"${ARTIFACT}\\"",
                 "make",
                 "make install"
               ]
             }
         ],
    }


**name**:
    Should match ``[a-zA-Z0-9-_+]+``.

**version**:
    Should match ``[a-zA-Z0-9-_+]*``.

..
    **description**:
    What makes this build special in some human-readable form, e.g.,
    ``icc-avx-gotoblas`` (this may be part of the pathname on some
    platforms). Should match ``[a-zA-Z0-9-_+]*``.

**build**:
    A job to run to perform the build. See :mod:`hashdist.core.run_job`
    for the documentation of this sub-document.

In addition, extra keys can be added at will to use for input to
commands executed in the build. In the example above, the `sources`
key is read by the ``hdist build-unpack-sources`` command.

The build environment
---------------------

See :mod:`hashdist.core.execute_job` for information about how the
build job is executed. In addition, the following environment variables
are set:

**BUILD**:
    Set to the build directory. This is also the starting `cwd` of
    each build command. This directory may be removed after the build.

**ARTIFACT**:
    The location of the final artifact. Usually this is the "install location"
    and should, e.g., be passed as the ``--prefix`` to ``./configure``-style
    scripts.

The build specification is available under ``$BUILD/build.json``, and
stdout and stderr are redirected to ``$BUILD/build.log``. These two
files will also be present in ``$ARTIFACT`` after the build.


Discussion
----------

Safety of the shortened IDs
'''''''''''''''''''''''''''

Hashdist will never use these to resolve build artifacts, so collision
problems come in two forms:

First, automatically finding the list of run-time dependencies from
the build dependencies. In this case one scans the artifact directory
only for the build dependencies (less than hundred). It then makes
sense to consider the chance of finding one exact string
``aaa/0.0/ZXa3`` in a random stream of 8-bit bytes, which helps
collision strength a lot, with chance "per byte" of
collision on the order :math:`2^{-(8 \cdot 12)}=2^{-96}`
for this minimal example.

If this is deemed a problem (the above is too optimistice), one can
also scan for "duplicates" (other artifacts where longer hashes
were chosen, since we know these).

The other problem can be future support for binary distribution of
build artifacts, where you get pre-built artifacts which have links to
other artifacts embedded, and artifacts from multiple sources may
collide. In this case it makes sense to increase the hash lengths a
bit since the birthday effect comes into play and since one only has 6
bits per byte. However, the downloaded builds presumably will contain
the full IDs, and so on can check if there is a conflict and give an
explicit error.


Reference
---------

.. automodule:: hashdist.core.build_store.build_store
    :members:

.. automodule:: hashdist.core.build_store.build_spec
    :members:

.. automodule:: hashdist.core.build_store.builder
    :members:


"""



import os
from os.path import join as pjoin
import shutil
import sys
import re
import errno
import json
from logging import DEBUG

from .hasher import Hasher
from .common import (InvalidBuildSpecError, BuildFailedError,
                     json_formatting_options, SHORT_ARTIFACT_ID_LEN,
                     working_directory)
from .fileutils import silent_unlink, rmtree_up_to, silent_makedirs, gzip_compress, write_protect
from . import run_job



class BuildSpec(object):
    """Wraps the document corresponding to a build.json

    The document is wrapped in order to a) signal that is has been
    canonicalized, b) make the artifact id available under the
    artifact_id attribute.
    """

    def __init__(self, build_spec):
        self.doc = canonicalize_build_spec(build_spec)
        self.name = self.doc['name']
        self.version = self.doc['version']
        digest = Hasher(self.doc).format_digest()
        self.digest = digest
        self.artifact_id = '%s/%s' % (self.name, digest)

def as_build_spec(obj):
    if isinstance(obj, BuildSpec):
        return obj
    else:
        return BuildSpec(obj)

def canonicalize_build_spec(spec):
    """Puts the build spec on a canonical form + basic validation

    See module documentation for information on the build specification.

    Parameters
    ----------
    spec : json-like
        The build specification

    Returns
    -------
    canonical_spec : json-like
        Canonicalized and verified build spec
    """
    result = dict(spec) # shallow copy
    assert_safe_name(result['name'])
    assert_safe_name(result['version'])
    result['build'] = run_job.canonicalize_job_spec(result['build'])

    return result

def strip_comments(spec):
    """Strips a build spec (which should be in canonical format) of comments
    that should not affect hash
    """
    raise NotImplementedError("please fix")
    def strip_desc(obj):
        r = dict(obj)
        if 'desc' in r:
            del r['desc']
        return r
    
    result = dict(spec)
    result['dependencies'] = [strip_desc(x) for x in spec['dependencies']]
    return result

_SAFE_NAME_RE = re.compile(r'[a-zA-Z0-9-_+]+')
def assert_safe_name(x):
    """Raises a ValueError if x does not match ``[a-zA-Z0-9-_+]+``.

    Returns `x`
    """
    if not _SAFE_NAME_RE.match(x):
        raise ValueError('version or name "%s" is empty or contains illegal characters' % x)
    return x


def shorten_artifact_id(artifact_id, length=SHORT_ARTIFACT_ID_LEN):
    """Shortens the hash part of the artifact_id to the desired length
    """
    name, digest = artifact_id.split('/')
    return '%s/%s' % (name, digest[:length])


class BuildStore(object):
    """
    Manages the directory of build artifacts; this is usually the entry point
    for kicking off builds as well.

    Arguments for path pattern:

     * name, version: Corresponding fields from build.json.

     * shorthash: Initially first 4 chars of hash; then grows until there is
       no collision. This must currently be present somewhere.

    Currently, the db symlink entries are always relative.

    Parameters
    ----------

    temp_build_dir : str
        Directory to use for temporary builds (these may be removed or linger
        depending on `keep_build` passed to :meth:`ensure_present`).
        
    db_dir : str
        Directory containing symlinks to the artifacts; this is the authoriative
        database of build artifacts, and is always structured as
        ``os.path.join("artifacts", digest[:2], digest[2:])``. `db_dir` should point to
        root of db dir, "artifacts" is always appended.

    artifact_root : str
        Root of artifacts, this will be prepended to artifact_path_pattern
        with `os.path.join`. While this could be part of `artifact_path_pattern`,
        the meaning is that garbage collection will never remove contents
        outside of this directory.

    artifact_path_pattern : str
        A pattern to use to name (new) artifact directories.
        See above for possible template arguments.
        Example: ``{name}-{version}/{shorthash}``

    logger : Logger
    """


    def __init__(self, temp_build_dir, db_dir, artifact_root, artifact_path_pattern, logger,
                 create_dirs=False, short_hash_len=SHORT_ARTIFACT_ID_LEN):
        if not os.path.isdir(db_dir) and not create_dirs:
            raise ValueError('"%s" is not an existing directory' % db_dir)
        if not '{shorthash}' in artifact_path_pattern:
            raise ValueError('artifact_path_pattern must contain at least "{shorthash}"')
        self.temp_build_dir = os.path.realpath(temp_build_dir)
        self.ba_db_dir = pjoin(os.path.realpath(db_dir), "artifacts")
        self.artifact_root = os.path.realpath(artifact_root)
        self.artifact_path_pattern = artifact_path_pattern
        self.logger = logger
        self.short_hash_len = short_hash_len
        if create_dirs:
            for d in [self.temp_build_dir, self.ba_db_dir, self.artifact_root]:
                silent_makedirs(d)

    @staticmethod
    def create_from_config(config, logger, **kw):
        """Creates a SourceCache from the settings in the configuration
        """
        return BuildStore(config['builder/build-temp'],
                          config['global/db'],
                          config['builder/artifacts'],
                          config['builder/artifact-dir-pattern'],
                          logger,
                          **kw)

    def get_build_dir(self):
        return self.temp_build_dir

    def delete_all(self):
        for dirpath, dirnames, filenames in os.walk(self.ba_db_dir):
            for link in filenames:
                link = pjoin(dirpath, link)
                if not os.path.islink(link):
                    self.logger.warning("%s is not a symlink" % link)
                    continue
                artifact_dir = os.path.realpath(pjoin(dirpath, link))
                if not artifact_dir.startswith(self.artifact_root):
                    self.logger.warning("%s escapes %s, doing nothing with it" %
                                        (artifact_dir, self.artifact_root))
                try:
                    shutil.rmtree(artifact_dir)
                except OSError, e:
                    if e.errno != errno.ENOENT:
                        raise
                    else:
                        self.logger.warning("%s referenced in db but does not exist" % artifact_dir)

        for x in os.listdir(self.ba_db_dir):
            shutil.rmtree(pjoin(self.ba_db_dir, x))

        for x in os.listdir(self.temp_build_dir):
            shutil.rmtree(pjoin(self.temp_build_dir, x))

    def _get_artifact_link(self, artifact_id):
        name, digest = artifact_id.split('/')
        return pjoin(self.ba_db_dir, digest[:2], digest[2:])

    def resolve(self, artifact_id):
        """Given an artifact_id, resolve the short path for it, or return
        None if the artifact isn't built.
        """
        link = self._get_artifact_link(artifact_id)
        # automatically heal the link database if an artifact has been manually removed
        try:
            a_dir = os.readlink(link)
        except OSError, e:
            if e.errno == errno.ENOENT:
                a_dir = None
            else:
                raise
        else:
            a_dir = os.path.realpath(pjoin(os.path.dirname(link), a_dir))
            if not os.path.exists(a_dir):
                self.logger.warning('Artifact %s has been manually removed; removing entry' %
                                    artifact_id)
                os.unlink(link)
                a_dir = None
        return a_dir

    def is_present(self, build_spec):
        build_spec = as_build_spec(build_spec)
        return self.resolve(build_spec.artifact_id) is not None

    def ensure_present(self, build_spec, config, virtuals=None, keep_build='never'):
        if virtuals is None:
            virtuals = {}
        if keep_build not in ('never', 'error', 'always'):
            raise ValueError("invalid keep_build value")
        build_spec = as_build_spec(build_spec)
        artifact_dir = self.resolve(build_spec.artifact_id)
        if artifact_dir is None:
            builder = ArtifactBuilder(self, build_spec, virtuals)
            artifact_dir = builder.build(config, keep_build)
        return build_spec.artifact_id, artifact_dir

    def make_artifact_dir(self, build_spec):
        """
        Makes a directory to put the result of the artifact build in.
        This does not register the artifact in the db (which should be done
        after the artifact is complete).
        """
        # try to make shortened dir and symlink to it; incrementally
        # lengthen the name in the case of hash collision
        vars = dict(name=build_spec.doc['name'],
                    version=build_spec.doc['version'])
        root = self.artifact_root
        hashlen = self.short_hash_len
        while True:
            vars['shorthash'] = build_spec.digest[:hashlen]
            name = self.artifact_path_pattern.format(**vars)
            artifact_dir = pjoin(root, name)
            try:
                os.makedirs(artifact_dir)
            except OSError, e:
                if e.errno != errno.EEXIST:
                    raise
            else:
                break
            hashlen += 1
        return artifact_dir

    def register_artifact(self, build_spec, artifact_dir):
        """
        Register an artifact that has been successfully built in the db.

        Upon return, `artifact_dir` is either registered in the db or
        removed (except possibly for malformed input). If the artifact
        is already registered under a different name (a race) then
        that is silently returned (and `artifact_dir` removed).

        Returns the new artifact dir (i.e., the input `artifact_dir` unless
        there is a race).
        """
        link = self._get_artifact_link(build_spec.artifact_id)
        rel_artifact_dir = os.path.relpath(artifact_dir, os.path.dirname(link))
        silent_makedirs(os.path.dirname(link))
        try:
            os.symlink(rel_artifact_dir, link)
        except OSError, e:
            shutil.rmtree(artifact_dir)
            if e.errno == errno.EEXIST:
                return os.path.realpath(link)
            else:
                raise
        else:
            return artifact_dir
                   
    def make_build_dir(self, build_spec):
        """Creates a temporary build directory

        Just to get a nicer name than mkdtemp would. The caller is responsible
        for removal.
        """
        name = '%s-%s-%s' % (build_spec.doc['name'], build_spec.doc['version'],
                             build_spec.digest[:self.short_hash_len])
        build_dir = orig_build_dir = pjoin(self.temp_build_dir, name)
        i = 0
        # Try to make build_dir, if not then increment a -%d suffix until we
        # find a free slot
        while True:
            try:
                os.makedirs(build_dir)
            except OSError, e:
                if e.errno != errno.EEXIST:
                    raise
            else:
                break
            i += 1
            build_dir = '%s-%d' % (orig_build_dir, i)
        self.logger.debug('Created build dir: %s' % build_dir)
        return build_dir
        
    def remove_build_dir(self, build_dir):
        self.logger.debug('Removing build dir: %s' % build_dir)
        shutil.rmtree(build_dir)
 
class ArtifactBuilder(object):
    def __init__(self, build_store, build_spec, virtuals):
        self.build_store = build_store
        self.logger = build_store.logger.get_sub_logger(build_spec.doc['name'])
        self.build_spec = build_spec
        self.artifact_id = build_spec.artifact_id
        self.virtuals = virtuals

    def build(self, config, keep_build):
        assert isinstance(config, dict), "caller not refactored"
        artifact_dir = self.build_store.make_artifact_dir(self.build_spec)
        try:
            self.build_to(artifact_dir, config, keep_build)
        except:
            shutil.rmtree(artifact_dir)
            raise
        artifact_dir = self.build_store.register_artifact(self.build_spec, artifact_dir)
        return artifact_dir

    def build_to(self, artifact_dir, config, keep_build):
        if keep_build not in ('never', 'always', 'error'):
            raise ValueError("keep_build not in ('never', 'always', 'error')")
        build_dir = self.build_store.make_build_dir(self.build_spec)
        should_keep = False # failures in init are bugs in hashdist itself, no need to keep dir
        try:
            env = {}
            env['ARTIFACT'] = artifact_dir
            env['BUILD'] = build_dir
            self.serialize_build_spec(build_dir)

            should_keep = (keep_build == 'always')
            try:
                self.run_build_commands(build_dir, artifact_dir, env, config)
                self.serialize_build_spec(artifact_dir)
            except:
                should_keep = (keep_build in ('always', 'error'))
                raise
        finally:
            if not should_keep:
                self.build_store.remove_build_dir(build_dir)
        return artifact_dir

    def serialize_build_spec(self, d):
        fname = pjoin(d, 'build.json')
        with file(fname, 'w') as f:
            json.dump(self.build_spec.doc, f, **json_formatting_options)
            f.write('\n')
        write_protect(fname)

    def run_build_commands(self, build_dir, artifact_dir, env, config):
        artifact_display_name = self.build_spec.digest[:SHORT_ARTIFACT_ID_LEN] + '..'

        job_spec = self.build_spec.doc['build']

        logger = self.logger
        log_filename = pjoin(build_dir, 'build.log')
        with file(log_filename, 'w') as log_file:
            if logger.level > DEBUG:
                logger.info('Building %s, follow log with:' % artifact_display_name)
                logger.info('  tail -f %s' % log_filename)
            else:
                logger.info('Building %s' % artifact_display_name)
            logger.push_stream(log_file, raw=True)
            try:
                run_job.run_job(logger, self.build_store, job_spec,
                                env, self.virtuals, build_dir, config)
            except:
                exc_type, exc_value, exc_tb = sys.exc_info()
                # Python 2 'wrapped exception': We raise an exception with the same traceback
                # but changing the type, and embedding the original type name in the message
                # string. This is primarily done in order to communicate the build_dir to
                # the caller
                raise BuildFailedError("%s: %s" % (exc_type.__name__, exc_value), build_dir), None, exc_tb
            finally:
                logger.pop_stream()
        log_gz_filename = pjoin(artifact_dir, 'build.log.gz')
        gzip_compress(pjoin(build_dir, 'build.log'), log_gz_filename)
        write_protect(log_gz_filename)

