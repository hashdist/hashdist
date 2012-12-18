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
import contextlib

from ..source_cache import scatter_files
from ..sandbox import get_artifact_dependencies_env
from .build_spec import shorten_artifact_id
from ..common import InvalidBuildSpecError


BUILD_ID_LEN = 4
ARTIFACT_ID_LEN = 4

class BuildFailedError(Exception):
    def __init__(self, msg, build_dir):
        Exception.__init__(self, msg)
        self.build_dir = build_dir

class ArtifactBuilder(object):
    def __init__(self, build_store, build_spec, virtuals):
        self.build_store = build_store
        self.logger = build_store.logger
        self.build_spec = build_spec
        self.artifact_id = build_spec.artifact_id
        self.virtuals = virtuals

    def build(self, source_cache, keep_build, log_inline):
        artifact_dir, artifact_link = self.make_artifact_dir()
        try:
            self.build_to(artifact_dir, source_cache, keep_build, log_inline)
        except:
            shutil.rmtree(artifact_dir)
            os.unlink(artifact_link)
            raise
        return artifact_dir

    def build_to(self, artifact_dir, source_cache, keep_build, log_inline):
        env = get_artifact_dependencies_env(self.build_store, self.virtuals,
                                            self.build_spec.doc.get('dependencies', ()))

        # Always clean up when these fail regardless of keep_build_policy
        build_dir = self.make_build_dir()
        try:
            env['ARTIFACT'] = artifact_dir
            env['BUILD'] = build_dir

            self.serialize_build_spec(artifact_dir, build_dir)
            self.unpack_sources(build_dir, source_cache)
            self.unpack_files(build_dir, env)
        except:
            self.remove_build_dir(build_dir)
            raise

        # Conditionally clean up when this fails
        try:
            self.run_build_commands(build_dir, artifact_dir, env, log_inline)
        except BuildFailedError, e:
            if keep_build == 'never':
                self.remove_build_dir(build_dir)
            raise e
        # Success
        if keep_build != 'always':
            self.remove_build_dir(build_dir)
        return artifact_dir

    def make_build_dir(self):
        short_id = shorten_artifact_id(self.artifact_id, BUILD_ID_LEN)
        build_dir = orig_build_dir = pjoin(self.build_store.temp_build_dir, short_id)
        i = 0
        # Try to make build_dir, if not then increment a -%d suffix until we
        # fine a free slot
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
        rmtree_up_to(build_dir, self.build_store.temp_build_dir)

    def make_artifact_dir(self):
        # try to make shortened dir and symlink to it; incrementally
        # lengthen the name in the case of hash collision
        store = self.build_store.artifact_store_dir
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
                json.dump(self.build_spec.doc, f, separators=(', ', ' : '), indent=4, sort_keys=True)

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

    def run_build_commands(self, build_dir, artifact_dir, env, log_inline):
        # Handles log-file, environment, build execution
        env['TARGET'] = artifact_dir
        env['BUILD'] = build_dir
        if 'PATH' not in env:
            env['PATH'] = ''

        log_filename = pjoin(build_dir, 'build.log')
        self.logger.info('Building artifact %s..., follow log with' %
                         shorten_artifact_id(self.artifact_id, ARTIFACT_ID_LEN + 2))
        self.logger.info('')
        self.logger.info('    tail -f %s\n\n' % log_filename)
        with file(log_filename, 'w') as log_file:
            logfileno = log_file.fileno()
            for command_lst in self.build_spec.doc.get('commands', ()):
                log_file.write("hdist: running command %r" % command_lst)
                if log_inline:
                    # HACK; we should really do a 'tee' here
                    logfileno = None
                
                try:
                    subprocess.check_call(command_lst, cwd=build_dir, env=env,
                                          stdin=None, stdout=logfileno, stderr=logfileno)
                except subprocess.CalledProcessError, e:
                    log_file.write("hdist: command FAILED with code %d\n" % e.returncode)
                    raise BuildFailedError('Build command failed with code %d (cwd: "%s")' %
                                           (e.returncode, build_dir), build_dir)
                except OSError, e:
                    if e.errno == errno.ENOENT:
                        log_file.write('hdist: command "%s" not found in PATH\n' % command_lst[0])
                        raise BuildFailedError('command "%s" not found in PATH (cwd: "%s")' %
                                               (command_lst[0], build_dir), build_dir)
                    else:
                        raise
                        
            log_file.write("hdist: SUCCESS\n")
        # On success, copy log file to artifact_dir
        shutil.copy(log_filename, pjoin(artifact_dir, 'build.log'))

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
    shutil.rmtree(path)
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
        
        if 'text' in file_spec:
            text = os.linesep.join(file_spec['text'])
            if file_spec.get('expandvars', False):
                text = subs(text)
            
            if file_spec.get('executable', False):
                mode = 0700
            else:
                mode = 0600

            # IIUC in Python 3.3+ one can do this with the 'x' file mode, but need to do it
            # ourselves currently
            fd = os.open(pjoin(dirname, basename), os.O_EXCL | os.O_CREAT | os.O_WRONLY, mode)
            with os.fdopen(fd, 'w') as f:
                f.write(text)

        elif 'symlink_to' in file_spec:
            os.symlink(file_spec['symlink_to'], target)

        else:
            raise ValueError('neither "text" nor "symlink_to" property found')


@contextlib.contextmanager
def working_directory(path):
    old = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(old)
