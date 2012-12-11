import os
from os.path import join as pjoin
import tempfile
import json
import shutil
import subprocess
import sys

from .hasher import Hasher

class BuildFailedError(Exception):
    def __init__(self, msg, build_dir):
        Exception.__init__(self, msg)
        self.build_dir = build_dir

class InvalidBuildSpecError(ValueError):
    pass

class Builder(object):

    def __init__(self, source_cache, artifact_store_dir, logger):
        if not os.path.isdir(artifact_store_dir):
            raise ValueError('"%s" is not an existing directory' % artifact_store_dir)
        self.source_cache = source_cache
        self.artifact_store_dir = os.path.realpath(artifact_store_dir)
        self.logger = logger

    def get_artifact_id(self, build_spec):
        h = Hasher(build_spec).format_digest()
        return '%s-%s' % (h, build_spec['name'])

    def resolve(self, build_spec):
        artifact_name = self.get_artifact_id(build_spec)
        adir = pjoin(self.artifact_store_dir, artifact_name)
        return os.path.exists(adir), artifact_name, adir

    def lookup(self, artifact_id):
        adir = pjoin(self.artifact_store_dir, artifact_id)
        return adir

    def is_present(self, build_spec):
        return self.resolve(build_spec)[0]

    def ensure_present(self, build_spec, keep_on_fail=False):
        is_present, artifact_name, artifact_dir = self.resolve(build_spec)
        if is_present:
            return artifact_name, artifact_dir
        else:
            build = ArtifactBuild(self, build_spec, artifact_name, artifact_dir)
            build.build(keep_on_fail)
            return artifact_name, artifact_dir

class ArtifactBuild(object):
    def __init__(self, builder, build_spec, artifact_name, artifact_dir):
        self.builder = builder
        self.logger = builder.logger
        self.build_spec = build_spec
        self.artifact_name = artifact_name
        self.artifact_dir = artifact_dir

    def get_dependencies_env(self):
        # Build the environment variables due to dependencies, and complain if
        # any dependency is not built
        env = {}
        for dep_name, dep_artifact in self.build_spec.get('dependencies', {}).iteritems():
            dep_dir = self.builder.lookup(dep_artifact)
            if not os.path.exists(dep_dir):
                raise InvalidBuildSpecError('Dependency {"%s" : "%s"} not already built (how did '
                                            'you even get a hash in the first place?) ' %
                                            (dep_name, dep_artifact))
            env[dep_name] = dep_artifact
            env['%s_abspath' % dep_name] = dep_dir
            env['%s_relpath' % dep_name] = pjoin('..', dep_artifact)
        return env

    def build(self, keep_on_fail):
        """
        Note that `keep_on_fail` only takes effect for failures within the build script;
        if the build specification is mis-specified then any temporary directory is always
        removed.
        """
        env = self.get_dependencies_env()
        
        build_dir = tempfile.mkdtemp(prefix='%s-building-' % self.artifact_name, suffix='',
                                     dir=self.builder.artifact_store_dir)
        # Always clean up when these fail
        try:
            self.serialize_build_spec(build_dir)
            self.unpack_sources(build_dir)
        except:
            shutil.rmtree(build_dir)
            raise
        
        # Conditionally clean up if this fails
        try:
            self.run_build_command(build_dir, env)
        except subprocess.CalledProcessError, e:
            if not keep_on_fail:
                shutil.rmtree(build_dir)
                raise BuildFailedError('Build command failed with code %d' % e.returncode, None)
            else:
                raise BuildFailedError('Build command failed with code %d, result in %s' %
                                       (e.returncode, build_dir), build_dir)
        # Success
        rename_or_delete(build_dir, self.artifact_dir)
 
    def serialize_build_spec(self, build_dir):
        with file(pjoin(build_dir, 'build.json'), 'w') as f:
            json.dump(self.build_spec, f, separators=(', ', ' : '), indent=4, sort_keys=True)

    def unpack_sources(self, build_dir):
        for source_item in self.build_spec['sources']:
            key = source_item['key']
            target = source_item.get('target', '.')
            full_target = os.path.abspath(pjoin(build_dir, target))
            if not full_target.startswith(build_dir):
                raise InvalidBuildSpecError('source target attempted to escape '
                                            'from build directory')
            self.builder.source_cache.unpack(key, full_target)

    def run_build_command(self, build_dir, env):
        # todo: $-interpolation in command
        command_lst = self.build_spec['command']

        env['PATH'] = os.environ['PATH'] # for now
        env['BUILD_TARGET'] = self.artifact_dir

        log_filename = pjoin(build_dir, 'build.log')
        self.logger.info('Building artifact %s, follow log with' % self.artifact_name)
        self.logger.info('')
        self.logger.info('    tail -f %s\n\n' % log_filename)
        with file(log_filename, 'w') as log_file:
            logfileno = log_file.fileno()
            subprocess.check_call(command_lst, cwd=build_dir, env=env,
                                  stdin=None, stdout=logfileno, stderr=logfileno)

def rename_or_delete(from_, to):
    """Renames a directory, or recursively deletes it if the target already exists.

    This is used in situations where multiple processes may compute the same result directory.
    """
    try:
        os.rename(from_, to)
    except OSError, e:
        if os.path.exists(to):
            shutil.rmtree(from_)
        else:
            raise

