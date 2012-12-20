"""
:mod:`hashdist.core.links` --- Link creation tool
==================================================

:func:`execute_links_dsl` takes a set of rules in a mini-language and
uses it to create (a potentially large number of) links.

The following rules creates links to everything in "/usr/bin", except
for "/usr/bin/gcc-4.6" which is copied (though it could be achieved
more easily with the `force` flag)::

  [
    {
      "action": "copy",
      "source": "/usr/bin/gcc-4.6",
      "target": "$ARTIFACT/bin/gcc-4.6"
    },
    {
      "action": "exclude",
      "select": "/usr/bin/gcc-4.6",
    },
    {
      "action": "symlink",
      "select": "/usr/bin/*",
      "prefix": "/usr",
      "target": "$ARTIFACT"
    }
    
  ]

Rules are applied in order.

**action**:
  One of "symlink", "copy", "exclude". Other types may be added
  later.

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

**force**:
  If present and `True`, overwrite target.

"""

import os
from os.path import join as pjoin
import shutil
import errno
from string import Template

from .ant_glob import glob_files

def expandtemplate(s, env):
    return Template(s).substitute(env)

def silent_makedirs(path):
    """like os.makedirs, but does not raise error in the event that the directory already exists"""
    try:
        os.makedirs(path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

def silent_unlink(path):
    """like os.unlink but does not raise error if the file does not exist"""
    try:
        os.unlink(path)
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise

_ACTIONS = {'symlink': os.symlink, 'copy': shutil.copyfile}

def _put_actions(makedirs_cache, action_name, force, source, dest, actions):
    path, basename = os.path.split(dest)
    if path != '' and path not in makedirs_cache:
        actions.append((silent_makedirs, path))
        makedirs_cache.add(path)
    if force:
        actions.append((silent_unlink, dest))
    try:
        actions.append((_ACTIONS[action_name], source, dest))
    except KeyError:
        raise ValueError('Unknown action: %s' % action_name)

    
def _glob_actions(rule, excluded, makedirs_cache, env, actions):
    select = expandtemplate(rule['select'], env)
    selected = set(glob_files(select, ''))
    selected.difference_update(excluded)
    if len(selected) == 0:
        return

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
            _put_actions(makedirs_cache, action_name, rule.get('force', False),
                         p, target, actions)

def _single_action(rule, excluded, makedirs_cache, env, actions):
    source = expandtemplate(rule['source'], env)
    if source in excluded:
        return
    if rule['action'] == 'exclude':
        excluded.add(source)
    else:
        target = expandtemplate(rule['target'], env)
        _put_actions(makedirs_cache, rule['action'], rule.get('force', False),
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


def execute_links_dsl(rules, env={}):
    """Executes the links DSL for linking/copying files
    
    The input is a set of rules which will be applied in order. The
    rules are documented above.
    
    Parameters
    ----------

    spec : list
        List of rules as described above.

    env : dict
        Environment to use for variable substitution.
    """
    for action in dry_run_links_dsl(rules, env):
        try:
            action[0](*action[1:])
        except OSError, e:
            # improve error message to include operation attempted
            raise OSError(e.errno, str(e) + " in %s%r" %
                          (action[0].__name__, action[1:]))

