import os
from os.path import join as pjoin
import shutil
import sys
import re
import errno

from .build_spec import as_build_spec
from .builder import ArtifactBuilder

from ..common import SHORT_ARTIFACT_ID_LEN

from ..fileutils import silent_unlink, rmtree_up_to, silent_makedirs

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
                 short_hash_len=SHORT_ARTIFACT_ID_LEN):
        if not os.path.isdir(db_dir):
            raise ValueError('"%s" is not an existing directory' % db_dir)
        if not '{shorthash}' in artifact_path_pattern:
            raise ValueError('artifact_path_pattern must contain at least "{shorthash}"')
        self.temp_build_dir = os.path.realpath(temp_build_dir)
        self.ba_db_dir = pjoin(os.path.realpath(db_dir), "artifacts")
        self.artifact_root = os.path.realpath(artifact_root)
        self.artifact_path_pattern = artifact_path_pattern
        self.logger = logger
        self.short_hash_len = short_hash_len

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

    @staticmethod
    def create_from_config(config, logger):
        """Creates a SourceCache from the settings in the configuration
        """
        return BuildStore(config['builder/build-temp'],
                          config['global/db'],
                          config['builder/artifacts'],
                          config['builder/artifact-dir-pattern'],
                          logger)

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
 
