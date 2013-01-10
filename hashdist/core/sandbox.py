"""
:mod:`hashdist.core.sandbox` --- Sandboxed job execution
========================================================

Executes a set of commands in a controlled environment. While this
should usually be used to launch a real script interpreter, a
bare-bones script language in JSON is provided to perform the script
launch. This is primarily because it only takes a few lines of code to
implement, and offers a cross-platform solution (as opposed to, e.g.,
always using the system shell to launch a process; Python would be
difficult too as there'd always be a different Python version
available).

Job specification
-----------------

The job spec is a document that contains what's needed to set up a
controlled environment and run the commands. The idea is to be able
to reproduce a job run, and hash the job spec. Example:

.. code-block:: python
    
    {
        "import" : [
            {"ref": "bash", "id": "virtual:bash"},
            {"ref": "make", "id": "virtual:gnu-make/3+"},
            {"ref": "zlib", "id": "zlib/2d4kh7hw4uvml67q7npltyaau5xmn4pc"},
            {"ref": "unix", "id": "virtual:unix"},
            {"ref": "gcc", "before": ["virtual:unix"], "id": "gcc/jonykztnjeqm7bxurpjuttsprphbooqt"}
         ],
         "env" : {
            "FOO" : "bar"
         },
         "env_nohash" : {
            "NCORES": "4"
         }
         "script" : [
            [
              ["CFLAGS=$(pkgcfg", "--cflags", "foo", ")"],
              ["./configure", "--prefix=$ARTIFACT", "--foo-setting=$FOO"]
            ],
            ["make", "-j$NCORES"],
            ["make", "install"]
         ],
    }


.. warning::
   The job spec may not completely specify the job
   environment because it is usually a building block of other specs
   which may imply certain additional environment variables. E.g.,
   during a build, ``$ARTIFACT`` and ``$BUILD`` are defined even if
   they are never mentioned here.


**import**:
    The artifacts needed in the environment for the run. After the
    job has run they have no effect (i.e., they do not
    affect garbage collection or run-time dependencies of a build,
    for instance). The list specifies an unordered set; `before` can be used to
    specify order.

    * **id**: The artifact ID. If the value is prepended with
      ``"virtual:"``, the ID is a virtual ID, used so that the real
      one does not contribute to the hash. See section on virtual
      imports below.

    * **ref**: A name to use to inject information of this dependency
      into the environment. Above, ``$zlib`` will be the
      absolute path to the ``zlib`` artifact, and ``$zlib_id`` will be
      the full artifact ID. This can be set to `None` in order to not
      set any environment variables for the artifact.

    * **before**: List of artifact IDs. Adds a constraint that this
      dependency is listed before the dependencies listed in all paths.

    * **in_env**: Whether to add the environment variables of the
      artifact (typically ``$PATH`` if there is a ``bin`` sub-directory
      and so on). Otherwise the artifact can only be used through the
      variables ``ref`` sets up. Defaults to `True`.

**script**:
    Executed to perform the build. See below.

**env**:
    Environment variables. The advantage to using this over just defining
    them in the `script` section is that they are automatically unordered
    w.r.t. hashing.

**env_nohash**:
    Same as `env` but entries here do not contribute to the hash. Should
    only be used when one is willing to trust that the value does not
    affect the build result in any way. E.g., parallelization flags,
    paths to manually downloaded binary installers, etc.


The sandbox environment
-----------------------

Standard output (except with "<=", see below) and error of all
commands are both re-directed to a Logger instance passed in
by the sandbox user. There is no stdin (it's set to a closed pipe).

The build environment variables are wiped out and the variables in `env`
and `env_nohash` set. Then, each of the `import`-ed artifacts are
visited and (if `in_env` is not set to `False`) the following variables
are affected:

**PATH**:
    Set to point to the ``bin``-sub-directories of imports.

**HDIST_CFLAGS**:
    Set to point to the ``include``-sub-directories of imports.

**HDIST_LDFLAGS**:
    Set to point to the ``lib*``-sub-directories of imports.

    Note that it is almost impossible to inject a relative RPATH; even
    if one manages to escaoe $ORIGIN properly for the build system,
    any auto-detection will tend to prepend absolute RPATHs
    anyway. See experiences in mess.rst. If on wishes '$ORIGIN' in the
    RPATH then ``patchelf`` should be used.

**HDIST_VIRTUALS**:
    The mapping of virtual artifacts to concrete artifact IDs that has
    been used. Format by example:
    ``virtual:unix=unix/r0/KALiap2<...>;virtual:hdist=hdist/r0/sLt4Zc<...>``

Mini script language
--------------------

The scripting language should only be used for 'launching', not for
complicated things, and intentionally does not contain any control
flow. While it is modelled after Bash to make it familiar to read, it
is *not* in any way Bash, the implementation is entirely in this Python
module.

The most important feature is that parsing is at a minimum, since most
of the structure is already present in the JSON structure. There's
no quoting, one document string is always passed as a single argument.

Example script::

    "script" : [
        [
            ["LIB=foo"],
            ["CFLAGS=$(pkgcfg", "--cflags", "$LIB", ")"],
            ["./configure", "--prefix=$ARTIFACT", "--foo-setting=$FOO"]
        ],
        ["make", "-j$NCORES"],
        ["make", "install"]
    ]

Rules:

 * Lists of strings are a command to execute, lists of lists is a scope
   (i.e., above, ``$CFLAGS`` is only available to the ``./configure``
   command).

 * Variable substitution is performed on all strings (except, currently,
   assignment left-hand-sides) using the ``$CFLAGS`` and ``${CFLAGS}``
   syntax. ``\$`` is an escape for ``$`` (but ``\`` not followed by ``$``
   is not currently an escape).

 * The ``["executable", "arg1", ...]``: First string is command to execute, all strings
   are used directly as argv (so no quoting etc.).

 * The ``["VAR=str"]`` command sets an environment variable

 * The ``["VAR=$(command", "arg1", ..., ")"]``: Assigns the stdout of the command
   to the variable. The result has leading and trailing whitespace stripped
   but is otherwise untouched. The trailing ``")"`` must stand by itself (and does not
   really mean anything except as to balance the opening visually).

The ``hdist`` command is given special treatment and is executed in the
same process, with logging set up to the logger of the sandbox.
In addition to what is listed in ``hdist --help``, the following special
command is available for interacting with the sandbox:

 * ``hdist logpipe HEADING LEVEL``: Creates a new Unix FIFO and prints
   its name to standard output (it will be removed once the job
   terminates). The sandbox runner will poll the pipe and print
   anything written to it nicely formatted to the log with the given
   heading and log level (the latter is one of ``DEBUG``, ``INFO``,
   ``WARNING``, ``ERROR``).

.. note::

    ``hdist`` is not automatically available in the environment in general
    (in launched scripts etc.), for that, see :mod:`hashdist.core.hdist_recipe`.
    ``hdist logpipe`` is currently not supported outside of the sandbox script
    at all (this could be supported through RPC with the sandbox, but the
    gain seems very slight).



Virtual imports
---------------

Some times one do not wish some imports to become part of the hash.
For instance, if the ``cp`` tool is used in the job, one is normally
ready to trust that the result wouldn't have been different if a newer
version of the ``cp`` tool was used instead.

Virtual imports, such as ``virtual:unix`` in the example above, are
used so that the hash depends on a user-defined string rather than the
artifact contents. If a bug in ``cp`` is indeed discovered, one can
change the user-defined string (e.g, ``virtual:unix/r2``) in order to
change the hash of the job desc.

.. note::
   One should think about virtual dependencies merely as a tool that gives
   the user control (and responsibility) over when the hash should change.
   They are *not* the primary mechanism for providing software
   from the host; though software from the host will sometimes be
   specified as virtual dependencies.

Reference
---------

"""

import os
from os.path import join as pjoin
import shutil
import subprocess
from glob import glob
from string import Template
from pprint import pformat
import tempfile
import errno
import select

from ..hdist_logging import WARNING, INFO, DEBUG

from .common import InvalidBuildSpecError, BuildFailedError, working_directory



def run_job(logger, build_store, job_spec, env, virtuals, cwd):
    """Runs a job in a sandbox, according to rules documented above.

    Parameters
    ---------

    logger : Logger

    build_store : BuildStore
        BuildStore to find referenced artifacts in.

    job_spec : document
        See above

    env : dict
        Initial environment variables; entries from the job spec may
        overwrite these.

    virtuals : dict
        Maps virtual artifact to real artifact IDs.

    cwd : str
        The starting working directory of the script. Currently this
        cannot be changed (though a ``cd`` command may be implemented in
        the future if necesarry)

    Returns
    -------

    out_env: dict
        The environment with modifications done by "root scope" of
        the script (modifications done in nested scopes are intentionally
        discarded).
    """
    job_spec = canonicalize_job_spec(job_spec)
    env = dict(env)
    env.update(job_spec['env'])
    env.update(job_spec['env_nohash'])
    env.update(get_imports_env(build_store, virtuals, job_spec['import']))
    rpc_dir = tempfile.mkdtemp(prefix='hdist-sandbox-')
    try:
        out_env = run_script(logger, job_spec['script'], env, cwd, rpc_dir)
    finally:
        shutil.rmtree(rpc_dir)
    return out_env

def canonicalize_job_spec(job_spec):
    """Returns a copy of job_spec with default values filled in.

    May also in time perform validation.
    """
    job_spec = dict(job_spec)
    job_spec.setdefault("import", [])
    job_spec.setdefault("env", {})
    job_spec.setdefault("env_nohash", {})
    job_spec.setdefault("script", [])
    return job_spec
    
def substitute(x, env):
    """
    Substitute environment variable into a string following the rules
    documented above.

    Raises KeyError if an unreferenced variable is not present in env
    (``$$`` always raises KeyError)
    """
    if '$$' in x:
        # it's the escape character of string.Template, hence the special case
        raise KeyError('$$ is not allowed (no variable can be named $): %s' % x)
    x = x.replace(r'\$', '$$')
    return Template(x).substitute(env)

def get_imports_env(build_store, virtuals, imports):
    """
    Sets up environment variables given by the 'import' section
    of the job spec (see above).

    Parameters
    ----------

    build_store : BuildStore object
        Build store to look up artifacts in

    virtuals : dict
        Maps virtual artifact IDs (including "virtual:" prefix) to concrete
        artifact IDs.

    imports : list
        'import' section of job spec document as documented above.

    Returns
    -------

    env : dict
        Environment variables to set containing variables for the dependency
        artifacts
    """
    # do a topological sort of imports
    imports = stable_topological_sort(imports)
    
    env = {}
    # Build the environment variables due to imports, and complain if
    # any dependency is not built

    PATH = []
    HDIST_CFLAGS = []
    HDIST_LDFLAGS = []
    
    for dep in imports:
        dep_ref = dep['ref']
        dep_id = dep['id']

        # Resolutions of virtual imports should be provided by the user
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
                HDIST_LDFLAGS.append('-Wl,-R,' + libdirs[0])
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
    
    problem : list of dict(id=..., before=..., ...)
        Each object is a dictionary which is preserved to the output.
        The `id` key is each objects identity, and the `before` is a list
        of ids of objects that a given object must come before in
        the ordered output.

    Returns
    -------

    solution : list
        The input `problem` in a possibly different order
    """
    # record order to use for sorting `before`
    id_to_obj = {}
    order = {}
    for i, obj in enumerate(problem):
        if obj['id'] in order:
            raise ValueError('%r appears twice in input' % obj['id'])
        order[obj['id']] = i
        id_to_obj[obj['id']] = obj

    # turn into dict-based graph, and find the roots
    graph = {}
    roots = set(order.keys())
    for obj in problem:
        graph[obj['id']] = sorted(obj['before'], key=order.__getitem__)
        roots.difference_update(obj['before'])

    result = []

    def dfs(obj_id):
        if obj_id not in result:
            result.append(obj_id)
            for child in graph[obj_id]:
                dfs(child)

    for obj_id in sorted(roots, key=order.__getitem__):
        dfs(obj_id)

    # cycles will have been left entirely out at this point
    if len(result) != len(problem):
        raise ValueError('provided constraints forms a graph with cycles')

    return [id_to_obj[obj_id] for obj_id in result]
    
def run_script(logger, script, env, cwd, rpc_dir):
    """Executes the 'script' part of the job spec.

    This is a building block of :func:`run_job`.

    Parameters
    ----------

    logger : Logger

    script : document
        The 'script' part of the job spec

    env : dict
        The starting process environment

    cwd : str
        The working directory for the script (stays the same for all commands)

    rpc_dir : str
        A temporary directory on a local filesystem. Currently used for creating
        pipes with the "hdist logpipe" command.

    Returns
    -------

    out_env : dict
        The environment as modified by the script.
    """
    env = dict(env)
    for script_line in script:
        # substitute variables ina all strings
        if len(script_line) == 0:
            pass
        elif isinstance(script_line[0], list):
            # sub-scope; recurse and discard the modified environment
            run_script(logger, script_line, env, cwd, rpc_dir)
        else:
            # command
            cmd = script_line[0]
            if '=$(' in cmd:
                varname, cmd = cmd.split('=$(')
                if script_line[-1] != ')':
                    raise ValueError("opens with $( but no closing ): %r" % script_line)
                del script_line[-1]
                action = 'capture'
            elif '=' in cmd:
                varname, cmd = cmd.split('=')
                action = 'assign'
                if len(script_line) > 1:
                    raise ValueError('assignment takes no extra arguments')
            else:
                action = 'spawn'
            cmd = substitute(cmd, env)
            args = [substitute(x, env) for x in script_line[1:]]

            if action == 'assign':
                env[varname] = cmd
            else:
                # spawn command; first log our environment
                logger.info('running %r' % script_line)
                logger.debug('cwd: ' + cwd)
                logger.debug('environment:')
                for line in pformat(env).splitlines():
                    logger.debug('  ' + line)

                try:
                    out = run_command(logger, [cmd] + args, env, cwd, rpc_dir,
                                      capture_stdout=(action == 'capture'))
                except subprocess.CalledProcessError, e:
                    logger.error("command failed (code=%d); raising" % e.returncode)
                    raise
                except:
                    logger.error("'hdist' command failed; raising")
                    raise
                if action == 'capture':
                    env[varname] = out.strip()
                logger.info('success')

def run_command(logger, command_lst, env, cwd, rpc_dir, capture_stdout):
    """Runs a single command of the sandbox script

    This mainly takes care of stream re-direction and special handling
    of the hdist command.

    Raises `subprocess.CalledProcessError` on non-zero return code,
    except when running ``hdist`` in-process in which case exception
    is simply propagated.
    

    Parameters
    ----------

    logger : Logger
    
    command_lst : list
        Passed dirctly on to Popen

    env : dict
        Process environment

    cwd : str
        Process cwd

    rpc_dir : str
        Directory to create log pipes in for "hdist logpipe"

    capture_stdout : bool
        If `False`, redirect stdout to logger, otherwise return it.

    Returns
    -------
        
    stdout : str or None
        Either captured stdout, or `None`, depending on `get_stdout`
        
    """
    if command_lst[0] == 'hdist' and len(command_lst) >= 2 and command_lst[1] == 'logpipe':
        # 'hdist logpipe' special case
        1/0
    elif command_lst[0] == 'hdist':
        # run hdist cli in-process special case the 'hdist' command and run it in the same
        # process
        from ..cli import main as cli_main
        # do not emit INFO-messages from sub-command unless level is DEBUG
        old_level = logger.level
        if logger.level > DEBUG:
            logger.level = WARNING
        try:
            with working_directory(cwd):
                cli_main(command_lst, env, logger)
        finally:
            logger.level = old_level
    else:
        return logged_check_call(logger, command_lst, env, cwd, capture_stdout)
    
def logged_check_call(logger, command_lst, env, cwd, capture_stdout):
    """
    Similar to subprocess.check_call, but redirects all output to a Logger instance.
    Also raises BuildFailedError on failures. See usage in run_command for more info.
    """
    try:
        proc = subprocess.Popen(command_lst,
                                cwd=cwd,
                                env=env,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    except OSError, e:
        if e.errno == errno.ENOENT:
            logger.error('command "%s" not found in PATH' % command_lst[0])
            raise BuildFailedError('command "%s" not found in PATH (cwd: "%s")' %
                                   (command_lst[0], cwd), cwd)
        else:
            raise
    proc.stdin.close()
    poller = select.poll()
    stdout = proc.stdout
    streams = [proc.stdout, proc.stderr]
    fd_to_stream = dict((stream.fileno(), stream) for stream in streams)
    for fd in fd_to_stream.keys():
        poller.register(fd, select.POLLIN)
    eofed = set()
    result = '' if capture_stdout else None
    while True:
        events = poller.poll()
        for fd, event in events:
            stream = fd_to_stream[fd]
            line = stream.readline()
            if not line:
                eofed.add(fd)
            elif capture_stdout and stream is stdout:
                result += line
            else:
                if line[-1] == '\n':
                    line = line[:-1]
                logger.debug(line)
        if len(eofed) == len(streams):
            break
    retcode = proc.wait()
    if retcode != 0:
        raise subprocess.CalledProcessError(retcode, command_lst)
    return result
