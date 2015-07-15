"""
:mod:`hashdist.core.build_store` --- Build artifact store
=========================================================

Principles
----------

The build store is the very core of HashDist: Producing build artifacts
identified by hash-IDs. It's important to have a clear picture of just
what the build store is responsible for and not.

Nix takes a pure approach where an artifact hash is guaranteed to
identify the resulting binaries (up to anything inherently random in
the build process, like garbage left by compilers). In contrast,
HashDist takes a much more lenient approach where the strictness is
configurable. The primary goal of HashDist is to make life simpler
by reliably triggering rebuilds when software components are updated,
not total control of the environment (in which case Nix is likely
the better option).

The *only* concern of the build store is managing the result of a
build.  So the declared dependencies in the build-spec are not the
same as "package dependencies" found in higher-level distributions;
for instance, if a pure Python package has a NumPy dependency, this
should not be declared in the build-spec because NumPy is not needed
during the build; indeed, the installation can happen in
parallel.

Artifact IDs
------------

A HashDist artifact ID has the form ``name/hash``, e.g.,
``zlib/4niostz3iktlg67najtxuwwgss5vl6k4``.

For the artifact paths on disk, a shortened form (4-char hash) is used
to make things more friendly to the human user. If there is a
collision, the length is simply increased for the one that comes
later. Thus, the example above could be stored on disk as
``~/.hit/opt/zlib/4nio``, or ``~/.hit/opt/zlib/1.2.7/4nios``
in the (rather unlikely) case of a collision. There is a symlink
from the full ID to the shortened form. See also Discussion below.

Build specifications and inferring artifact IDs
-----------------------------------------------

The fundamental object of the build store is the JSON build
specification.  If you know the build spec, you know the artifact ID,
since the latter is the hash of the former. The key is that both
`dependencies` and `sources` are specified in terms of their hashes.

An example build spec:

.. code-block:: python

    {
        "name" : "<name of piece of software>",
        "description": "<what makes this build special>",
        "build": {
            "import" : [
                 {"ref": "bash", "id": "virtual:bash"},
                 {"ref": "make", "id": "virtual:gnu-make/3+"},
                 {"ref": "zlib", "id": "zlib/1.2.7/fXHu+8dcqmREfXaz+ixMkh2LQbvIKlHf+rtl5HEfgmU"},
                 {"ref": "unix", "id": "virtual:unix"},
                 {"ref": "gcc", "id": "gcc/host-4.6.3/q0VSL7JmzH1P17meqITYc4kMbnIjIexrWPdlAlqPn3s", "before": ["virtual:unix"]},
             ],
             "commands" : [
                 {"cmd": ["bash", "build.sh"]}
             ],
         },
         "sources" : [
             {"key": "git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3"},
             {"key": "tar.bz2:RB1JbykVljxdvL07mN60y9V9BVCruWRky2FpK2QCCow", "target": "sources"},
             {"key": "files:5fcANXHsmjPpukSffBZF913JEnMwzcCoysn-RZEX7cM"}
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

**sources**:
    Sources are unpacked; documentation for now in 'hit unpack-sources'

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
stdout and stderr are redirected to ``$BUILD/_hashdist/build.log``. These two
files will also be present in ``$ARTIFACT`` after the build.

Build artifact storage format
-----------------------------

The presence of the 'id' file signals that the build is complete, and
contains the full 256-bit hash.

More TODO.


Reference
---------



"""



import os
from os.path import join as pjoin
import shutil
import sys
import re
import errno
import json
import base64

from .source_cache import SourceCache
from .hasher import hash_document, prune_nohash
from .common import (InvalidBuildSpecError, BuildFailedError,
                     IllegalBuildStoreError,
                     json_formatting_options, SHORT_ARTIFACT_ID_LEN,
                     working_directory)
from .fileutils import silent_unlink, robust_rmtree, silent_makedirs, gzip_compress, write_protect
from .fileutils import rmtree_write_protected, atomic_symlink, realpath_to_symlink, allow_writes
from . import run_job

from hashdist.util.logger_setup import log_to_file, getLogger


class BuildSpec(object):
    """Wraps the document corresponding to a build.json

    The document is wrapped in order to a) signal that is has been
    canonicalized, b) make the artifact id available under the
    artifact_id attribute.
    """

    def __init__(self, build_spec):
        self.doc = canonicalize_build_spec(build_spec)
        self.name = self.doc['name']
        digest = hash_document('build-spec', prune_nohash(self.doc))
        self.digest = digest
        self.artifact_id = '%s/%s' % (self.name, digest)
        self.short_artifact_id = '%s/%s' % (self.name, digest[:SHORT_ARTIFACT_ID_LEN])

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
    assert_safe_name(result.get('version', 'n'))
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

    Parameters
    ----------

    temp_build_dir : str
        Directory to use for temporary builds (these may be removed or linger
        depending on `keep_build` passed to :meth:`ensure_present`).

    artifact_root : str
        Root of artifacts, this will be prepended to artifact_path_pattern
        with `os.path.join`. While this could be part of `artifact_path_pattern`,
        the meaning is that garbage collection will never remove contents
        outside of this directory.

    gc_roots_dir : str
        Directory of symlinks to symlinks to artifacts. Artifacts reached
        through these will not be collected in garbage collection.

    logger : Logger
    """


    def __init__(self, temp_build_dir, artifact_root, gc_roots_dir, logger, create_dirs=False):
        self.temp_build_dir = os.path.realpath(temp_build_dir)
        self.artifact_root = os.path.realpath(artifact_root)
        self.gc_roots_dir = gc_roots_dir
        self.logger = logger
        if create_dirs:
            for d in [self.temp_build_dir, self.artifact_root]:
                silent_makedirs(d)

    def _log_artifact_collision(self, path, artifact_id):
        d = dict(path=path, artifact_id=artifact_id)
        self.logger.error("""\
            The target directory already exists: %(path)s. This may be
            because of an earlier sudden crash, or because somebody else is
            currently performing the build on a shared
            filesystem. If you are sure the latter is not the case,
            you may run the following to fix the situation:""" % d)
        self.logger.error('')
        self.logger.error('    hit purge %(artifact_id)s' % d)
        self.logger.error('')

    @staticmethod
    def create_from_config(config, logger, **kw):
        """Creates a SourceCache from the settings in the configuration
        """
        if len(config['build_stores']) != 1:
            logger.error("Only a single build store currently supported")
            raise NotImplementedError()

        return BuildStore(config['build_temp'],
                          config['build_stores'][0]['dir'],
                          config['gc_roots'],
                          logger,
                          **kw)

    def get_build_dir(self):
        return self.temp_build_dir

    def is_path_in_build_store(self, d):
        return os.path.realpath(d).startswith(self.artifact_root)

    def delete_all(self):
        for x in os.listdir(self.artifact_root):
            rmtree_write_protected(pjoin(self.artifact_root, x))

    def delete(self, artifact_id):
        """Deletes an artifact ID from the store. This is simply an
        `rmtree`, i.e., it is (at least currently) possible to delete
        an aborted build, a build in progress etc., as long as it is
        present in the right path.

        This is the backend of the ``hit purge`` command.

        Returns the path that was removed, or `None` if no path was present.
        """
        name, digest = artifact_id.split('/')
        path = self._get_artifact_path(name, digest)
        if os.path.exists(path):
            rmtree_write_protected(path)
            return path
        else:
            return None

    def _get_artifact_path(self, name, digest):
        return pjoin(self.artifact_root, name, digest[:SHORT_ARTIFACT_ID_LEN])

    def resolve(self, artifact_id):
        """Given an artifact_id, resolve the short path for it, or return
        None if the artifact isn't built.
        """
        name, digest = artifact_id.split('/')
        path = self._get_artifact_path(name, digest)
        if not os.path.exists(path):
            return None
        else:
            try:
                f = open(pjoin(path, 'id'))
            except IOError:
                self._log_artifact_collision(path, '%s/%s' % (name, digest[:SHORT_ARTIFACT_ID_LEN]))
                raise IllegalBuildStoreError('can not access file: %s/id' % path)
            with f:
                present_id = f.read().strip()
                if present_id != artifact_id:
                    self.logger.error('WARNING: An artifact with a hash that agrees in the first %d characters ' %
                                      SHORT_ARTIFACT_ID_LEN)
                    self.logger.error('is already installed. The two hashes are:')
                    self.logger.error('')
                    self.logger.error('    %s (already present)' % present_id)
                    self.logger.error('    %s (wants to access/build)' % artifact_id)
                    self.logger.error('')
                    self.logger.error('The odds of this happening due to chance are very low.')
                    self.logger.error('Please get in touch with the HashDist developer mailing list.')
                    raise IllegalBuildStoreError('Hashes collide in first 12 chars: %s and %s' % (present_id, artifact_id))
            return path

    def is_present(self, build_spec):
        build_spec = as_build_spec(build_spec)
        return self.resolve(build_spec.artifact_id) is not None

    def ensure_present(self, build_spec, config, extra_env=None, virtuals=None, keep_build='never',
                       debug=False):
        """
        Builds an artifact (if it is not already present).

        extra_env: dict (optional)
            Extra environment variables to pass to the build environment. These are *NOT* hashed!
        """
        if virtuals is None:
            virtuals = {}
        if extra_env is None:
            extra_env = {}
        if keep_build not in ('never', 'error', 'always'):
            raise ValueError("invalid keep_build value")
        build_spec = as_build_spec(build_spec)
        artifact_dir = self.resolve(build_spec.artifact_id)


        if artifact_dir is None:
            builder = ArtifactBuilder(self, build_spec, extra_env, virtuals, debug=debug)
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
        vars = dict(name=build_spec.doc['name'])
        path = pjoin(self.artifact_root, build_spec.short_artifact_id)
        try:
            os.makedirs(path)
        except OSError, e:
            if e.errno == errno.EEXIST:
                self._log_artifact_collision(path)
            raise
        return path

    def make_build_dir(self, build_spec):
        """Creates a temporary build directory

        Just to get a nicer name than mkdtemp would. The caller is responsible
        for removal.
        """
        name = build_spec.short_artifact_id.replace('/', '-')
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
        robust_rmtree(build_dir, self.logger)

    def prepare_build_dir(self, config, logger, build_spec, target_dir):
        source_cache = SourceCache.create_from_config(config, logger)
        self.serialize_build_spec(build_spec, target_dir)
        unpack_sources(self.logger, source_cache, build_spec.doc.get('sources', []), target_dir)

    def serialize_build_spec(self, build_spec, target_dir):
        fname = pjoin(target_dir, 'build.json')
        with allow_writes(target_dir):
            with file(fname, 'w') as f:
                json.dump(build_spec.doc, f, **json_formatting_options)
                f.write('\n')
        write_protect(fname)

    def _encode_symlink(self, symlink):
        """Format of HashDist-managed entries in gc_roots directory; an underscore + base64"""
        return '_' + base64.b64encode(symlink).replace('=', '-')

    def create_symlink_to_artifact(self, artifact_id, symlink_target):
        """Creates a symlink to an artifact (usually a 'profile')

        The symlink can be placed anywhere the users wants to access it. In addition
        to the symlink being created, it is listed in gc_roots.

        The symlink will be created atomically, any target
        file/symlink will be overwritten.
        """
        # We use base64-encoding of realpath_to_symlink(symlink_target) as the name of the link within gc_roots
        symlink_target = realpath_to_symlink(symlink_target)
        artifact_dir = self.resolve(artifact_id)
        atomic_symlink(artifact_dir, symlink_target)
        root_name = self._encode_symlink(symlink_target)
        atomic_symlink(symlink_target, pjoin(self.gc_roots_dir, root_name))

    def remove_symlink_to_artifact(self, symlink_target):
        symlink_target = realpath_to_symlink(symlink_target)
        root_name = self._encode_symlink(symlink_target)
        silent_unlink(pjoin(self.gc_roots_dir, root_name))
        silent_unlink(symlink_target)

    def gc(self):
        """Run garbage collection, removing any unneeded artifacts.

        For now, this doesn't care about virtual dependencies. They're not
        used at the moment of writing this; it would have to be revisited
        in the future.
        """
        # mark phase
        marked = set()
        for gc_root in os.listdir(self.gc_roots_dir):
            try:
                f = open(pjoin(self.gc_roots_dir, gc_root, 'artifact.json'))
            except IOError as e:
                if e.errno == errno.ENOENT:
                    self.logger.warning("GC root link does not lead to artifact, removing: %s" % gc_root)
                    silent_unlink(pjoin(self.gc_roots_dir, gc_root))
                else:
                    raise
            else:
                with f:
                    doc = json.load(f)
                marked.add(doc['id'])
                marked.update(doc['dependencies'])
        # Less confusing output if we first output all keep, then the removals
        for artifact_id in marked:
            if not artifact_id.startswith('virtual:'):
                self.logger.info('Keeping %s' % shorten_artifact_id(artifact_id))
        # sweep phase
        for artifact_name in os.listdir(self.artifact_root):
            for short_digest in os.listdir(pjoin(self.artifact_root, artifact_name)):
                artifact_dir = pjoin(self.artifact_root, artifact_name, short_digest)
                artifact_id_file = pjoin(artifact_dir, 'id')
                with open(artifact_id_file) as f:
                    artifact_id = f.read().strip()
                if artifact_id not in marked:
                    # make sure 'id' is removed first, to de-mark the artifact as valid
                    # before we go ahead and remove it
                    self.logger.info('Removing %s' % shorten_artifact_id(artifact_id))
                    os.chmod(artifact_dir, 0o777)
                    os.unlink(artifact_id_file)
                    rmtree_write_protected(artifact_dir)


class ArtifactBuilder(object):
    def __init__(self, build_store, build_spec, extra_env, virtuals, debug):
        self.build_store = build_store
        self.logger = getLogger('package', build_spec.doc['name'])
        self.build_spec = build_spec
        self.artifact_id = build_spec.artifact_id
        self.virtuals = virtuals
        self.extra_env = extra_env
        self.debug = debug

    def find_complete_dependencies(self):
        """Return set of complete dependencies of the build spec

        The purpose of this list is for garbage collection (currently we
        just include everything, we could be more nuanced in the future).

        We simply iterate through all the build imports, load their artifact.json,
        and return the combined result. This will in turn be stored in artifact.json
        for this build artifact.

        virtual dependencies are not searched for further child dependencies,
        but just included directly
        """
        build_imports = [entry['id'] for entry in self.build_spec.doc.get('build', {}).get('import', [])]
        deps = set()
        for artifact_id in build_imports:
            deps.add(artifact_id)
            if not artifact_id.startswith('virtual:'):
                artifact_dir = self.build_store.resolve(artifact_id)
                if artifact_dir is None:
                    msg = 'Required artifact not already present: %s' % artifact_id
                    self.logger.error(msg)
                    raise BuildFailedError(msg, None, None)
                with open(pjoin(artifact_dir, 'artifact.json')) as f:
                    doc = json.load(f)
                deps.update(doc.get('dependencies', []))
        return deps

    def build(self, config, keep_build):
        assert isinstance(config, dict), "caller not refactored"
        artifact_dir = self.build_store.make_artifact_dir(self.build_spec)
        try:
            self.make_artifact_json(artifact_dir)
            self.build_to(artifact_dir, config, keep_build)
        except:
            rmtree_write_protected(artifact_dir)
            raise
        return artifact_dir

    def build_to(self, artifact_dir, config, keep_build):
        if keep_build not in ('never', 'always', 'error'):
            raise ValueError("keep_build not in ('never', 'always', 'error')")

        build_dir = self.build_store.make_build_dir(self.build_spec)

        should_keep = False # failures in init are bugs in hashdist itself, no need to keep dir
        try:
            env = dict(self.extra_env)
            env['BUILD'] = build_dir

            should_keep = (keep_build == 'always')
            try:
                self.run_build_commands(build_dir, artifact_dir, env, config)
                self.build_store.serialize_build_spec(self.build_spec, artifact_dir)

                # Create 'id' marker for finished build by writing to _id and then mv to id
                with allow_writes(artifact_dir):
                    with open(pjoin(artifact_dir, '_id'), 'w') as f:
                        f.write('%s\n' % self.build_spec.artifact_id)
                    os.rename(pjoin(artifact_dir, '_id'), pjoin(artifact_dir, 'id'))
            except:
                should_keep = (keep_build in ('always', 'error'))
                raise
        finally:
            if build_dir != artifact_dir and not should_keep:
                self.build_store.remove_build_dir(build_dir)


    def build_out(self, artifact_dir, config):
        """Builds an artifact outside of the BuildStore"""

        build_dir = artifact_dir

        env = dict(self.extra_env)
        env['BUILD'] = build_dir
        self.run_build_commands(build_dir, artifact_dir, env, config)
        self.make_artifact_json(artifact_dir)

        # Create 'id' marker for finished build by writing to _id and then mv to id
        with open(pjoin(artifact_dir, '_id'), 'w') as f:
            f.write('%s\n' % self.build_spec.artifact_id)
        os.rename(pjoin(artifact_dir, '_id'), pjoin(artifact_dir, 'id'))


    def make_artifact_json(self, artifact_dir):
        deps = self.find_complete_dependencies()
        fname = pjoin(artifact_dir, 'artifact.json')
        doc = self.build_spec.doc
        artifact_doc = {'name': doc['name'], 'dependencies': sorted(list(deps)),
                        'id': self.build_spec.artifact_id}
        if 'version' in doc:
            artifact_doc['version'] = doc['version']
        with open(fname, 'w') as f:
            json.dump(artifact_doc, f, **json_formatting_options)

    def run_build_commands(self, build_dir, artifact_dir, env, config):
        job_tmp_dir = pjoin(build_dir, 'job')
        os.mkdir(job_tmp_dir)
        job_spec = self.build_spec.doc['build']

        os.mkdir(pjoin(build_dir, '_hashdist'))
        log_filename = pjoin(build_dir, '_hashdist', 'build.log')
        self.logger.warning('Building %s, follow log with:' % self.build_spec.short_artifact_id)
        self.logger.warning('  tail -f %s' % log_filename)
        self.logger.debug('Start log output to file %s', log_filename)
        with log_to_file('package', log_filename):
            self.build_store.prepare_build_dir(config, self.logger, self.build_spec, build_dir)

            try:
                run_job.run_job(self.logger, self.build_store, job_spec,
                                env, artifact_dir, self.virtuals, cwd=build_dir, config=config,
                                temp_dir=job_tmp_dir, debug=self.debug)
            except:
                exc_type, exc_value, exc_tb = sys.exc_info()
                # Python 2 'wrapped exception': We raise an exception with the same traceback
                # but changing the type, and embedding the original type name in the message
                # string. This is primarily done in order to communicate the build_dir to
                # the caller
                raise BuildFailedError("%s: %s" % (exc_type.__name__, exc_value), build_dir,
                                       (exc_type, exc_value, exc_tb)), None, exc_tb
        self.logger.debug('Stop log output to file %s', log_filename)
        log_gz_filename = pjoin(artifact_dir, 'build.log.gz')
        with allow_writes(artifact_dir):
            gzip_compress(log_filename, log_gz_filename)
        write_protect(log_gz_filename)

def unpack_sources(logger, source_cache, doc, target_dir):
    """
    Executes source unpacking from 'sources' section in build.json
    """
    for source_item in doc:
        key = source_item['key']
        target = pjoin(target_dir, source_item.get('target', '.'))
        logger.debug('Unpacking sources %s' % key)
        source_cache.unpack(key, target)
