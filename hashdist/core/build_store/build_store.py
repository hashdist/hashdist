import os
from os.path import join as pjoin
import shutil
import sys
import re

from .build_spec import as_build_spec
from .builder import ArtifactBuilder

class BuildStore(object):

    def __init__(self, temp_build_dir, artifact_store_dir, logger):
        if not os.path.isdir(artifact_store_dir):
            raise ValueError('"%s" is not an existing directory' % artifact_store_dir)
        self.artifact_store_dir = os.path.realpath(artifact_store_dir)
        self.temp_build_dir = os.path.realpath(temp_build_dir)
        self.logger = logger

    def delete_all(self):
        for x in [self.artifact_store_dir, self.temp_build_dir]:
            shutil.rmtree(x)
            os.mkdir(x)

    @staticmethod
    def create_from_config(config, logger):
        """Creates a SourceCache from the settings in the configuration
        """
        return BuildStore(config.get_path('builder', 'builds-path'),
                          config.get_path('builder', 'artifacts-path'),
                          logger)

    def resolve(self, artifact_id):
        """Given an artifact_id, resolve the short path for it, or return
        None if the artifact isn't built.
        """
        adir = pjoin(self.artifact_store_dir, artifact_id)
        return os.path.realpath(adir) if os.path.exists(adir) else None

    def is_present(self, build_spec):
        build_spec = as_build_spec(build_spec)
        return self.resolve(build_spec.artifact_id) is not None

    def ensure_present(self, build_spec, source_cache, virtuals=None, keep_build='never',
                       log_inline=False):
        if virtuals is None:
            virtuals = {}
        if keep_build not in ('never', 'error', 'always'):
            raise ValueError("invalid keep_build value")
        build_spec = as_build_spec(build_spec)
        artifact_dir = self.resolve(build_spec.artifact_id)
        if artifact_dir is None:
            builder = ArtifactBuilder(self, build_spec, virtuals)
            artifact_dir = builder.build(source_cache, keep_build, log_inline)
        return build_spec.artifact_id, artifact_dir

