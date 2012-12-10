import os
from os.path import join as pjoin
import tempfile
import json
import shutil
import subprocess
import sys

from .hash import hash_json, create_hasher, encode_digest

class BuildFailedError(Exception):
    def __init__(self, msg, path):
        Exception.__init__(self, msg)
        self.path = path

class InvalidBuildSpecError(ValueError):
    pass

class Builder(object):

    def __init__(self, source_cache, artifact_store_dir):
        if not os.path.isdir(artifact_store_dir):
            raise ValueError('"%s" is not an existing directory' % artifact_store_dir)
        self.source_cache = source_cache
        self.artifact_store_dir = os.path.realpath(artifact_store_dir)

    def get_artifact_name(self, build_spec):
        h = create_hasher()
        hash_json(h, build_spec)
        return '%s-%s' % (encode_digest(h), build_spec['name'])

    def resolve(self, build_spec):
        artifact_name = self.get_artifact_name(build_spec)
        adir = pjoin(self.artifact_store_dir, artifact_name)
        return os.path.exists(adir), artifact_name, adir

    def is_present(self, build_spec):
        return self.resolve(build_spec)[0]

    def ensure_present(self, build_spec, keep_on_fail=False):
        is_present, artifact_name, artifact_dir = self.resolve(build_spec)
        if is_present:
            return artifact_name
        else:
            d = tempfile.mkdtemp(prefix='%s-building-' % artifact_name, suffix='',
                                 dir=self.artifact_store_dir)
            try:
                build = ArtifactBuild(self, build_spec, d, artifact_name, artifact_dir)
                build.build()
            except:
                if keep_on_fail:
                    raise BuildFailedError('Temporary result in %s' % d, d)
                else:
                    shutil.rmtree(d)
                    raise
            else:
                os.rename(d, artifact_dir)
            return artifact_name, artifact_dir

class ArtifactBuild(object):
    def __init__(self, builder, build_spec, build_dir, artifact_name, artifact_dir):
        self.builder = builder
        self.build_spec = build_spec
        self.build_dir = build_dir
        self.artifact_name = artifact_name
        self.artifact_dir = artifact_dir

    def build(self):
        log_filename = pjoin(self.build_dir, 'build.log')
        sys.stderr.write('Building artifact %s, follow log with\n\n'
                         '    tail -f %s\n\n' %
                         (self.artifact_name, log_filename))
        sys.stderr.write('...')
        sys.stderr.flush()
        self.log_file = file(log_filename, 'w')
        try:
            self.serialize_build_spec()
            self.unpack_sources()
            self.run_build_command()
        finally:
            self.log_file.close()
            sys.stderr.write('done!\n\n')

    def serialize_build_spec(self):
        with file(pjoin(self.build_dir, 'build.json'), 'w') as f:
            json.dump(self.build_spec, f, separators=(', ', ' : '), indent=4, sort_keys=True)

    def unpack_sources(self):
        for source_item in self.build_spec['sources']:
            key = source_item['key']
            target = source_item['target']
            full_target = os.path.abspath(pjoin(self.build_dir, target))
            if not full_target.startswith(self.build_dir):
                raise InvalidBuildSpecError('source target attempted to escape '
                                            'from build directory')
            self.builder.source_cache.unpack(key, full_target)

    def run_build_command(self):
        # todo: $-interpolation in command
        command_lst = self.build_spec['command']

        env = {
            'PATH' : os.environ['PATH'], # for now
            'BUILD_TARGET' : self.artifact_dir,
            }

        logfileno = self.log_file.fileno()
        subprocess.check_call(command_lst, cwd=self.build_dir, env=env,
                              stdin=None, stdout=logfileno, stderr=logfileno)
