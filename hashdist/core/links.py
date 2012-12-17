import os
from os.path import join as pjoin
import shutil
import errno
from string import Template

def expandtemplate(s, env):
    return Template(s).substitute(env)

def silent_makedirs(path):
    """like os.makedirs, but does not raise error in the event that the directory already exists"""
    try:
        os.makedirs(path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

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
        select = expandtemplate(rule['select'], env)

        if select in excluded:
            continue

        action_name = rule['action']
        if action_name == 'exclude':
            excluded.add(select)
        else:
            target = expandtemplate(rule['target'], env)
            prefix = rule.get('prefix', None)

            if prefix is not None:
                prefix = expandtemplate(prefix, env)
                if prefix != '' and not prefix.endswith(os.path.sep):
                    prefix += os.path.sep
                if not select.startswith(prefix):
                    raise ValueError('%s does not start with %s' % (select, prefix))
                remainder = select[len(prefix):]
                target = pjoin(target, remainder)

            path, basename = os.path.split(target)
            if path != '' and path not in makedirs_cache:
                actions.append((silent_makedirs, path))
                makedirs_cache.add(path)

            if action_name == 'symlink':
                action = (os.symlink, select, target)
            elif action_name == 'copy':
                action = (shutil.copyfile, select, target)
            else:
                raise ValueError('Unknown action: %s' % action_name)

            actions.append(action)
        
    
    return actions


def execute_links_dsl(rules, env={}):
    """Executes the links DSL for linking/copying files
    
    The input is a set of rules which will be applied in order. Example
    of rule::

        {"action": "symlink",
         "select": "/bin/cp",
         "prefix": "/",
         "target": "$ARTIFACT"}

    `action` can be either "symlink", "copy", "exclude". `select` is the object
    to link to (the plan is to add `glob` too).

    If `prefix` is present, then the prefix will be stripped and
    the rest will be appended to `target`, e.g., in the example above,
    the symlink ``$ARTIFACT/bin/cp`` will be created. If `prefix` is not
    present, target is used directly (so if `prefix` is remove above,
    ``$ARTIFACT`` is expected to not exist and will be created as a symlink
    to ``/bin/cp``). An empty `prefix` may make sense  (if `select` is relative)
    and is distinct from a `None` prefix.

    .. note::
    
        `select` and `prefix` should either both be absolute paths or
        both be relative paths

    Parameters
    ----------

    spec : list
        List of rules as described above.

    env : dict
        Environment to use for variable substitution.
    """
    for action in dry_run_links_dsl(rules, env):
        action[0](*action[1:])

