import os
from os.path import join as pjoin
import functools
import tempfile
import shutil
from textwrap import dedent

from nose.tools import assert_raises

from .utils import logger

from .. import source_cache, builder

def fixture(func):
    @functools.wraps(func)
    def decorated():
        tempdir = tempfile.mkdtemp()
        try:
            os.makedirs(pjoin(tempdir, 'sources'))
            os.makedirs(pjoin(tempdir, 'artifacts'))
            sc = source_cache.SourceCache(pjoin(tempdir, 'sources'))
            bldr = builder.Builder(sc, pjoin(tempdir, 'artifacts'), logger)
            return func(tempdir, sc, bldr)
        finally:
            shutil.rmtree(tempdir)
    return decorated

@fixture
def test_basic(tempdir, sc, bldr):
    script_key = sc.put('build.sh', dedent("""\
    echo hi stdout
    echo hi stderr>&2
    echo hello > hello
    """))
    spec = {
        "name": "foo",
        "sources": [
            {"target": ".", "key": script_key},
            {"target": "subdir", "key": script_key}
            ],
        "command": ["/bin/bash", "build.sh"]
        }
    assert not bldr.is_present(spec)
    name, path = bldr.ensure_present(spec)
    assert bldr.is_present(spec)
    assert ['build.json', 'build.log', 'build.sh', 'hello', 'subdir'] == sorted(os.listdir(path))
    assert os.listdir(pjoin(path, 'subdir')) == ['build.sh']
    with file(pjoin(path, 'hello')) as f:
        assert f.read() == 'hello\n'
    with file(pjoin(path, 'build.log')) as f:
        s =  f.read()
        assert 'hi stdout' in s
        assert 'hi stderr' in s


@fixture
def test_failing_build(tempdir, sc, bldr):
    script_key = sc.put('build.sh', 'exit 1')
    spec = {"name": "foo",
            "sources": [{"key": script_key}],
            "command": ["/bin/bash", "build.sh"]}
    try:
        bldr.ensure_present(spec, keep_on_fail=True)
    except builder.BuildFailedError, e:
        assert os.path.exists(pjoin(e.build_dir, 'build.sh'))
    else:
        assert False

    try:
        bldr.ensure_present(spec, keep_on_fail=False)
    except builder.BuildFailedError, e:
        assert e.build_dir is None
    else:
        assert False
    

@fixture
def test_source_target_tries_to_escape(tempdir, sc, bldr):
    for target in ["..", "/etc"]:
        spec = {"name": "foo",
                "sources": [{"target": target, "key": "foo"}]
                }
        with assert_raises(builder.InvalidBuildSpecError):
            bldr.ensure_present(spec)


@fixture
def test_fail_to_find_dependency(tempdir, sc, bldr):
    for target in ["..", "/etc"]:
        spec = {"name": "foo", "dependencies": {"bar": "bogushash"}}
        with assert_raises(builder.InvalidBuildSpecError):
            bldr.ensure_present(spec)

# To test more complex relationship with packages we need to automate a bit:

class MockPackage:
    def __init__(self, name, deps):
        self.name = name
        self.deps = deps


def build_mock_packages(builder, packages):
    name_to_artifact = {} # name -> (artifact_id, path)
    for pkg in packages:
        if len(pkg.deps) == 0:
            script = 'touch deps'
        else:
            script = '\n'.join(
                'echo %(x)s $%(x)s $%(x)s_abspath $%(x)s_relpath >> deps' % dict(x=dep.name)
                for dep in pkg.deps)
        script_key = builder.source_cache.put('build.sh', script)
        spec = {"name": pkg.name,
                "dependencies": dict((dep.name, name_to_artifact[dep.name][0])
                                     for dep in pkg.deps),
                "sources": [{"key": script_key}],
                "command": ["/bin/bash", "build.sh"]}
        artifact, path = builder.ensure_present(spec)
        name_to_artifact[pkg.name] = (artifact, path)

        with file(pjoin(path, 'deps')) as f:
            for line, dep in zip(f.readlines(), pkg.deps):
                d, artifact_id, abspath, relpath = line.split()
                assert d == dep.name
                assert os.path.abspath(pjoin(path, relpath)) == abspath
                assert abspath == name_to_artifact[d][1]
        
@fixture
def test_dependency_substitution(tempdir, sc, bldr):
    # Test that environment variables for dependencies are present in build environment
    libc = MockPackage("libc", [])
    blas = MockPackage("blas", [libc])
    numpy = MockPackage("numpy", [blas, libc])
    build_mock_packages(bldr, [libc, blas, numpy])
