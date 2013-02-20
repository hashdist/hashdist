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
            {"ref": "BASH", "id": "virtual:bash"},
            {"ref": "MAKE", "id": "virtual:gnu-make/3+"},
            {"ref": "ZLIB", "id": "zlib/2d4kh7hw4uvml67q7npltyaau5xmn4pc"},
            {"ref": "UNIX", "id": "virtual:unix"},
            {"ref": "GCC", "before": ["virtual:unix"], "id": "gcc/jonykztnjeqm7bxurpjuttsprphbooqt"}
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
by the user. There is no stdin (it's set to a closed pipe).

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
any control flow. Parsing is at a minimum, since most of the structure
is already present in the JSON structure. There's no quoting, one
string from the input document is always passed as a single argument
to ``Popen``.

Example script::

    "script" : [
        {"hdist": ["unpack-sources"]},
        { "env": {"LIB": "foo"},
          "cwd": "src",
          "scope": [
            {"cmd": ["pkgcfg", "--cflags", "$LIB"], "to_var": "FOO"}
            {"cmd": ["./configure", "--prefix=$ARTIFACT", "--foo-setting=$FOO"]},
          ]
        },
        {"cmd": ["make", "-j$NCORES"], "cwd": "src"},
        {"cmd": ["make", "install"], "cwd": "src"}
    ]

Rules:

 * Every item in the script is either a `cmd` or a `scope` or a `hdist`, i.e.
   those keys are mutually exclusive.

 * In the case of scope, variable changes only take affect within the scope (above,
   both ``$LIB`` and ``$FOO`` are only available in the sub-scope, it acts
   like a normal programming language stack).

 * The `cmd` list is passed straight to :func:`subprocess.Popen` as is
   (after variable substiution). I.e., no quoting needed, no globbing.

 * The `hdist` executes the `hdist` tool *in-process*. It acts like `cmd` otherwise,
   e.g., `to_var` works.

 * `env` and `cwd` modifies env-vars/working directory for the command in question,
   or the scope if it is a scope. They acts just like the regular
   `cd` command, i.e., you can do things like ``"cwd": ".."``

 * stdout and stderr will be logged, except if `to_var` or
   `append_to_file` is present in which case the stdout is capture to
   an environment variable or redirected in append-mode to file, respectively. (In
   the former case, the resulting string undergoes `strip()`, and is
   then available for the following commands within the same scope.)

 * Variable substitution is performed the following places: The `cmd`,
   values of `env`, the `cwd`, `stdout_to_file`.  The syntax is
   ``$CFLAGS`` and ``${CFLAGS}``. ``\$`` is an escape for ``$``
   (but ``\`` not followed by ``$`` is not currently an escape).


For the `hdist` tool, in addition to what is listed in ``hdist
--help``, the following special command is available for interacting
with the job runner:

 * ``hdist logpipe HEADING LEVEL``: Creates a new Unix FIFO and prints
   its name to standard output (it will be removed once the job
   terminates). The job runner will poll the pipe and print
   anything written to it nicely formatted to the log with the given
   heading and log level (the latter is one of ``DEBUG``, ``INFO``,
   ``WARNING``, ``ERROR``).

.. note::

    ``hdist`` is not automatically available in the environment in general
    (in launched scripts etc.), for that, see :mod:`hashdist.core.hdist_recipe`.
    ``hdist logpipe`` is currently not supported outside of the job script
    at all (this could be supported through RPC with the job runner, but the
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

LOG_PIPE_BUFSIZE = 4096


class InvalidJobSpecError(ValueError):
    pass

class JobFailedError(RuntimeError):
    pass

def run_job(logger, build_store, job_spec, override_env, virtuals, cwd, config):
    """Runs a job in a controlled environment, according to rules documented above.

    Parameters
    ----------

    logger : Logger

    build_store : BuildStore
        BuildStore to find referenced artifacts in.

    job_spec : document
        See above

    override_env : dict
        Extra environment variables not present in job_spec, these will be added
        last and overwrite existing ones.

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
    env = get_imports_env(build_store, virtuals, job_spec['import'])
    env.update(job_spec['env'])
    env.update(job_spec['env_nohash'])
    env.update(override_env)
    env['HDIST_VIRTUALS'] = pack_virtuals_envvar(virtuals)
    env['HDIST_CONFIG'] = json.dumps(config, separators=(',', ':'))
    executor = ScriptExecution(logger)
    try:
        out_env = executor.run(job_spec['script'], env, cwd)
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
    HDIST_IMPORT = []
    
    for dep in imports:
        dep_ref = dep['ref']
        dep_id = dep['id']
        HDIST_IMPORT.append(dep_id)

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
            env['%s_ID' % dep_ref] = dep_id

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
    env['HDIST_IMPORT'] = ' '.join(HDIST_IMPORT)
    return env
    
def pack_virtuals_envvar(virtuals):
    return ';'.join('%s=%s' % tup for tup in sorted(virtuals.items()))

def unpack_virtuals_envvar(x):
    if not x:
        return {}
    else:
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

    rpc_dir : str
        A temporary directory on a local filesystem. Currently used for creating
        pipes with the "hdist logpipe" command.
    """
    
    def __init__(self, logger):
        self.logger = logger
        self.log_fifo_filenames = {}
        self.rpc_dir = tempfile.mkdtemp(prefix='hdist-sandbox-')

    def close(self):
        """Removes log FIFOs; should always be called when one is done
        """
        shutil.rmtree(self.rpc_dir)

    def substitute(self, x, env):
        try:
            return substitute(x, env)
        except KeyError, e:
            msg = 'No such environment variable: %s' % str(e)
            self.logger.error(msg)
            raise ValueError(msg)

    def run(self, script, env, cwd):
        """Executes script, given as the 'script' part of the job spec.

        Parameters
        ----------
        script : document
            The 'script' part of the job spec

        env : dict
            The starting process environment

        cwd : str
            Working directory

        Returns
        -------

        out_env : dict
            The environment as modified by the script.
        """
        for line in script:
            if sum(['cmd' in line, 'hdist' in line, 'scope' in line]) != 1:
                raise ValueError("Each script line should have exactly one of the 'cmd', 'hdist', 'scope' keys")
            if sum(['to_var' in line, 'stdout_to_file' in line]) > 1:
                raise ValueError("Can only have one of to_var, stdout_to_file")
            if 'scope' in line and ('append_to_file' in line or 'to_var' in line):
                raise ValueError('"scope" not compatible with to_var or append_to_file')


            # Make scope for this line
            line_env = dict(env)
            line_cwd = cwd

            # Process common options
            if 'cwd' in line:
                cwd = pjoin(line_cwd, line['cwd'])
            if 'env' in line:
                for key, value in line['env'].items():
                    # note: subst. using parent env to make sure order doesn't matter
                    line_env[key] = self.substitute(value, env)

            if 'cmd' in line or 'hdist' in line:
                if 'cmd' in line:
                    args = line['cmd']
                    func = self.run_cmd
                else:
                    args = line['hdist']
                    func = self.run_hdist
                args = [self.substitute(x, line_env) for x in args]

                if 'to_var' in line:
                    stdout = StringIO()
                    func(args, line_env, line_cwd, stdout_to=stdout)
                    # modifying *parent* env, not line_env
                    env[line['to_var']] = stdout.getvalue().strip()
                    
                elif 'append_to_file' in line:
                    stdout_filename = self.substitute(line['append_to_file'], line_env)
                    if not os.path.isabs(stdout_filename):
                        stdout_filename = pjoin(cwd, stdout_filename)
                    stdout_filename = os.path.realpath(stdout_filename)
                    if stdout_filename.startswith(self.rpc_dir):
                        raise NotImplementedError("Cannot currently use stream re-direction to write to "
                                                  "a log-pipe (doing the write from a "
                                                  "sub-process is OK)")
                    with file(stdout_filename, 'a') as stdout:
                        func(args, line_env, line_cwd, stdout_to=stdout)
                
                else:
                    func(args, line_env, line_cwd)
                    
            elif 'scope' in line:
                self.run(line['scope'], line_env, line_cwd)

            else:
                assert False

        return env

    def run_cmd(self, args, env, cwd, stdout_to=None):
        logger = self.logger
        logger.debug('running %r' % args)
        logger.debug('cwd: ' + cwd)
        logger.debug('environment:')
        for line in pformat(env).splitlines():
            logger.debug('  ' + line)
        try:
            self.logged_check_call(args, env, cwd, stdout_to)
        except subprocess.CalledProcessError, e:
            logger.error("command failed (code=%d); raising" % e.returncode)
            raise

    def run_hdist(self, args, env, cwd, stdout_to=None):
        args = ['hdist'] + args
        logger = self.logger
        logger.debug('running %r' % args)
        # run it in the same process, but do not emit
        # INFO-messages from sub-command unless level is DEBUG
        old_level = logger.level
        old_stdout = sys.stdout
        try:
            if logger.level > DEBUG:
                logger.level = WARNING
            if stdout_to is not None:
                sys.stdout = stdout_to

            if len(args) >= 2 and args[1] == 'logpipe':
                if len(args) != 4:
                    raise ValueError('wrong number of arguments to "hdist logpipe"')
                sublogger_name, level = args[2:]
                self.create_log_pipe(sublogger_name, level)
            else:
                from ..cli import main as cli_main
                with working_directory(cwd):
                    cli_main(args, env, logger)
        except:
            logger.error("hdist command failed")
            raise
        finally:
            logger.level = old_level
            sys.stdout = old_stdout
       

    def logged_check_call(self, args, env, cwd, stdout_to):
        """
        Similar to subprocess.check_call, but multiplexes input from stderr, stdout
        and any number of log FIFO pipes available to the called process into
        a single Logger instance. Optionally captures stdout instead of logging it.
        """
        logger = self.logger
        try:
            proc = subprocess.Popen(args,
                                    cwd=cwd,
                                    env=env,
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    close_fds=True)
        except OSError, e:
            if e.errno == errno.ENOENT:
                # fix error message up a bit since the situation is so confusing
                if '/' in args[0]:
                    msg = 'command "%s" not found (cwd: %s)' % (args[0], cwd)
                else:
                    msg = 'command "%s" not found in $PATH (cwd: %s)' % (args[0], cwd)
                logger.error(msg)
                raise OSError(e.errno, msg)
            else:
                raise

        # Weave together input from stdout, stderr, and any attached log
        # pipes.  To avoid any deadlocks with unbuffered stderr
        # interlaced with use of log pipe etc. we avoid readline(), but
        # instead use os.open to read and handle line-assembly ourselves...

        stdout_fd, stderr_fd = proc.stdout.fileno(), proc.stderr.fileno()
        poller = select.poll()
        poller.register(stdout_fd)
        poller.register(stderr_fd)

        # Set up { fd : (logger, level) }
        loggers = {stdout_fd: (logger, DEBUG), stderr_fd: (logger, DEBUG)}
        buffers = {stdout_fd: '', stderr_fd: ''}

        # The FIFO pipes are a bit tricky as they need to the re-opened whenever
        # any client closes. This also modified the loggers dict and fd_to_logpipe
        # dict.

        fd_to_logpipe = {} # stderr/stdout not re-opened
        
        def open_fifo(fifo_filename, logger, level):
            # need to open in non-blocking mode to avoid waiting for printing client process
            fd = os.open(fifo_filename, os.O_NONBLOCK|os.O_RDONLY)
            # remove non-blocking after open to treat all streams uniformly in
            # the reading code
            fcntl.fcntl(fd, fcntl.F_SETFL, os.O_RDONLY)
            loggers[fd] = (logger, level)
            buffers[fd] = ''
            fd_to_logpipe[fd] = fifo_filename
            poller.register(fd)

        def flush_buffer(fd):
            buf = buffers[fd]
            if buf:
                # flush buffer in case last line not terminated by '\n'
                sublogger, level = loggers[fd]
                sublogger.log(level, buf)
            del buffers[fd]

        def close_fifo(fd):
            flush_buffer(fd)
            poller.unregister(fd)
            os.close(fd)
            del loggers[fd]
            del fd_to_logpipe[fd]
            
        def reopen_fifo(fd):
            fifo_filename = fd_to_logpipe[fd]
            logger, level = loggers[fd]
            close_fifo(fd)
            open_fifo(fifo_filename, logger, level)

        for (header, level), fifo_filename in self.log_fifo_filenames.items():
            sublogger = logger.get_sub_logger(header)
            open_fifo(fifo_filename, sublogger, level)
            
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
                if reason & select.POLLHUP and not (reason & select.POLLIN):
                    # we want to continue receiving PULLHUP|POLLIN until all
                    # is read
                    if fd in fd_to_logpipe:
                        reopen_fifo(fd)
                    elif fd in (stdout_fd, stderr_fd):
                        poller.unregister(fd)
                elif reason & select.POLLIN:
                    if stdout_to is not None and fd == stdout_fd:
                        # Just forward
                        buf = os.read(fd, LOG_PIPE_BUFSIZE)
                        stdout_to.write(buf)
                    else:
                        # append new bytes to what's already been read on this fd; and
                        # emit any completed lines
                        new_bytes = os.read(fd, LOG_PIPE_BUFSIZE)
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

        flush_buffer(stderr_fd)
        flush_buffer(stdout_fd)
        for fd in fd_to_logpipe.keys():
            close_fifo(fd)

        retcode = proc.wait()
        if retcode != 0:
            raise subprocess.CalledProcessError(retcode, command_lst)

    def create_log_pipe(self, sublogger_name, level_str):
        level = dict(CRITICAL=CRITICAL, ERROR=ERROR, WARNING=WARNING, INFO=INFO, DEBUG=DEBUG)[level_str]
        fifo_filename = self.log_fifo_filenames.get((sublogger_name, level), None)
        if fifo_filename is None:
            fifo_filename = pjoin(self.rpc_dir, "logpipe-%s-%s" % (sublogger_name, level_str))
            os.mkfifo(fifo_filename, 0600)
            self.log_fifo_filenames[sublogger_name, level] = fifo_filename
        sys.stdout.write(fifo_filename)
        
