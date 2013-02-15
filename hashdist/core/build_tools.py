import os
from os.path import join as pjoin
import json
from string import Template

from .common import json_formatting_options
from .build_store import BuildStore
from .profile import make_profile
from .fileutils import rmdir_empty_up_to, write_protect

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

def get_import_envvar(env):
    return env['HDIST_IMPORT'].split()

def build_whitelist(build_store, artifact_ids, stream):
    for artifact_id in artifact_ids:
        path = build_store.resolve(artifact_id)
        if path is None:
            raise Exception("Artifact %s not found" % artifact_id)
        stream.write('%s\n' % pjoin(path, '**'))
        #with open(pjoin(path, 'artifact.json')) as f:
        #    doc = json.load(f)

def recursive_list_files(dir):
    result = set()
    for root, dirs, files in os.walk(dir):
        for fname in files:
            result.add(pjoin(root, fname))
    return result

def push_build_profile(config, logger, virtuals, buildspec_filename, manifest_filename, target_dir):
    files_before_profile = recursive_list_files(target_dir)
    
    with open(buildspec_filename) as f:
        imports = json.load(f).get('build', {}).get('import', [])
    build_store = BuildStore.create_from_config(config, logger)
    make_profile(logger, build_store, imports, target_dir, virtuals, config)

    files_after_profile = recursive_list_files(target_dir)
    installed_files = files_after_profile.difference(files_before_profile)
    with open(manifest_filename, 'w') as f:
        json.dump({'installed-files': sorted(list(installed_files))}, f)

def pop_build_profile(manifest_filename, root):
    with open(manifest_filename) as f:
        installed_files = json.load(f)['installed-files']
    for fname in installed_files:
        os.unlink(fname)
        rmdir_empty_up_to(os.path.dirname(fname), root)


#
# Tools to use on individual files for postprocessing
#

def postprocess_launcher_shebangs(filename, launcher_program):
    if not os.path.isfile(filename):
        return
    
    mode = os.stat(filename).st_mode
    if mode | 0o111:
        with open(filename) as f:
            is_script = (f.read(2) == '#!')
            if is_script:
                script_no_hashexclam = f.read()

    if is_script:
        script_filename = filename + '.real'
        dirname = os.path.dirname(filename)
        rel_launcher = os.path.relpath(launcher_program, dirname)
        # Set up:
        #   thescript      # symlink to ../../path/to/launcher
        #   thescript.real # non-executable script with modified shebang
        lines = script_no_hashexclam.splitlines(True) # keepends=True
        cmd = lines[0].split()
        interpreters = '${PROFILE_BIN_DIR}/%s:${ORIGIN}/%s' % (
            os.path.basename(cmd[0]), os.path.relpath(cmd[0], dirname))
        cmd[0] = interpreters
        lines[0] = '#!%s\n' % ' '.join(cmd)
        with open(script_filename, 'w') as f:
            f.write(''.join(lines))
        write_protect(script_filename)
        os.unlink(filename)
        os.symlink(rel_launcher, filename)

def postprocess_write_protect(filename):
    """
    Write protect files. Leave directories alone because the inability
    to rm -rf is very annoying.
    """
    if not os.path.isfile(filename):
        return
    write_protect(filename)
