import sys
import os
import logging
from os.path import join as pjoin
from nose.tools import eq_
from textwrap import dedent
from subprocess import CalledProcessError
from pprint import pprint
from nose import SkipTest

from .. import run_job
from .test_build_store import fixture as build_store_fixture

from .utils import which, logger as test_logger, assert_raises
from hashdist.util.logger_fixtures import log_capture


env_to_stderr = [sys.executable, '-c',
                 "import os, sys; sys.stderr.write("
                 "'ENV:%s=%s' % (sys.argv[1], repr(os.environ.get(sys.argv[1], None))))"]
def filter_out(lines):
    return [x[len('INFO:ENV:'):] for x in lines if x.startswith('INFO:ENV:')]

@build_store_fixture()
def test_run_job_environment(tempdir, sc, build_store, cfg):
    # tests that the environment gets correctly set up and that the local scope feature
    # works
    LD_LIBRARY_PATH = os.environ.get("LD_LIBRARY_PATH", "")
    job_spec = {
        "commands": [
            {"set": "LD_LIBRARY_PATH", "value": LD_LIBRARY_PATH},
            {"set": "FOO", "value": "foo"},
            {"set": "BAR", "nohash_value": "bar"},
            {
                "commands": [
                    {"set": "BAR", "value": "${FOO}x"},
                    {"set": "HI", "nohash_value": "hi"},
                    {"cmd": env_to_stderr + ["FOO"]},
                    {"cmd": env_to_stderr + ["BAR"]},
                    {"cmd": env_to_stderr + ["HI"]},
                    ],
            },
            {"cmd": env_to_stderr + ["FOO"]},
            {"cmd": env_to_stderr + ["BAR"]},
            {"cmd": env_to_stderr + ["HI"]},
        ]}
    with log_capture('build') as logger:
        ret_env = run_job.run_job(logger, build_store, job_spec, {"BAZ": "BAZ"}, '<no-artifact>',
                                  {"virtual:bash": "bash/ljnq7g35h6h4qtb456h5r35ku3dq25nl"},
                                  tempdir, cfg)
    assert 'HDIST_CONFIG' in ret_env
    del ret_env['HDIST_CONFIG']
    del ret_env['PWD']
    expected = {
        'ARTIFACT': '<no-artifact>',
        'BAR': 'bar',
        'BAZ': 'BAZ',
        'FOO': 'foo',
        'HDIST_IMPORT': '',
        'HDIST_IMPORT_PATHS': '',
        'HDIST_VIRTUALS': 'virtual:bash=bash/ljnq7g35h6h4qtb456h5r35ku3dq25nl',
        'LD_LIBRARY_PATH': LD_LIBRARY_PATH,
        'PATH': ''
        }
    eq_(expected, ret_env)
    lines = filter_out(logger.lines)
    eq_(["FOO='foo'", "BAR='foox'", "HI='hi'", "FOO='foo'", "BAR='bar'", 'HI=None'],
        lines)

@build_store_fixture()
def test_env_control(tempdir, sc, build_store, cfg):
    LD_LIBRARY_PATH = os.environ.get("LD_LIBRARY_PATH", "")
    job_spec = {
        "commands": [
            {"set": "LD_LIBRARY_PATH", "value": LD_LIBRARY_PATH},
            {"set": "FOO", "value": "foo"},
            {"set": "FOO", "value": "bar"},
            {"append_flag": "CFLAGS", "value": "-O3"},
            {"prepend_flag": "CFLAGS", "value": "-O2"},
            {"prepend_flag": "CFLAGS", "value": "-O1"},
            {"append_path": "PATH", "value": "/bar/bin"},
            {"prepend_path": "PATH", "value": "/foo/bin"},
            {"cmd": env_to_stderr + ["FOO"]},
            {"cmd": env_to_stderr + ["CFLAGS"]},
            {"cmd": env_to_stderr + ["PATH"]},
        ]}
    with log_capture('build') as logger:
        ret_env = run_job.run_job(logger, build_store, job_spec, {},
                                  '<no-artifact>', {}, tempdir, cfg)
    eq_(["FOO='bar'", "CFLAGS='-O1 -O2 -O3'", "PATH='/foo/bin:/bar/bin'"],
        filter_out(logger.lines))

@build_store_fixture()
def test_imports(tempdir, sc, build_store, cfg):
    # Make dependencies
    doc = {
        "name": "foosoft", "version": "na", "build": {"commands": []},
        }
    foo_id, foo_path = build_store.ensure_present(doc, cfg)

    doc = {
        "name": "barsoft", "version": "na", "build": {"commands": []},
        }
    bar_id, bar_path = build_store.ensure_present(doc, cfg)

    virtuals = {'virtual:bar' : bar_id}

    # Dependee
    LD_LIBRARY_PATH = os.environ.get("LD_LIBRARY_PATH", "")
    doc = {
            "import": [{"ref": "FOOSOFT", "id": foo_id}, {"ref": "BARSOFT", "id": "virtual:bar"}],
            "commands": [
                {"cmd": env_to_stderr + ["FOOSOFT_DIR"]},
                {"cmd": env_to_stderr + ["FOOSOFT_ID"]},
                {"cmd": env_to_stderr + ["BARSOFT_DIR"]},
                {"cmd": env_to_stderr + ["BARSOFT_ID"]},
                ]
        }
    with log_capture('build') as logger:
        ret_env = run_job.run_job(logger, build_store, doc, {},
                                  '<no-artifact>', virtuals, tempdir, cfg)
    eq_(["FOOSOFT_DIR=%r" % foo_path,
         "FOOSOFT_ID=%r" % foo_id,
         "BARSOFT_DIR=%r" % bar_path,
         "BARSOFT_ID=%r" % bar_id],
        filter_out(logger.lines))

@build_store_fixture()
def test_inputs(tempdir, sc, build_store, cfg):
    job_spec = {
        "commands": [
            {
             "env": {"LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", "")},
             "cmd": [sys.executable, "$in0", "$in1"],
             "inputs": [
                 {"text": ["import sys",
                           "import json",
                           "with open(sys.argv[1]) as f:"
                           "    print json.load(f)['foo']"]},
                 {"json": {"foo": "Hello1"}}
                 ]
             },
            {
             "env": {"LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", "")},
             "cmd": [sys.executable, "$in0"],
             "inputs": [{"string": "import sys\nprint 'Hello2'"}]
             },
            ]
        }
    with log_capture('build') as logger:
        ret_env = run_job.run_job(logger, build_store, job_spec, {"BAZ": "BAZ"}, '<no-artifact>',
                                  {"virtual:bash": "bash/ljnq7g35h6h4qtb456h5r35ku3dq25nl"},
                                  tempdir, cfg)
    logger.assertLogged('INFO:Hello1')
    logger.assertLogged('INFO:Hello2')

@build_store_fixture()
def test_capture_stdout(tempdir, sc, build_store, cfg):
    job_spec = {
        "commands": [
            {"cmd": ["$echo", "  a  b   \n\n\n "], "to_var": "HI"},
            {
             "env": {"LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", "")},
             "cmd": env_to_stderr + ["HI"]}
        ]}
    # Test both with _TEST_LOG_PROCESS_SIMPLE and without
    def doit():
        with log_capture() as logger:
            run_job.run_job(logger, build_store, job_spec, {"echo": "/bin/echo"},
                            '<no-artifact>', {}, tempdir, cfg)
        eq_(["HI='a  b'"], filter_out(logger.lines))

    doit()
    o = run_job._TEST_LOG_PROCESS_SIMPLE
    try:
        run_job._TEST_LOG_PROCESS_SIMPLE = True
        doit()
    finally:
        run_job._TEST_LOG_PROCESS_SIMPLE = o

@build_store_fixture()
def test_script_redirect(tempdir, sc, build_store, cfg):
    job_spec = {
        "commands": [
            {"set": "foo", "value": "foo"},
            {"cmd": ["$echo", "hi"], "append_to_file": "$foo"}
        ]}
    run_job.run_job(test_logger, build_store, job_spec,
                    {"echo": "/bin/echo"}, '<no-artifact>', {}, tempdir, cfg)
    with file(pjoin(tempdir, 'foo')) as f:
        assert f.read() == 'hi\n'

@build_store_fixture()
def test_attach_log(tempdir, sc, build_store, cfg):
    if 'linux' not in sys.platform:
        raise SkipTest('Linux only')

    with file(pjoin(tempdir, 'hello'), 'w') as f:
        f.write('hello from pipe')
    job_spec = {
        "commands": [
            {"hit": ["logpipe", "mylog", "WARNING"], "to_var": "LOG"},
            {"cmd": ["/bin/dd", "if=hello", "of=$LOG"]},
        ]}
    with log_capture('build') as logger:
        run_job.run_job(logger, build_store, job_spec, {},
                        '<no-artifact>', {}, tempdir, cfg)
    logger.assertLogged('^WARNING:mylog:hello from pipe$')

@build_store_fixture()
def test_error_exit(tempdir, sc, build_store, cfg):
    job_spec = {
        "commands": [
            {"cmd": [which("false")]},
        ]}
    with assert_raises(CalledProcessError):
        run_job.run_job(test_logger, build_store, job_spec, {}, '<no-artifact>', {}, tempdir, cfg)

@build_store_fixture()
def test_log_pipe_stress(tempdir, sc, build_store, cfg):
    if 'linux' not in sys.platform:
        raise SkipTest('Linux only')

    # Stress-test the log piping a bit, since the combination of Unix FIFO
    # pipes and poll() is a bit tricky to get right.

    # We want to launch many clients who each concurrently send many messages,
    # then check that they all get through to log_capture. We do this by
    # writing out two Python scripts and executing them...
    NJOBS = 5
    NMSGS = 300 # must divide 2

    with open(pjoin(tempdir, 'client.py'), 'w') as f:
        f.write(dedent('''\
        import os, sys
        msg = sys.argv[1] * (256 // 4) # less than PIPE_BUF, more than what we set BUFSIZE to
        for i in range(int(sys.argv[2]) // 2):
            with open(os.environ["LOG"], "a") as f:
                f.write("%s\\n" % msg)
                f.write("%s\\n" % msg)
            # hit stdout too
            sys.stdout.write("stdout:%s\\nstdout:%s\\n" % (sys.argv[1], sys.argv[1]))
            sys.stdout.flush()
            sys.stderr.write("stderr:%s\\nstderr:%s\\n" % (sys.argv[1], sys.argv[1]))
            sys.stderr.flush()
        '''))

    with open(pjoin(tempdir, 'launcher.py'), 'w') as f:
        f.write(dedent('''\
        import sys
        import subprocess
        procs = [subprocess.Popen([sys.executable, sys.argv[1], '%4d' % i, sys.argv[3]]) for i in range(int(sys.argv[2]))]
        for p in procs:
            if not p.wait() == 0:
                raise AssertionError("process failed: %d" % p.pid)
        '''))

    job_spec = {
        "commands": [
            {"hit": ["logpipe", "mylog", "WARNING"], "to_var": "LOG"},
            {"set": "LD_LIBRARY_PATH", "value": os.environ.get("LD_LIBRARY_PATH", "")},
            {"cmd": [sys.executable, pjoin(tempdir, 'launcher.py'),
                     pjoin(tempdir, 'client.py'), str(NJOBS), str(NMSGS)]},
        ]}
    old = run_job.LOG_PIPE_BUFSIZE
    try:
        run_job.LOG_PIPE_BUFSIZE = 50
        with log_capture('build') as logger:
            run_job.run_job(logger, build_store, job_spec, {}, '<no-artifact>', {}, tempdir, cfg)
    finally:
        run_job.LOG_PIPE_BUFSIZE = old

    log_bins = [0] * NJOBS
    stdout_bins = [0] * NJOBS
    stderr_bins = [0] * NJOBS
    for line in logger.lines:
        parts = line.split(':')
        if len(parts) != 3:
            continue
        level, log, msg = parts
        if log == 'mylog':
            assert level == 'WARNING'
            assert msg == msg[:4] * (256 // 4)
            idx = int(msg[:4])
            log_bins[idx] += 1
        elif log == 'stdout':
            assert level == 'INFO'
            stdout_bins[int(msg)] += 1
        elif log == 'stderr':
            assert level == 'INFO'
            stderr_bins[int(msg)] += 1
    assert all(x == NMSGS for x in log_bins)
    assert all(x == NMSGS for x in stdout_bins)
    assert all(x == NMSGS for x in stderr_bins)

@build_store_fixture()
def test_notimplemented_redirection(tempdir, sc, build_store, cfg):
    job_spec = {
        "commands": [
            {"hit": ["logpipe", "mylog", "WARNING"], "to_var": "log"},
            {"cmd": ["/bin/echo", "my warning"], "append_to_file": "$log"}
        ]}
    with assert_raises(NotImplementedError):
        run_job.run_job(test_logger, build_store, job_spec, {}, '<no-artifact>', {}, tempdir, cfg)

@build_store_fixture()
def test_script_cwd(tempdir, sc, build_store, cfg):
    os.makedirs(pjoin(tempdir, 'a', 'b', 'c'))
    job_spec = {
        "commands": [
            {"chdir": "a"},
            {"commands": [
                {"chdir": "b"},
                {"commands": [
                    {"chdir": "c"},
                    {"commands": [
                        {"chdir": ".."},
                        {"cmd": ["/bin/pwd"], "append_to_file": "out"}
                        ]}]}]}]}
    run_job.run_job(test_logger, build_store, job_spec, {}, '<no-artifact>', {}, tempdir, cfg)
    assert os.path.exists(pjoin(tempdir, 'a', 'b', 'out'))
    with open(pjoin(tempdir, 'a', 'b', 'out')) as f:
        assert f.read().strip() == pjoin(tempdir, 'a', 'b')


def test_substitute():
    env = {"A": "a", "B": "b"}
    def check(want, x):
        eq_(want, run_job.substitute(x, env))
    def check_raises(x):
        with assert_raises(KeyError):
            run_job.substitute(x, env)
    yield check, "ab", "$A$B"
    yield check, "ax", "${A}x"
    yield check, r"${A}x", "\\${A}x"
    yield check, r"\${A}x", "\\\\${A}x"
    yield check, "\\", "\\"
    yield check, "\\\\", "\\\\"
    yield check, "a$${x}", "${A}\$\${x}"
    yield check_raises, "$Ax"
    yield check_raises, "$$"
