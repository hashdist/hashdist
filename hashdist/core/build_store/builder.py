"""
Code for setting up environment for performing a build.

Can be considered a private part of .build_store, documentation-wise and test-wise.
"""

from os.path import join as pjoin
import os
import subprocess
import shutil
import json
import errno
import sys
from textwrap import dedent
from string import Template
from pprint import pformat
import gzip

from ..source_cache import scatter_files
from .. import sandbox
from .build_spec import shorten_artifact_id
from ..common import (InvalidBuildSpecError, BuildFailedError,
                      json_formatting_options, SHORT_BUILD_ID_LEN,
                      SHORT_ARTIFACT_ID_LEN, working_directory)

from ...hdist_logging import DEBUG

class ArtifactBuilder(object):
    def __init__(self, build_store, build_spec, virtuals):
        self.build_store = build_store
        self.logger = build_store.logger.get_sub_logger(build_spec.doc['name'])
        self.build_spec = build_spec
        self.artifact_id = build_spec.artifact_id
        self.virtuals = virtuals

    def build(self, source_cache, keep_build):
        artifact_dir, artifact_link = self.make_artifact_dir()
        try:
            self.build_to(artifact_dir, source_cache, keep_build)
        except:
            shutil.rmtree(artifact_dir)
            os.unlink(artifact_link)
            raise
        return artifact_dir

    def build_to(self, artifact_dir, source_cache, keep_build):
        if keep_build not in ('never', 'always', 'error'):
            raise ValueError("keep_build not in ('never', 'always', 'error')")
        env = sandbox.get_artifact_dependencies_env(self.build_store, self.virtuals,
                                                    self.build_spec.doc.get('dependencies', ()))
        env['HDIST_VIRTUALS'] = pack_virtuals_envvar(self.virtuals)

        # Always clean up when these fail regardless of keep_build_policy
        build_dir = self.make_build_dir()
        self.logger.info('Unpacking sources to %s' % build_dir)
        try:
            env['ARTIFACT'] = artifact_dir
            env['BUILD'] = build_dir

            self.serialize_build_spec(build_dir)
            self.unpack_sources(build_dir, source_cache)
            self.unpack_files(build_dir, env)
        except:
            self.remove_build_dir(build_dir)
            raise

        # Conditionally clean up when this fails
        try:
            self.run_build_commands(build_dir, artifact_dir, env)
            self.serialize_build_spec(artifact_dir)
        except:
            if keep_build == 'never':
                self.remove_build_dir(build_dir)
            raise
        # Success
        if keep_build != 'always':
            self.remove_build_dir(build_dir)
        return artifact_dir

    def make_build_dir(self):
        short_id = shorten_artifact_id(self.artifact_id, SHORT_BUILD_ID_LEN)
        build_dir = orig_build_dir = pjoin(self.build_store.temp_build_dir, short_id)
        i = 0
        # Try to make build_dir, if not then increment a -%d suffix until we        # fine a free slot
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
        return build_dir

    def remove_build_dir(self, build_dir):
        self.logger.info('Removing %s' % build_dir)
        rmtree_up_to(build_dir, self.build_store.temp_build_dir)

    def make_artifact_dir(self):
        # try to make shortened dir and symlink to it; incrementally
        # lengthen the name in the case of hash collision
        store = self.build_store.artifact_store_dir
        extra = 0
        while True:
            short_id = shorten_artifact_id(self.artifact_id, SHORT_ARTIFACT_ID_LEN + extra)
            artifact_dir = pjoin(store, short_id)
            try:
                os.makedirs(artifact_dir)
            except OSError, e:
                if e.errno != errno.EEXIST:
                    raise
                if os.path.exists(pjoin(store, self.artifact_id)):
                    raise NotImplementedError('race condition or unclean store')
            else:
                break
            extra += 1

        # Make a symlink from the full id to the shortened one
        artifact_link = pjoin(store, self.artifact_id)
        os.symlink(os.path.split(short_id)[-1], artifact_link)
        return artifact_dir, artifact_link
 
    def serialize_build_spec(self, d):
        with file(pjoin(d, 'build.json'), 'w') as f:
            json.dump(self.build_spec.doc, f, **json_formatting_options)
            f.write('\n')

    def unpack_sources(self, build_dir, source_cache):
        # sources
        for source_item in self.build_spec.doc.get('sources', []):
            key = source_item['key']
            target = source_item.get('target', '.')
            full_target = os.path.abspath(pjoin(build_dir, target))
            if not full_target.startswith(build_dir):
                raise InvalidBuildSpecError('source target attempted to escape '
                                            'from build directory')
            # if an exception is raised the directory is removed, so unsafe_mode
            # should be ok
            source_cache.unpack(key, full_target, unsafe_mode=True, strip=source_item['strip'])

    def unpack_files(self, build_dir, env):
        with working_directory(build_dir):
            execute_files_dsl(self.build_spec.doc.get('files', ()), env)

    def run_build_commands(self, build_dir, artifact_dir, env):
        artifact_display_name = shorten_artifact_id(self.artifact_id, SHORT_ARTIFACT_ID_LEN) + '..'
        env.update(self.build_spec.doc.get('env', {}))

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
                script = self.build_spec.doc.get('commands', ())
                sandbox.run_script_in_sandbox(logger, script, env=env, cwd=build_dir)
            finally:
                logger.pop_stream()
        compress(pjoin(build_dir, 'build.log'), pjoin(artifact_dir, 'build.log.gz'))

def rmtree_up_to(path, parent):
    """Executes shutil.rmtree(path), and then removes any empty parent directories
    up until (and excluding) parent.
    """
    path = os.path.realpath(path)
    parent = os.path.realpath(parent)
    if path == parent:
        return
    if not path.startswith(parent):
        raise ValueError('must have path.startswith(parent)')
    shutil.rmtree(path, ignore_errors=True)
    while path != parent:
        path, child = os.path.split(path)
        if path == parent:
            break
        try:
            os.rmdir(path)
        except OSError, e:
            if e.errno != errno.ENOTEMPTY:
                raise
            break

def compress(source_filename, dest_filename):
    chunk_size = 16 * 1024
    with file(source_filename, 'rb') as src:
        with gzip.open(dest_filename, 'wb') as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk: break
                dst.write(chunk)

def pack_virtuals_envvar(virtuals):
    return ';'.join('%s=%s' % tup for tup in sorted(virtuals.items()))

def unpack_virtuals_envvar(x):
    return dict(tuple(tup.split('=')) for tup in x.split(';'))

def execute_files_dsl(files, env):
    """
    Executes the mini-language used in the "files" section of the build-spec.

    Relative directories in targets are relative to current cwd.

    Parameters
    ----------

    files : json-like
        Files to create in the "files" mini-language (todo: document)

    env : dict
        Environment to use for variable substitutation
    """
    def subs(x):
        return Template(x).substitute(env)
    
    for file_spec in files:
        target = subs(file_spec['target'])
        # Automatically create parent directory of target
        dirname, basename = os.path.split(target)
        if dirname != '' and not os.path.exists(dirname):
            os.makedirs(dirname)

        if sum(['text' in file_spec, 'object' in file_spec]) != 1:
            print file_spec
            raise ValueError('objects in files section must contain either "text" or "object"')
        if 'object' in file_spec and 'expandvars' in file_spec:
            raise NotImplementedError('"expandvars" only supported for "text" currently')

        # IIUC in Python 3.3+ one can do this with the 'x' file mode, but need to do it
        # ourselves currently
        if file_spec.get('executable', False):
            mode = 0700
        else:
            mode = 0600
        fd = os.open(pjoin(dirname, basename), os.O_EXCL | os.O_CREAT | os.O_WRONLY, mode)
        with os.fdopen(fd, 'w') as f:
            if 'text' in file_spec:
                text = os.linesep.join(file_spec['text'])
                if file_spec.get('expandvars', False):
                    text = subs(text)
                f.write(text)
            else:
                json.dump(file_spec['object'], f, **json_formatting_options)

