"""
:mod:`hashdist.core.links` --- Link creation tool
==================================================

:func:`execute_links_dsl` takes a set of rules in a mini-language and
uses it to create (a potentially large number of) links.

The following rules creates links to everything in "/usr/bin", except
for "/usr/bin/gcc-4.6" which is copied (though it could be achieved
more easily with the `overwrite` flag)::

  [
    {
      "action": "copy",
      "source": "/usr/bin/gcc-4.6",
      "target": "$ARTIFACT/bin/gcc-4.6"
    },
    {
      "action": "exclude",
      "select": ["/usr/bin/gcc-4.6", "/something/else/too/**"]
    },
    {
      "action": "symlink",
      "select": "/usr/bin/*",
      "prefix": "/usr",
      "target": "$ARTIFACT"
    }

  ]

Rules are executed in order. If a target file already exists, nothing
happens.


**action**:
  One of "symlink", "absolute_symlink", "relative_symlink", "copy",
  "exclude", "launcher". Other types may be added later.

  * *absolute_symlink* creates absolute symlinks. Just *symlink* is an
    alias for absolute symlink.
  * *relative_symlink* creates relative symlinks
  * *copy* copies contents and mode (``shutil.copy``)
  * *exclude* makes sure matching files are not considered in rules below
  * *launcher*, see :func:`make_launcher`

**select**, **prefix**:
  `select` contains glob of files to
  link/copy/exclude. This is in ant-glob format (see
  :mod:`hashdist.core.ant_glob`). If `select` is given and `action` is
  not `exclude`, one must also supply a `prefix` (possibly empty
  string) which will be stripped from each matching path, before
  recreating the same hierarchy beneath `target`.

  Variable substitution is performed both in `select` and `prefix`.
  `select` and `prefix` should either both be absolute paths or
  both be relative paths

**source**:
  Provide an exact filename instead of a glob. In this case `target`
  should refer to the exact filename of the resulting link/copy.

**target**:
  Target filename (`source` is used) or directory (`select` is used).
  Variable substitution is performed.

**dirs**:
  If present and `True`, symlink matching directories, not only files.
  Only takes effect for `select`; `source` always selectes dirs.

**overwrite**:
  If present and `True`, overwrite target.
"""

import sys
import os
from os.path import join as pjoin
import shutil
import errno
import logging
from string import Template

from .fileutils import (silent_makedirs, silent_unlink, silent_relative_symlink,
                        silent_absolute_symlink, silent_copy)

from .ant_glob import ant_iglob


def expandtemplate(s, env):
    return Template(s).substitute(env)

def make_launcher(src, dst, launcher_program):
    """
    The 'launcher' action. This is a general tool for processing
    bin-style directories where the binaries must have a "fake"
    argv[0] target (read: Python). The action depends on the source type:

    program (i.e., executable not starting with #!):
        Set up as symlink to "launcher", which is copied into same directory;
        and "$dst.link" is set up to point relatively to "$src".

    symlink:
        Copy it verbatim. Thus, e.g., ``python -> python2.7`` will point to the
        newly, "launched-ified" ``python2.7``.

    other (incl. scripts):
        Symlink relatively to it.
    """
    dstdir = os.path.dirname(dst)

    type = 'other'
    if os.path.islink(src):
        type = 'symlink'
    elif os.stat(src).st_mode & 0o111:
        with open(src) as f:
            if f.read(2) != '#!':
                type = 'program'

    if type in 'symlink':
        os.symlink(os.readlink(src), dst)
    elif type == 'program':
        if launcher_program is None or not os.path.exists(launcher_program):
            raise TypeError('Did not provide path to "launcher" program')
        dst_launcher = pjoin(dstdir, 'launcher')
        if not os.path.exists(dst_launcher):
            shutil.copy(launcher_program, dst_launcher)
        with open(dst + '.link', 'w') as f:
            f.write(os.path.relpath(src, dstdir))
        os.symlink('launcher', dst)
    else:
        os.symlink(os.path.relpath(src, dstdir), dst)


_ACTIONS = {'symlink': silent_absolute_symlink,
            'relative_symlink': silent_relative_symlink,
            'absolute_symlink': silent_absolute_symlink,
            'copy': silent_copy,
            'launcher': make_launcher}

def _put_actions(makedirs_cache, action_name, overwrite, source, dest, actions):
    path, basename = os.path.split(dest)
    if path != '' and path not in makedirs_cache:
        actions.append((silent_makedirs, path))
        makedirs_cache.add(path)
    if overwrite:
        actions.append((silent_unlink, dest))
    try:
        actions.append((_ACTIONS[action_name], source, dest))
    except KeyError:
        raise ValueError('Unknown action: %s' % action_name)


def _glob_actions(rule, excluded, makedirs_cache, env, actions):
    select = rule['select']
    if not isinstance(select, (list, tuple)):
        select = [select]
    selected = set()
    for pattern in select:
        pattern = expandtemplate(pattern, env)
        selected.update(ant_iglob(pattern, '', include_dirs=rule.get('dirs', False)))
    selected.difference_update(excluded)
    if len(selected) == 0:
        return
    selected = list(selected)
    selected.sort() # easier on the unit tests...

    action_name = rule['action']
    if action_name == 'exclude':
        excluded.update(selected)
    else:
        if 'prefix' not in rule:
            raise ValueError('When using select one must also supply prefix')
        target_prefix = expandtemplate(rule['target'], env)
        prefix = expandtemplate(rule['prefix'], env)
        if prefix != '' and not prefix.endswith(os.path.sep):
            prefix += os.path.sep

        for p in selected:
            if not p.startswith(prefix):
                raise ValueError('%s does not start with %s' % (p, prefix))
            remainder = p[len(prefix):]
            target = pjoin(target_prefix, remainder)
            _put_actions(makedirs_cache, action_name, rule.get('overwrite', False),
                         p, target, actions)

def _single_action(rule, excluded, makedirs_cache, env, actions):
    source = expandtemplate(rule['source'], env)
    if source in excluded:
        return
    if rule['action'] == 'exclude':
        excluded.add(source)
    else:
        target = expandtemplate(rule['target'], env)
        _put_actions(makedirs_cache, rule['action'], rule.get('overwrite', False),
                     source, target, actions)

def dry_run_links_dsl(rules, env={}):
    """Turns a DSL for creating links/copying files into a list of actions to be taken.

    This takes into account filesystem contents and current directory
    at the time of call.

    See :func:`execute_links_dsl` for information on the DSL.

    Parameters
    ----------

    rules : list
        List of rules as described in :func:`execute_links_dsl`.

    env : dict
        Environment to use for variable substitution

    Returns
    -------

    actions : list
        What actions should be performed as a list of (func,) + args_to_pass,
        where `func` is one of `os.symlink`, :func:`silent_makedirs`,
        `shutil.copyfile`.
    """
    assert os.path.sep == '/'
    actions = []
    excluded = set()
    makedirs_cache = set()
    for rule in rules:
        if 'select' in rule:
            _glob_actions(rule, excluded, makedirs_cache, env, actions)
        else:
            _single_action(rule, excluded, makedirs_cache, env, actions)

    return actions


def execute_links_dsl(rules, env={}, launcher_program=None, logger=None):
    """Executes the links DSL for linking/copying files

    The input is a set of rules which will be applied in order. The
    rules are documented above.

    Parameters
    ----------

    spec : list
        List of rules as described above.

    env : dict
        Environment to use for variable substitution.

    launcher_program : str or None
        If the 'launcher' action is used, the path to the launcher executable
        must be provided.

    logger : Logger or ``None`` (default)

    """
    if logger is None:
        logger = logging.getLogger('null_logger')
    actions = dry_run_links_dsl(rules, env)
    for action in actions:
        action_desc = "%s%r" % (action[0].__name__, action[1:])
        try:
            if action[0] is make_launcher:
                make_launcher(*action[1:], launcher_program=launcher_program)
            else:
                action[0](*action[1:])
            logger.debug(action_desc)
        except OSError, e:
            # improve error message to include operation attempted
            msg = str(e) + " in " + action_desc
            logger.error(msg)
            exc_type, exc_val, exc_tb = sys.exc_info()
            raise OSError, OSError(e.errno, msg), exc_tb

