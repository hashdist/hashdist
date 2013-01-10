import sys
from os.path import join as pjoin
from nose.tools import eq_, assert_raises
from pprint import pprint

from .. import sandbox
from .test_build_store import fixture as build_store_fixture


from .utils import MemoryLogger, logger as test_logger

env_to_stderr = [sys.executable, '-c',
                 "import os, sys; sys.stderr.write("
                 "'ENV:%s=%s' % (sys.argv[1], repr(os.environ.get(sys.argv[1], None))))"]
def filter_out(lines):
    return [x[len('DEBUG:ENV:'):] for x in lines if x.startswith('DEBUG:ENV:')]

@build_store_fixture()
def test_run_job_environment(tempdir, sc, build_store):
    # tests that the environment gets correctly set up and that the local scope feature
    # works
    job_spec = {
        "env": {"FOO": "foo"},
        "env_nohash": {"BAR": "$bar"},
        "script": [
            [
                ["BAR=${FOO}x"],
                ["HI=hi"],
                env_to_stderr + ["FOO"],
                env_to_stderr + ["BAR"],
                env_to_stderr + ["HI"],
            ],
            env_to_stderr + ["FOO"],
            env_to_stderr + ["BAR"],
            env_to_stderr + ["HI"],
            env_to_stderr + ["PATH"]
        ]}
    logger = MemoryLogger()
    ret_env = sandbox.run_job(logger, build_store, job_spec, {"BAZ": "BAZ"}, {}, tempdir)
    assert ret_env == {
        'PATH': '',
        'HDIST_LDFLAGS': '',
        'HDIST_CFLAGS': '',
        'BAR': '$bar',
        'FOO': 'foo',
        'BAZ': 'BAZ'}
    lines = filter_out(logger.lines)
    eq_(["FOO='foo'", "BAR='foox'", "HI='hi'", "FOO='foo'", "BAR='$bar'", 'HI=None', "PATH=''"],
        lines)

@build_store_fixture()
def test_script_dollar_paren(tempdir, sc, build_store):
    job_spec = {
        "script": [
            ["HI=$($echo", "  a  b   \n\n\n ", ")"],
            env_to_stderr + ["HI"]
        ]}
    logger = MemoryLogger()
    sandbox.run_job(logger, build_store, job_spec, {"echo": "/bin/echo"}, {}, tempdir)
    eq_(["HI='a  b'"], filter_out(logger.lines))

@build_store_fixture()
def test_script_redirect(tempdir, sc, build_store):
    job_spec = {
        "script": [
            ["$echo>$foo", "hi"]
        ]}
    sandbox.run_job(test_logger, build_store, job_spec,
                    {"echo": "/bin/echo", "foo": "foo"}, {}, tempdir)
    with file(pjoin(tempdir, 'foo')) as f:
        assert f.read() == 'hi\n'

@build_store_fixture()
def test_attach_log(tempdir, sc, build_store):
    with file(pjoin(tempdir, 'hello'), 'w') as f:
        f.write('hello from pipe')
    job_spec = {
        "script": [
            ["LOG=$(hdist", "logpipe", "mylog", "WARNING", ")"],
            ["/bin/dd", "if=hello", "of=$LOG"],
        ]}
    logger = MemoryLogger()
    sandbox.run_job(logger, build_store, job_spec, {}, {}, tempdir)
    assert 'WARNING:mylog:hello from pipe' in logger.lines

@build_store_fixture()
def test_notimplemented_redirection(tempdir, sc, build_store):
    job_spec = {
        "script": [
            ["LOG=$(hdist", "logpipe", "mylog", "WARNING", ")"],
            ["/bin/echo>$LOG", "my warning"]
        ]}
    with assert_raises(NotImplementedError):
        logger = MemoryLogger()
        sandbox.run_job(logger, build_store, job_spec, {}, {}, tempdir)

def test_substitute():
    env = {"A": "a", "B": "b"}
    def check(want, x):
        eq_(want, sandbox.substitute(x, env))
    def check_raises(x):
        with assert_raises(KeyError):
            sandbox.substitute(x, env)
    yield check, "ab", "$A$B"
    yield check, "ax", "${A}x"
    yield check, "\\", "\\"
    yield check, "\\\\", "\\\\"
    yield check, "a$${x}", "${A}\$\${x}"
    yield check_raises, "$Ax"
    yield check_raises, "$$"

def test_stable_topological_sort():
    def check(expected, problem):
        # pack simpler problem description into objects
        problem_objs = [dict(id=id, before=before, preserve=id[::-1])
                        for id, before in problem]
        got = sandbox.stable_topological_sort(problem_objs)
        got_ids = [x['id'] for x in got]
        assert expected == got_ids
        for obj in got:
            assert obj['preserve'] == obj['id'][::-1]
    
    problem = [
        ("t-shirt", []),
        ("sweater", ["t-shirt"]),
        ("shoes", []),
        ("space suit", ["sweater", "socks", "underwear"]),
        ("underwear", []),
        ("socks", []),
        ]

    check(['shoes', 'space suit', 'sweater', 't-shirt', 'underwear', 'socks'], problem)
    # change order of two leaves
    problem[-2], problem[-1] = problem[-1], problem[-2]
    check(['shoes', 'space suit', 'sweater', 't-shirt', 'socks', 'underwear'], problem)
    # change order of two roots (shoes and space suit)
    problem[2], problem[3] = problem[3], problem[2]
    check(['space suit', 'sweater', 't-shirt', 'socks', 'underwear', 'shoes'], problem)

    # error conditions
    with assert_raises(ValueError):
        # repeat element
        check([], problem + [("socks", [])])

    with assert_raises(ValueError):
        # cycle
        check([], [("x", ["y"]), ("y", ["x"])])

