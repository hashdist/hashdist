"""
:mod:`hashdist.core.build_tools` --- Tools to assist build scripts
==================================================================

Reference
---------


"""

import sys
import os
from os.path import join as pjoin
import json
from string import Template
from textwrap import dedent
import re
import subprocess

from .common import json_formatting_options
from .build_store import BuildStore
from .fileutils import rmdir_empty_up_to, write_protect, silent_unlink

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
            mode = 0o755
        else:
            mode = 0o644
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

#
# Tools to use on individual files for postprocessing
#

def is_executable(filename):
    return os.stat(filename).st_mode & 0o111 != 0

def postprocess_launcher_shebangs(filename, launcher_program):
    if not os.path.isfile(filename) or os.path.islink(filename):
        return
    if 'bin' not in filename:
        return

    if is_executable(filename):
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

def postprocess_multiline_shebang(build_store, filename):
    """
    Try to rewrite the shebang of scripts. This function deals with
    detecting whether the script is a shebang, and if so, rewrite it.
    """
    if not os.path.isfile(filename) or os.path.islink(filename) or not is_executable(filename):
        return

    with open(filename) as f:
        if f.read(2) != '#!':
            # no shebang
            return

        scriptlines = f.readlines()
        scriptlines[0] = '#!' + scriptlines[0]

    try:
        mod_scriptlines = make_relative_multiline_shebang(build_store, filename, scriptlines)
    except UnknownShebangError:
        # just leave unsupported scripts as is
        pass
    else:
        if mod_scriptlines != scriptlines:
            with open(filename, 'w') as f:
                f.write(''.join(mod_scriptlines))

#
# Relocatability
#
def postprocess_relative_symlinks(logger, artifact_dir, filename):
    """
    Turns absolute symlinks that points inside the artifact_dir into relative
    symlinks, and gives an error on symlinks that point out of the artifact
    """
    if os.path.islink(filename):
        target = os.readlink(filename)
        if os.path.isabs(target):
            if not filename.startswith(artifact_dir):
                msg = 'Absolute symlink %s points to %s outside of %s' % (filename, target, artifact_dir)
                logger.error(msg)
                raise ValueError(msg)
            else:
                new_target = os.path.relpath(target, os.path.dirname(filename))
                logger.debug('Rewriting symlink "%s" from "%s" to "%s"' % (filename, target, new_target))
                os.unlink(filename)
                os.symlink(new_target, filename)

def postprocess_rpath(logger, artifact_root_dir, env, filename):
    if os.path.islink(filename) or not os.path.isfile(filename) or not is_executable(filename):
        return
    if 'linux' in sys.platform:
        postprocess_rpath_linux(logger, env, filename)
    if 'darwin' in sys.platform:
        postprocess_rpath_darwin(logger, artifact_root_dir, env, filename)

def _check_call(logger, cmd):
    """
    Like subprocess.check_call but additionally captures stdout/stderr, and returns stdout.
    """
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    out, err = p.communicate()
    if p.wait() != 0:
        logger.error('%r failed: %d' % (cmd, p.wait()))
        raise Exception(
            'Command %r failed with code %d and stderr:\n%s' % (cmd, p.wait(), err))
    return out

def postprocess_rpath_darwin(logger, artifact_root_dir, env, filename):
    """
    Convert absolute Mach-O dyld links to libraries in the build store to relative links
    """

    print filename
    print artifact_root_dir

    out = _check_call(logger, ['otool', '-l', filename])

    def emit_load_cmds(cmd_list):
        """
        Given a list of Mach-O load commands, emit all dynamic libraries to be loaded
        """
        for i, line in enumerate(cmd_list):
            if 'cmd LC_LOAD_DYLIB' in line:
                yield cmd_list[i+2]

    def emit_absolute_libs(otool_l_output):
        """
        Given the raw output of otool -l, emit the names of any dynamic libraries that
        are referred to the absolute location of the artifact_root_dir
        """
        cmd_list = out.splitlines()[1:]
        for load_cmd in emit_load_cmds(cmd_list):
            lib_path = load_cmd.split()[1]
            if artifact_root_dir in lib_path:
                yield lib_path

    if out:
        # check for the presence of absolute references to the artifact_root_dir
        d = os.path.dirname(os.path.realpath(filename))
        for abs_lib_path in emit_absolute_libs(out):
            rel_lib_path = '@loader_path/' + os.path.relpath(abs_lib_path, d)
            logger.debug('Rewriting absolute library path on "%s" from "%s" to "%s"' %
                         (filename, abs_lib_path, rel_lib_path))
            _check_call(logger, ['install_name_tool', '-change', abs_lib_path, rel_lib_path, filename])

def postprocess_rpath_linux(logger, env, filename):
    # Read first 4 bytes to check for ELF magic
    with open(filename) as f:
        if f.read(4) != '\x7fELF':
            # Not an ELF file
            return

    if 'PATCHELF' not in env:
        raise Exception('PATCHELF not set (Linux relocatable packages depend on patchelf)')
    patchelf = env['PATCHELF']

    # OK, we have an ELF, patch it. We first shrink the RPATH to what is actually used.
    _check_call(logger, [patchelf, '--shrink-rpath', filename])

    # Then grab the RPATH, make each path relative to ${ORIGIN}, and set again.
    out = _check_call(logger, [patchelf, '--print-rpath', filename]).strip()
    if out:
        # non-empty RPATH, patch it
        abs_rpaths_str = out.strip()
        abs_rpaths = abs_rpaths_str.split(':')
        d = os.path.dirname(os.path.realpath(filename))
        rel_rpaths = ['${ORIGIN}/' + os.path.relpath(abs_rpath, d) for abs_rpath in abs_rpaths]
        rel_rpaths_str = ':'.join(rel_rpaths)
        logger.debug('Rewriting RPATH on "%s" from "%s" to "%s"' % (filename, abs_rpaths_str, rel_rpaths_str))
        _check_call(logger, [patchelf, '--set-rpath', rel_rpaths_str, filename])


PKG_CONFIG_FILES_RE = re.compile(r'.*/lib/pkgconfig/.*\.pc$')
def postprocess_remove_pkgconfig(logger, filename):
    """
    Delete pkg-config .pc-files

    These include the absolute path by default. Packages may be able
    to build without pkg-config information, so one (suboptimal)
    possibility is to delete them.
    """
    if PKG_CONFIG_FILES_RE.match(os.path.realpath(filename)):
        logger.info('Removing %s' % filename)
        silent_unlink(filename)

def postprocess_relative_pkgconfig(logger, artifact_dir, filename):
    """
    Rewrite pkg-config .pc-files without absolute paths.

    Replaces the ``artifact_dir`` with ``${FOO_DIR}`` (replace ``FOO``
    with package name). The hashstack pkg-config includes a wrapper
    script that then passes ``--define-variable=FOO_DIR=artifact_dir``
    to the pkg-config implementation.
    """
    if not PKG_CONFIG_FILES_RE.match(os.path.realpath(filename)):
        return
    if os.path.islink(filename):
        # Link to another pc file, e.g. libpng.pc -> libpng16.pc
        return
    # we don't have access to the spec of the package that we are rewriting :-(
    # ugly workaround: guess package name from the artifact dir
    name = os.path.basename(os.path.dirname(artifact_dir))
    package_dir = '${' + name.upper() + '_DIR}'
    logger.info('Rewriting %s using %s', filename, package_dir)
    with open(filename, 'r') as f:
        pc = f.read()
    pc = pc.replace(artifact_dir, package_dir)
    with open(filename, 'w') as f:
        f.write(pc)

def postprocess_sh_script(logger, patterns, artifact_dir, filename):
    """
    `patterns` should only match files that should be modified.
    Assuming the script is a bash/sh script, we modify it
    """
    if not os.path.isfile(filename) or os.path.islink(filename):
        return
    filename = os.path.realpath(filename)
    s = filename[len(artifact_dir):]
    for pattern in patterns:
        if re.match(pattern, s):
            break
    else:
        return

    # Number of .. to get from script-dir to artifact_dir
    up = os.path.relpath(artifact_dir, os.path.dirname(filename))

    # Pattern matches, let's modify the file:
    # a) Insert a small script to set HASHDIST_ARTIFACT to the artifact containing the script
    # b) Replace occurences of the artifact dir with ${HASHDIST_ARTIFACT}
    logger.info('Patching %s to compute artifact path dynamically' % filename)
    script = ['# Compute HASHDIST_ARTIFACT\n'] + pack_sh_script(dedent("""\
        o=`pwd`
        p="$0"
        while test -L "$p"; do  # while it is a link
            cd `dirname "$p"`
            cd `pwd -P`
            p=`readlink "$p"`
        done
        cd `dirname "$p"`/%(up)s
        HASHDIST_ARTIFACT=`pwd -P`
        cd "$o"
    """ % dict(up=up))).splitlines(True)
    with open(filename) as f:
        lines = f.readlines(True)  # keepends=True
    if not lines:
        # empty
        return
    i = 1 if lines[0].startswith('#!') else 0
    lines = lines[:i] + script + [line.replace(artifact_dir, '${HASHDIST_ARTIFACT}') for line in lines[i:]]
    with open(filename, 'w') as f:
        f.write(''.join(lines))


def check_relocatable(logger, ignore_patterns, artifact_dir, filename):
    """
    Checks whether `filename` contains the string `artifact_dir`, in which case it is not
    relocatable.

    For now we simply load the entire file into memory.
    """
    if not filename.startswith(artifact_dir):
        raise ValueError('filename must be prefixed with artifact_dir')
    s = filename[len(artifact_dir):]
    for pattern in ignore_patterns:
        if re.match(pattern, s):
            return

    artifact_dir_b = artifact_dir.encode(sys.getfilesystemencoding())
    baddies = []
    is_link = os.path.islink(filename)
    if not is_link and os.path.isfile(filename):
        with open(filename) as f:
            data = f.read()
        if artifact_dir_b in data:
            logger.error('File contains "%s" and can not be relocated: %s' % (artifact_dir_b, filename))
            baddies.append(filename)
    elif is_link:
        if artifact_dir_b in os.readlink(filename):
            logger.error('Symlink contains "%s" and can not be relocated: %s' % (artifact_dir_b, filename))
            baddies.append(filename)
    if baddies:
        raise Exception('Files not relocatable:\n%s' % ('\n'.join('  ' + x for x in baddies)))

#
# Shebang
#
class UnknownShebangError(NotImplementedError):
    pass


# we don't patch /bin, /usr/bin, ...
_INTERPRETER_RE = re.compile(r'^#!\s*(\S+)\s+.*')
def make_relative_multiline_shebang(build_store, filename, scriptlines):
    """
    See module docstring for motivation.

    Any shebang starting with "/bin" or "/usr/bin" will be left intact (including
    "/usr/bin/env python"). Otherwise, it is assumed they refer to a
    build artifact by absolute path and we rewrite it to a relative
    one.

    Parameters
    ----------

    build_store : BuildStore
        Used to identify shebangs that reference paths within HashDist artifacts

    scriptlines : list of str
        List of lines in the script; each line includes terminating newline

    Returns
    -------

    scriptlines : list of str
        List of lines of modified script; each line including terminating newline

    """
    shebang = scriptlines[0]
    m = _INTERPRETER_RE.match(shebang)
    if not m:
        # not a shebang
        return scriptlines
    interpreter = m.group(1)
    if not (os.path.isabs(interpreter) and build_store.is_path_in_build_store(interpreter)):
        # we do not touch scripts with interpreters like #!python or #!/usr/bin/env
        return scriptlines
    elif 'python' in shebang:
        mod_scriptlines = patch_python_shebang(filename, scriptlines)
    else:
        raise UnknownShebangError('No support for shebang "%s" in file "%s"' %
                                  (shebang, filename))
    return mod_scriptlines


# Assume that the script is called through a set of symlinks; p_n ->
# ... -> p_1 -> script. On call $0 is p_n, and we assume the first
# non-symlink is the script. For each link in the chain, we walk .. to
# the root (of the *physical* path) checking for the presence of the
# file "is-profile"; if found, we launch the interpreter from the
# "bin"-directory beneath it. If not found, we use the given relpath
# relative to the script location.

_launcher_script = dedent("""\
    i="%(interpreter)s" # interpreter base-name
    %(arg_assign)s # may be 'arg=...' if there is an argument

    # If this script is called during "hit build" (i.e. HDIST_IN_BUILD=yes),
    # then we simply call the $i (interpreter name) on this script (no lookup
    # happens). This assumes that $i is in the path. Typically you put "python"
    # into the $PATH while building Python packages and then assign $i=python.

    if [ "$HDIST_IN_BUILD" = "yes" ] ; then exec "$i" "$0"%(arg_expr)s"$@"; fi

    # If this script is called by the user (i.e. HDIST_IN_BUILD!=yes), then the
    # script must be in a profile. As such, all we need to do is to loop to
    # follow the chain of links by cd-ing to their directories and calling
    # readlink, until we cd into the directory with artifact.json. From there
    # we call bin/$i (i.e. typically bin/python) on this script. If
    # artifact.json cannot be found, we exit with an error.

    o=`pwd`
    # $p is the current link:
    p="$0"
    while true; do
        # This loop tests whether $p is a link and if so, it continues
        # following the symlinks (this happens e.g. when the user symlinks
        # "ipython" from some profile into their ~/bin directory which is on
        # the $PATH). For each step, it tries to determine whether it is in the
        # profile and if so, executes the bin/$i from there, and if not,
        # continue looping.
        # If $p is not a symlink (and not in a profile), then it fails with an
        # error. This outer loop must always terminate, because eventually $p
        # will not be a symlink, and it will either be in a profile (success)
        # or not (failure).
        test -L "$p"
        il=$? # is_link
        cd `dirname "$p"`
        pdir=`pwd -P`
        d="$pdir"

        # In this inner loop we cd upwards towards root searching for
        # "artifact.json" file. If we find it, we execute bin/$i from there. If
        # we don't find it, we exit the loop without an error.
        while [ "$d" != / ]; do

            if [ -e "$d/artifact.json" ]; then
                if [ ! -e "$d/bin/$i" ]; then
                    echo "Unable to locate needed $i in $p/bin"
                    echo "HashDist profile $d has likely been corrupted, please try rebuilding."
                    exit 127
                fi
                cd "$o" && exec "$d/bin/$i" "$0"%(arg_expr)s"$@"
            fi
            cd ..
            d=`pwd -P`
        done

        cd "$pdir"
        if [ "$il" -ne 0 ]; then
            # $p is not a symlink and not in a profile (this simply means that
            # no profile was found), so we terminate the loop with an error.
            echo "No profile found."
            exit 127
        fi
        p=`readlink $p`  # TODO should this not be readlink of `basename $p`?
    done
""")

def _get_launcher(script_filename, shebang):
    if shebang[:2] != '#!':
        raise ValueError("expected a shebang first in '%s'" % script_filename)
    cmd = [x.strip() for x in shebang[2:].split()]
    if len(cmd) > 1:
        # in shebangs the remainder is a single argument
        arg_assign = 'arg="%s"' % ' '.join(cmd[1:])
        arg_expr = '"$arg"'
    else:
        arg_assign = arg_expr = ' '
    relpath = os.path.relpath(os.path.dirname(cmd[0]),
                              os.path.dirname(script_filename))
    return _launcher_script % dict(interpreter=os.path.basename(cmd[0]),
                                   arg_assign=arg_assign,
                                   arg_expr=arg_expr,
                                   relpath=relpath)

_CLEAN_RE = re.compile(r'^([^#]*)(#.*)?$')
def pack_sh_script(script):
    lines = script.splitlines()
    lines = [_CLEAN_RE.match(line).group(1).strip() for line in lines]
    lines = [x for x in lines if len(x) > 0]
    lines = [x + ' ' if x.endswith(' do') or x.endswith(' then') else x + ';' for x in lines]
    return ''.join(lines)

_PY_EMPTY_RE = re.compile(r'^\s*(#.*)?$')
_PY_DOCSTR_RE = re.compile(r'^\s*[ubrUBR]+(\'\'\'|""").*$')
def patch_python_shebang(filename, scriptlines):
    """
    Replaces a Python shebang with a multi

    The shebang is *assumed* to be on the form "/absolute/path/to/python";
    the caller should check for forms such as "/usr/bin/env python" first.
    The shebang is replaced with a "multi-line"
    shebang, using the property that::

        #/bin/sh
        "true" '''\' SHELL_SCRIPT
        '''
        PYTHON_SCRIPT

    is both executable by a Unix shell and by Python. The the Unix
    shell script is seen as the module docstring by Python, so we must
    also patch up the module docstring by prepending '__doc__ = '.

    Parameters
    ----------

    filename : str
        Filename of script. Not modified (by this function), but used to
        access the relative path.

    scriptlines : list of str
        List of lines in the script; each line includes terminating newline

    Returns
    -------

    scriptlines : list of str
        List of lines of modified script; each line including terminating newline
    """
    shebang = scriptlines[0]
    del scriptlines[0] # remove old shebang

    # prepend module docstring with "__doc__ = "
    for i, line in enumerate(scriptlines):
        if _PY_DOCSTR_RE.match(line):
            scriptlines[i] = '__doc__ = ' + scriptlines[i]
        if not _PY_EMPTY_RE.match(line):
            break

    launcher_script = _get_launcher(filename, shebang)
    preamble = dedent("""\
    #!/bin/sh
    "true" '''\\';%s
    ''' # end multi-line shebang, see hashdist.core.build_tools
    """) % pack_sh_script(launcher_script)

    lines = preamble.splitlines(True) + scriptlines
    lines = add_modelines(lines, 'python')
    return lines

def add_modelines(scriptlines, language):
    """Sets file metadata/modelines so that editors will treat it correctly

    Since setting the shebang destroys auto-detection for scripts, we add
    mode-lines for Emacs and vi.
    """
    shebang = scriptlines[0:1]
    body = scriptlines[1:]
    if not any('-*-' in line for line in scriptlines):
        emacs_modeline = ['# -*- mode: %s -*-\n' % language]
    else:
        emacs_modeline = []
    if not any(' vi:' in line for line in scriptlines):
        vi_modeline = ['# vi: filetype=python\n']
    else:
        vi_modeline = []
    return shebang + emacs_modeline + body + vi_modeline
