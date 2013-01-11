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
from .. import run_job
from ..common import (InvalidBuildSpecError, BuildFailedError,
                      json_formatting_options, SHORT_ARTIFACT_ID_LEN,
                      working_directory)
from ..fileutils import rmtree_up_to

from ...hdist_logging import DEBUG

class ArtifactBuilder(object):
    def __init__(self, build_store, build_spec, virtuals):
        self.build_store = build_store
        self.logger = build_store.logger.get_sub_logger(build_spec.doc['name'])
        self.build_spec = build_spec
        self.artifact_id = build_spec.artifact_id
        self.virtuals = virtuals

        # Some features are implemented by transforming the build spec to add
        # items to the job script
        transformed_job_spec = self.build_spec.doc['build']
        for transform in [transform_job_unpack_sources, transform_job_write_files]:
            transformed_job_spec = transform(self.build_spec.doc, transformed_job_spec)
        self.transformed_job_spec = transformed_job_spec

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
        with file(pjoin(d, 'build.json'), 'w') as f:
            json.dump(self.build_spec.doc, f, **json_formatting_options)
            f.write('\n')

    def run_build_commands(self, build_dir, artifact_dir, env, config):
        artifact_display_name = self.build_spec.digest[:SHORT_ARTIFACT_ID_LEN] + '..'
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
                run_job.run_job(logger, self.build_store, self.transformed_job_spec,
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
        compress(pjoin(build_dir, 'build.log'), pjoin(artifact_dir, 'build.log.gz'))


def _prepend_command(command, job_spec):
    result = dict(job_spec)
    result['script'] = [command] + list(job_spec['script'])
    return result

def transform_job_unpack_sources(build_spec, job_spec):
    """Given a build spec document with a 'sources' section, transform
    the job spec to add actions for unpacking sources.

    Returns a new job_spec without modifying the old one (though it may
    share sub-trees that were not modified).
    """
    if not build_spec['sources']:
        return job_spec
    else:
        return _prepend_command(['@hdist', 'build-unpack-sources', 'build.json'], job_spec)

def transform_job_write_files(build_spec, job_spec):
    """Given a build spec document with a 'files' section, transform
    the job spec to add actions for writing files.

    Returns a new job_spec without modifying the old one (though it may
    share sub-trees that were not modified).
    """
    if not build_spec['files']:
        return job_spec
    else:
        return _prepend_command(['@hdist', 'build-write-files', 'build.json'], job_spec)

def compress(source_filename, dest_filename):
    chunk_size = 16 * 1024
    with file(source_filename, 'rb') as src:
        with gzip.open(dest_filename, 'wb') as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk: break
                dst.write(chunk)

def execute_files_dsl(files, env):
    """
    Executes the mini-language used in the "files" section of the build-spec.
    See :class:`.BuildWriteFiles`.

    Relative directories in targets are relative to current cwd.

    Parameters
    ----------

    files : json-like
        Files to create in the "files" mini-language

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

        # IIUC in Python 3.3+ one can do exclusive creation with the 'x'
        # file mode, but need to do it ourselves currently
        if file_spec.get('executable', False):
            mode = 0o700
        else:
            mode = 0o600
        fd = os.open(pjoin(dirname, basename), os.O_EXCL | os.O_CREAT | os.O_WRONLY, mode)
        with os.fdopen(fd, 'w') as f:
            if 'text' in file_spec:
                text = os.linesep.join(file_spec['text'])
                if file_spec.get('expandvars', False):
                    text = subs(text)
                f.write(text)
            else:
                json.dump(file_spec['object'], f, **json_formatting_options)

