"""
:mod:`hashdist.core.execute_job` --- Job exection
=================================================

Executes a set of commands in a controlled environment. This
should usually be used to launch a real script interpreter, but
basic support for modifying the environment and running multiple
commands are provided through the JSON job specification.

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


The execution environment
-------------------------

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

It may seem insane to invent another script language, so here's some
rationalization: First off, *something* must do the initial launch from
the Python process. That couldn't be a shell (because no shell is cross-platform)
and it couldn't be Python (because of all the different Python versions,
and we would like job specifications to not be Python-specific).

Then, there were a few features (notably getting log output from
hdist-jail reliably) that were simply easier to implement this way.
Ultimately, the "advanced" features like redirection are justified by
how little extra code was needed.

The scripting language should only be used for setting up an
environment and launching the job, and intentionally does not contain
any control flow. While it is modelled after Bash to make it familiar
to read, it is *not* in any way Bash, the implementation is entirely
in this Python module.

Parsing is at a minimum, since most of the structure is already
present in the JSON structure. There's no quoting, one string from the
input document is always passed as a single argument to ``Popen``.

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

 * The ``["executable", "arg1", ...]``: First string is command to execute (either
   absolute or looked up in ``$PATH``). Both `stdout` and `stderr` are
   redirected to the application logger.

 * The ``["executable>filename", "arg1", ...]``: Like the above, but `stdout` is
   redirected to the file. **Note** the unusual location of the filename (this was
   done so that one does not have to mess with escaping the ``>`` character for
   arguments).

 * The ``["VAR=str"]`` command sets an environment variable

 * The ``["VAR=$(command", "arg1", ..., ")"]``: Assigns the stdout of the command
   to the variable. The result has leading and trailing whitespace stripped
   but is otherwise untouched. The trailing ``")"`` must stand by itself (and does not
   really mean anything except as to balance the opening visually).

 * All forms above can be prepended with ``@`` on the command-string to silence
   logging the running environment (this may silence even more in the future).


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

import sys
import os
import fcntl
from os.path import join as pjoin
import shutil
import subprocess
from glob import glob
from string import Template
from pprint import pformat
import tempfile
import errno
import select
from StringIO import StringIO
import json

from ..hdist_logging import CRITICAL, ERROR, WARNING, INFO, DEBUG

from .common import working_directory

class InvalidJobSpecError(ValueError):
    pass

class JobFailedError(RuntimeError):
    pass

def run_job(logger, build_store, job_spec, env, virtuals, cwd, config):
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

    config : dict
        Configuration from :mod:`hashdist.core.config`. This will be
        serialied and put into the HDIST_CONFIG environment variable
        for use by ``hdist``.

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
    env['HDIST_VIRTUALS'] = pack_virtuals_envvar(virtuals)
    env['HDIST_CONFIG'] = json.dumps(config, separators=(',', ':'))
    executor = ScriptExecution(logger, cwd)
    try:
        out_env = executor.run(job_spec['script'], env)
    finally:
        executor.close()
    return out_env

def canonicalize_job_spec(job_spec):
    """Returns a copy of job_spec with default values filled in.

    Also performs a tiny bit of validation.
    """
    def canonicalize_import(item):
        item = dict(item)
        item.setdefault('in_env', True)
        if item.setdefault('ref', None) == '':
            raise ValueError('Empty ref should be None, not ""')
        item['before'] = sorted(item.get('before', []))
        return item

    result = dict(job_spec)
    result['import'] = [
        canonicalize_import(item) for item in result.get('import', ())]
    result['import'].sort(key=lambda item: item['id'])
    result.setdefault("env", {})
    result.setdefault("env_nohash", {})
    result.setdefault("script", [])
    return result
    
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
            raise InvalidJobSpecError('Dependency "%s"="%s" not already built, please build it first' %
                                        (dep_ref, dep_id))

        if dep_ref is not None:
            env[dep_ref] = dep_dir
            env['%s_id' % dep_ref] = dep_id

        if dep['in_env']:
            bin_dir = pjoin(dep_dir, 'bin')
            if os.path.exists(bin_dir):
                PATH.append(bin_dir)

            libdirs = glob(pjoin(dep_dir, 'lib*'))
            if len(libdirs) == 1:
                HDIST_LDFLAGS.append('-L' + libdirs[0])
                HDIST_LDFLAGS.append('-Wl,-R,' + libdirs[0])
            elif len(libdirs) > 1:
                raise InvalidJobSpecError('in_hdist_compiler_paths set for artifact %s with '
                                          'more than one library dir (%r)' % (dep_id, libdirs))

            incdir = pjoin(dep_dir, 'include')
            if os.path.exists(incdir):
                HDIST_CFLAGS.append('-I' + incdir)

    env['PATH'] = os.path.pathsep.join(PATH)
    env['HDIST_CFLAGS'] = ' '.join(HDIST_CFLAGS)
    env['HDIST_LDFLAGS'] = ' '.join(HDIST_LDFLAGS)
    return env
    
def pack_virtuals_envvar(virtuals):
    return ';'.join('%s=%s' % tup for tup in sorted(virtuals.items()))

def unpack_virtuals_envvar(x):
    return dict(tuple(tup.split('=')) for tup in x.split(';'))


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


class ScriptExecution(object):
    """
    Class for maintaining state (in particular logging pipes) while
    executing script. Note that the environment is passed around as
    parameters instead.

    Executing :meth:`run` multiple times amounts to executing
    different variable scopes (but with same logging pipes set up).
    
    Parameters
    ----------

    logger : Logger

    cwd : str
        The working directory for the script (stays the same for all commands)

    rpc_dir : str
        A temporary directory on a local filesystem. Currently used for creating
        pipes with the "hdist logpipe" command.
    """
    
    def __init__(self, logger, cwd):
        self.logger = logger
        self.cwd = cwd
        self.log_fifo_fds = {}
        self.rpc_dir = tempfile.mkdtemp(prefix='hdist-sandbox-')

    def close(self):
        """Terminates and removes log FIFOs; should always be called when one is done
        """
        for fd in self.log_fifo_fds.values():
            os.close(fd)
        shutil.rmtree(self.rpc_dir)

    def run(self, script, env):
        """Executes script, given as the 'script' part of the job spec.

        Parameters
        ----------
        script : document
            The 'script' part of the job spec

        env : dict
            The starting process environment

        Returns
        -------

        out_env : dict
            The environment as modified by the script.
        """
        env = dict(env)
        for script_line in script:
            if len(script_line) == 0:
                continue
            if isinstance(script_line[0], list):
                if any(not isinstance(x, list) for x in script_line):
                    raise ValueError("mixing list and str at same level in script")
                # sub-scope; recurse and discard the modified environment
                self.run(script_line, env)
            else:
                cmd = script_line[0]
                silent = cmd.startswith('@')
                if silent:
                    cmd = cmd[1:]
                args = [substitute(x, env) for x in script_line[1:]]
                if '=$(' in cmd:
                    # a=$(command)
                    varname, cmd = cmd.split('=$(')
                    if args[-1] != ')':
                        raise ValueError("opens with $( but no closing ): %r" % script_line)
                    del args[-1]
                    cmd = substitute(cmd, env)
                    stdout = StringIO()
                    self.run_command([cmd] + args, env, stdout_to=stdout, silent=silent)
                    env[varname] = stdout.getvalue().strip()
                elif '=' in cmd:
                    # VAR=value
                    varname, value = cmd.split('=')
                    if args:
                        raise ValueError('assignment takes no extra arguments')
                    env[varname] = substitute(value, env)
                elif '>' in cmd:
                    # program>out
                    cmd, stdout_filename = cmd.split('>')
                    cmd = substitute(cmd, env)
                    
                    stdout_filename = substitute(stdout_filename, env)
                    if not os.path.isabs(stdout_filename):
                        stdout_filename = pjoin(self.cwd, stdout_filename)
                    stdout_filename = os.path.realpath(stdout_filename)
                    if stdout_filename.startswith(self.rpc_dir):
                        raise NotImplementedError("Cannot currently use stream re-direction to write to "
                                                  "a sandbox log-pipe (doing the write from a "
                                                  "sub-process is OK)")
                    stdout = file(stdout_filename, 'a')
                    try:
                        self.run_command([cmd] + args, env, stdout_to=stdout, silent=silent)
                    finally:
                        stdout.close()
                else:
                    # program
                    cmd = substitute(cmd, env)
                    self.run_command([cmd] + args, env, silent=silent)
        return env

    def run_command(self, command_lst, env, stdout_to=None, silent=False):
        """Runs a single command of the sandbox script

        This mainly takes care of stream re-direction and special handling
        of the hdist command.

        Raises `subprocess.CalledProcessError` on non-zero return code,
        except when running ``hdist`` in-process in which case exception
        is simply propagated.


        Parameters
        ----------

        command_lst : list
            Passed dirctly on to Popen

        env : dict
            Process environment

        stdout_to : bool
            If `False`, redirect stdout to logger, otherwise return it
        """
        logger = self.logger
        logger.info('running %r' % command_lst)
        if not silent:
            logger.debug('cwd: ' + self.cwd)
            logger.debug('environment:')
            for line in pformat(env).splitlines():
                logger.debug('  ' + line)
        if command_lst[0] == 'hdist':
            # run hdist cli in-process special case the 'hdist'
            # command and run it in the same process do not emit
            # INFO-messages from sub-command unless level is DEBUG
            old_level = logger.level
            old_stdout = sys.stdout
            try:
                if logger.level > DEBUG:
                    logger.level = WARNING
                if stdout_to is not None:
                    sys.stdout = stdout_to
                self.hdist_command(command_lst, env, logger)
            except:
                logger.error("hdist command failed; raising")
                raise
            finally:
                logger.level = old_level
                sys.stdout = old_stdout
        else:
            try:
                self.logged_check_call(command_lst, env, stdout_to)
            except subprocess.CalledProcessError, e:
                logger.error("command failed (code=%d); raising" % e.returncode)
                raise

    def logged_check_call(self, command_lst, env, stdout_to):
        """
        Similar to subprocess.check_call, but multiplexes input from stderr, stdout
        and any number of log FIFO pipes available to the called process into
        a single Logger instance. Optionally captures stdout instead of logging it.
        """
        logger = self.logger
        try:
            proc = subprocess.Popen(command_lst,
                                    cwd=self.cwd,
                                    env=env,
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    close_fds=True)
        except OSError, e:
            if e.errno == errno.ENOENT:
                # fix error message up a bit since the situation is so confusing
                logger.error('command "%s" not found in PATH' % command_lst[0])
                raise OSError(e.errno, 'command "%s" not found in PATH (cwd: "%s")' %
                              (command_lst[0], self.cwd), self.cwd)
            else:
                raise

        # Multiplex input from stdout, stderr, and any attached log
        # pipes.  To avoid any deadlocks with unbuffered stderr
        # interlaced with use of log pipe etc. we avoid readline(), but
        # instead use os.open to read and handle line-assembly ourselves...
        stdout_fd, stderr_fd = proc.stdout.fileno(), proc.stderr.fileno()
        fds = [stdout_fd, stderr_fd] + self.log_fifo_fds.values()
        # map from fd to logger and level to use
        loggers = {stdout_fd: (logger, DEBUG), stderr_fd: (logger, DEBUG)}
        for (header, level), fd in self.log_fifo_fds.iteritems():
            sublogger = logger.get_sub_logger(header)
            loggers[fd] = (sublogger, level)

        poller = select.poll()
        for fd in fds:
            poller.register(fd, select.POLLIN)

        buffers = dict((fd, '') for fd in fds)
        BUFSIZE = 4096
        while True:
            # Python poll() doesn't return when SIGCHLD is received;
            # and there's the freak case where a process first
            # terminates stdout/stderr, then trying to write to a log
            # pipe, so we should track child termination the proper
            # way. Being in Python, it's easiest to just poll every
            # 50 ms; the majority of the time is spent in poll() so
            # it doesn't really increase log message latency
            events = poller.poll(50)
            if len(events) == 0:
                if proc.poll() is not None:
                    break # child terminated
            for fd, reason in events:
                if reason & select.POLLHUP:
                    poller.unregister(fd)

                if reason & select.POLLIN:
                    if stdout_to is not None and fd == stdout_fd:
                        # Just forward
                        buf = os.read(fd, BUFSIZE)
                        stdout_to.write(buf)
                    else:
                        # append new bytes to what's already been read on this fd; and
                        # emit any completed lines
                        new_bytes = os.read(fd, BUFSIZE)
                        assert new_bytes != '' # after all, we did poll
                        buffers[fd] += new_bytes
                        lines = buffers[fd].splitlines(True) # keepends=True
                        if lines[-1][-1] != '\n':
                            buffers[fd] = lines[-1]
                            del lines[-1]
                        else:
                            buffers[fd] = ''
                        # have list of lines, emit them to logger
                        sublogger, level = loggers[fd]
                        for line in lines:
                            if line[-1] == '\n':
                                line = line[:-1]
                            sublogger.log(level, line)
        # deal with buffers not terminated by '\n'
        for fd, buf in buffers.iteritems():
            sublogger, level = loggers[fd]
            if buf:
                sublogger.log(level, buf)

        retcode = proc.wait()
        if retcode != 0:
            raise subprocess.CalledProcessError(retcode, command_lst)

    def hdist_command(self, argv, env, logger):
        if len(argv) >= 2 and argv[1] == 'logpipe':
            if len(argv) != 4:
                raise ValueError('wrong number of arguments to "hdist logpipe"')
            sublogger_name, level = argv[2:]
            self.create_log_pipe(sublogger_name, level)
        else:
            from ..cli import main as cli_main
            with working_directory(self.cwd):
                cli_main(argv, env, logger)

    def create_log_pipe(self, sublogger_name, level_str):
        level = dict(CRITICAL=CRITICAL, ERROR=ERROR, WARNING=WARNING, INFO=INFO, DEBUG=DEBUG)[level_str]
        fifo_name = pjoin(self.rpc_dir, "logpipe-%s-%s" % (sublogger_name, level_str))
        fifo_file = self.log_fifo_fds.get((sublogger_name, level), None)
        if fifo_file is None:
            os.mkfifo(fifo_name, 0600)
            fd = os.open(fifo_name, os.O_NONBLOCK|os.O_RDONLY)
            # remove non-blocking after open to treat all streams uniformly in
            # the multiplexer code
            fcntl.fcntl(fd, fcntl.F_SETFL, os.O_RDONLY) 
            self.log_fifo_fds[sublogger_name, level] = fd
        sys.stdout.write(fifo_name)
        
