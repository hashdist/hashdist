"""
Execution environment for ``build.json`` and ``install.json``.
"""

import os
from os.path import join as pjoin
import subprocess
from glob import glob
from string import Template
from pprint import pformat
import errno

from .common import InvalidBuildSpecError, BuildFailedError, working_directory

def substitute(x, env):
    return Template(x).substitute(env)

def get_artifact_dependencies_env(build_store, virtuals, dependencies):
    """
    Sets up an environment for a build spec, given the `dependencies`
    property of the document (see :mod:`hashdist.core.build_store`).

    Parameters
    ----------

    build_store : BuildStore object
        Build store to look up artifacts in

    virtuals : dict
        Maps virtual artifact IDs (including "virtual:" prefix) to concrete
        artifact IDs.

    dependencies : list of dict
        The `dependencies` property of the build spec, see above link.

    Returns
    -------

    env : dict
        Environment variables to set containing variables for the dependency
        artifacts
    """
    # do a topological sort of dependencies
    problem = [(dep['id'], dep['before']) for dep in dependencies]
    sorted_ids = stable_topological_sort(problem)
    order = dict((id, i) for i, id in enumerate(sorted_ids))
    dependencies = sorted(dependencies, key=lambda dep: order[dep['id']])
    
    # just need something that has the right depth relative to the cache_path to
    # use for os.path.relpath
    prototype_lib_dir = pjoin(build_store.artifact_store_dir,
                              '__name', '__version', '__hash', 'lib')

    env = {}
    # Build the environment variables due to dependencies, and complain if
    # any dependency is not built

    PATH = []
    HDIST_CFLAGS = []
    HDIST_LDFLAGS = []
    
    for dep in dependencies:
        dep_ref = dep['ref']
        dep_id = dep['id']

        # Resolutions of virtual dependencies should be provided by the user
        # at the time of build
        if dep_id.startswith('virtual:'):
            try:
                dep_id = virtuals[dep_id]
            except KeyError:
                raise ValueError('build spec contained a virtual dependency "%s" that was not '
                                 'provided' % dep_id)

        dep_dir = build_store.resolve(dep_id)
        if dep_dir is None:
            raise InvalidBuildSpecError('Dependency "%s"="%s" not already built, please build it first' %
                                        (dep_ref, dep_id))

        if dep_ref is not None:
            env[dep_ref] = dep_dir
            env['%s_id' % dep_ref] = dep_id

        if dep['in_path']:
            bin_dir = pjoin(dep_dir, 'bin')
            if os.path.exists(bin_dir):
                PATH.append(bin_dir)

        if dep['in_hdist_compiler_paths']:
            libdirs = glob(pjoin(dep_dir, 'lib*'))
            if len(libdirs) == 1:
                HDIST_LDFLAGS.append('-L' + libdirs[0])
                HDIST_LDFLAGS.append('-Wl,-rpath,' + libdirs[0])
            elif len(libdirs) > 1:
                raise InvalidBuildSpecError('in_hdist_compiler_paths set for artifact %s with '
                                            'more than one library dir (%r)' % (dep_id, libdirs))

            incdir = pjoin(dep_dir, 'include')
            if os.path.exists(incdir):
                HDIST_CFLAGS.append('-I' + incdir)

    env['PATH'] = os.path.pathsep.join(PATH)
    env['HDIST_CFLAGS'] = ' '.join(HDIST_CFLAGS)
    env['HDIST_LDFLAGS'] = ' '.join(HDIST_LDFLAGS)
    return env
    

def stable_topological_sort(problem):
    """Topologically sort items with dependencies

    The concrete algorithm is to first identify all roots, then
    do a DFS. Children are visited in the order they appear in
    the input. This ensures that there is a predictable output
    for every input. If no constraints are given the output order
    is the same as the input order.

    The items to sort must be hashable and unique.

    Parameters
    ----------
    
    problem : list of (obj, before_set)
        `obj` are the items to be topologically sorted, while `before_lst`
        is an iterable of constraints; `obj` is required to come before the
        objects listed in `before_set` in the output.

    Returns
    -------

    solution : list
        The input `obj` in a possibly different order
    """
    # record order to use for sorting `before`
    order = {}
    for i, (obj, before) in enumerate(problem):
        if obj in order:
            raise ValueError('%r appears twice in input' % obj)
        order[obj] = i

    # turn into dict-based graph, and find the roots
    graph = {}
    roots = set(order.keys())
    for obj, before in problem:
        graph[obj] = sorted(before, key=order.__getitem__)
        roots.difference_update(before)

    result = []

    def dfs(node):
        if node not in result:
            result.append(node)
            for child in graph[node]:
                dfs(child)

    for obj in sorted(roots, key=order.__getitem__):
        dfs(obj)

    # cycles will have been left entirely out at this point
    if len(result) != len(problem):
        raise ValueError('provided constraints forms a graph with cycles')

    return result
    
def run_script_in_sandbox(logger, script, env, cwd):
    """
    Executes a command description given a JSON-like description.
    `doc` should describe the commands to be executed as described
    in :mod:`hashdist.core.build_store`; the relevant keys
    are *dependencies*, *commands*, *env*.

    The "hdist" command is treated as a special-case and run in the
    same process, which a) facilitates bootstrapping, and b) makes
    logging nicer. However, the "hdist" command will not be available
    to shell scripts launched etc. without further measures
    (:mod:`hashdist.core.hdist_recipe` will help with setting up
    the `hdist` command in PATH properly).

    Parameters
    ----------
    logger : Logger

    script : list
        List of commands ("commands" key in build spec)

    env : dict
        Environment variables to use

    cwd : str
        cwd to use

    """
    if not isinstance(script, (list, tuple)):
        raise TypeError('commands is not a list')
    for command_lst in script:
        # substitute variables
        command_lst = [substitute(x, env) for x in command_lst]
        # command-specific environment -- strings containing = before the command
        command_lst = list(command_lst)
        command_env = dict(env)
        command_cwd = cwd
        while '=' in command_lst[0]:
            key, value = command_lst[0].split('=')
            if key == 'CWD':
                command_cwd = value
            else:
                command_env[key] = value
            del command_lst[0]
                
        # log the command to run
        logger.info('running %r' % command_lst)
        logger.debug('cwd: ' + cwd)
        logger.debug('environment:')
        for line in pformat(env).splitlines():
            logger.debug('  ' + line)

        if command_lst[0] == 'hdist':
            # special case the 'hdist' command and run it in the same
            # process; note that hashdist.core.hdist_recipe can be used to make
            # 'hdist' available to sub-shells
            from ..cli import main as cli_main
            with working_directory(cwd):
                cli_main(command_lst, command_env, logger)
        else:
            logged_check_call(logger, command_lst, command_env, command_cwd)
        logger.info('success')
    
def logged_check_call(logger, command_lst, env, cwd):
    """
    Similar to subprocess.check_call, but redirects all output to a Logger instance.
    Also raises BuildFailedError on failures.
    """
    try:
        proc = subprocess.Popen(command_lst,
                                cwd=cwd,
                                env=env,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
    except OSError, e:
        if e.errno == errno.ENOENT:
            logger.error('command "%s" not found in PATH' % command_lst[0])
            raise BuildFailedError('command "%s" not found in PATH (cwd: "%s")' %
                                   (command_lst[0], cwd), cwd)
        else:
            raise
    proc.stdin.close()
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        if line[-1] == '\n':
            line = line[:-1]
        logger.debug(line)
    retcode = proc.wait()
    if retcode != 0:
        logger.error("command failed with code %d, cwd=%s" %\
                     (retcode,  cwd))
        raise BuildFailedError('Build command failed with code %d (cwd: "%s")' %
                               (retcode, cwd), cwd)
