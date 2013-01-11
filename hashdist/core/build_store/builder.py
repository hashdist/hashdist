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

from ..source_cache import scatter_files
from .. import run_job
from ..common import (InvalidBuildSpecError, BuildFailedError,
                      json_formatting_options, SHORT_ARTIFACT_ID_LEN,
                      working_directory)

from ..fileutils import rmtree_up_to, gzip_compress

from ...hdist_logging import DEBUG

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
        with file(pjoin(d, 'build.json'), 'w') as f:
            json.dump(self.build_spec.doc, f, **json_formatting_options)
            f.write('\n')

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
        gzip_compress(pjoin(build_dir, 'build.log'), pjoin(artifact_dir, 'build.log.gz'))

