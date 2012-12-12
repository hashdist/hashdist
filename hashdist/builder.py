import os
from os.path import join as pjoin
import tempfile
import json
import shutil
import subprocess
import sys
import re
import errno

from .hasher import Hasher
from .source_cache import SourceCache

class BuildFailedError(Exception):
    def __init__(self, msg, build_dir):
        Exception.__init__(self, msg)
        self.build_dir = build_dir

class InvalidBuildSpecError(ValueError):
    pass

BUILD_ID_LEN = 4
ARTIFACT_ID_LEN = 4

SAFE_NAME_RE = re.compile(r'[a-zA-Z0-9-_+]+')

def assert_safe_name(x):
    """Raises a ValueError if x does not match SAFE_NAME_RE. Returns `x`."""
    if not SAFE_NAME_RE.match(x):
        raise ValueError('"%s" is empty or contains illegal characters')
    return x

def get_artifact_id(build_spec):
    """Produces the hash/"artifact id" from the given build spec.

    This can be produced merely from the textual form of the spec without
    considering any run-time state on any system.
    
    """
    digest = Hasher(build_spec).format_digest()
    name = assert_safe_name(build_spec['name'])
    version = assert_safe_name(build_spec['version'])
    
    return '%s/%s/%s' % (name, version, digest)

def shorten_artifact_id(artifact_id, length):
    """Shortens the hash part of the artifact_id to the desired length
    """
    return artifact_id[:artifact_id.rindex('/') + length + 1]

class Builder(object):

    def __init__(self, source_cache, temp_build_dir, artifact_store_dir, logger,
                 keep_build_policy='never'):
        if not os.path.isdir(artifact_store_dir):
            raise ValueError('"%s" is not an existing directory' % artifact_store_dir)
        if keep_build_policy not in ('never', 'error', 'always'):
            raise ValueError("invalid keep_build_dir_policy")
        self.source_cache = source_cache
        self.artifact_store_dir = os.path.realpath(artifact_store_dir)
        self.temp_build_dir = os.path.realpath(temp_build_dir)
        self.logger = logger
        self.keep_build_policy = keep_build_policy

    def delete_all(self):
        for x in [self.artifact_store_dir, self.temp_build_dir]:
            shutil.rmtree(x)
            os.mkdir(x)

    @staticmethod
    def create_from_config(config, logger):
        """Creates a SourceCache from the settings in the configuration
        """
        source_cache = SourceCache.create_from_config(config)
        return Builder(source_cache,
                       config.get_path('builder', 'artifacts-path'),
                       config.get_path('builder', 'builds-path'),
                       logger)

    def resolve(self, artifact_id):
        """Given an artifact_id, resolve the short path for it, or return
        None if the artifact isn't built.
        """
        adir = pjoin(self.artifact_store_dir, artifact_id)
        return os.path.realpath(adir) if os.path.exists(adir) else None

    def is_present(self, build_spec):
        return self.resolve(get_artifact_id(build_spec)) is not None

    def ensure_present(self, build_spec):
        artifact_id = get_artifact_id(build_spec)
        artifact_dir = self.resolve(artifact_id)
        if artifact_dir is None:
            build = ArtifactBuild(self, build_spec, artifact_id)
            artifact_dir = build.build()
        return artifact_id, artifact_dir

class ArtifactBuild(object):
    def __init__(self, builder, build_spec, artifact_id):
        self.builder = builder
        self.logger = builder.logger
        self.build_spec = build_spec
        self.artifact_id = artifact_id

    def get_dependencies_env(self, relative_from):
        # Build the environment variables due to dependencies, and complain if
        # any dependency is not built
        env = {}
        for dep_name, dep_artifact in self.build_spec.get('dependencies', {}).iteritems():
            dep_dir = self.builder.resolve(dep_artifact)
            if dep_dir is None:
                raise InvalidBuildSpecError('Dependency {"%s" : "%s"} not already built, please build it first' %
                                            (dep_name, dep_artifact))
            env[dep_name] = dep_artifact
            env['%s_abspath' % dep_name] = dep_dir
            env['%s_relpath' % dep_name] = os.path.relpath(dep_dir, relative_from)
        return env

    def build(self):        
        artifact_dir, artifact_link = self.make_artifact_dir()
        try:
            self.build_to(artifact_dir)
        except:
            shutil.rmtree(artifact_dir)
            os.unlink(artifact_link)
            raise
        return artifact_dir

    def build_to(self, artifact_dir):
        env = self.get_dependencies_env(artifact_dir)
        keep_build_policy = self.builder.keep_build_policy

        # Always clean up when these fail regardless of keep_build_policy
        build_dir = self.make_build_dir()
        try:
            self.serialize_build_spec(artifact_dir, build_dir)
            self.unpack_sources(build_dir)
        except:
            shutil.rmtree(build_dir)
            raise

        # Conditionally clean up when this fails
        try:
            self.run_build_command(build_dir, artifact_dir, env)
        except subprocess.CalledProcessError, e:
            if keep_build_policy == 'never':
                shutil.rmtree(build_dir)
                raise BuildFailedError('Build command failed with code %d' % e.returncode, None)
            else:
                raise BuildFailedError('Build command failed with code %d, result in %s' %
                                       (e.returncode, build_dir), build_dir)
        # Success
        if keep_build_policy != 'always':
            shutil.rmtree(build_dir)
        return artifact_dir

    def make_build_dir(self):
        short_id = shorten_artifact_id(self.artifact_id, BUILD_ID_LEN)
        build_dir = orig_build_dir = pjoin(self.builder.temp_build_dir, short_id)
        i = 0
        # Try to make build_dir, if not then increment a -%d suffix until we
        # fine a free slot
        while True:
            try:
                os.makedirs(build_dir)
            except OSError, e:
                if e != errno.EEXIST:
                    raise
            else:
                break
            i += 1
            build_dir = '%s-%d' % (orig_build_dir, i)
        return build_dir

    def make_artifact_dir(self):
        # try to make shortened dir and symlink to it; incrementally
        # lengthen the name in the case of hash collision
        store = self.builder.artifact_store_dir
        extra = 0
        while True:
            short_id = shorten_artifact_id(self.artifact_id, ARTIFACT_ID_LEN + extra)
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
 
    def serialize_build_spec(self, build_dir, artifact_dir):
        for d in [build_dir, artifact_dir]:
            with file(pjoin(d, 'build.json'), 'w') as f:
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

    def run_build_command(self, build_dir, artifact_dir, env):
        # todo: $-interpolation in command
        command_lst = self.build_spec['command']

        env['PATH'] = os.environ['PATH'] # for now
        env['PREFIX'] = artifact_dir

        log_filename = pjoin(build_dir, 'build.log')
        self.logger.info('Building artifact %s, follow log with' % self.artifact_id)
        self.logger.info('')
        self.logger.info('    tail -f %s\n\n' % log_filename)
        with file(log_filename, 'w') as log_file:
            logfileno = log_file.fileno()
            subprocess.check_call(command_lst, cwd=build_dir, env=env,
                                  stdin=None, stdout=logfileno, stderr=logfileno)
        # On success, copy log file to artifact_dir
        shutil.copy(log_filename, pjoin(artifact_dir, 'build.log'))

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

