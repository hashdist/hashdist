import os
from os.path import join as pjoin
import functools
import tempfile
import shutil
from textwrap import dedent

from nose.tools import assert_raises

from .utils import logger

from .. import source_cache, builder


#
# Simple tests
#
def test_shorten_artifact_id():
    assert 'foo/1.2/012' == builder.shorten_artifact_id('foo/1.2/01234567890', 3)
    with assert_raises(ValueError):
        builder.shorten_artifact_id('foo-1.2-01234567890', 3)

#
# Tests requiring fixture
#
def fixture(keep_policy='never', ARTIFACT_ID_LEN=None):
    def decorator(func):
        @functools.wraps(func)
        def decorated():
            old_aid_len = builder.ARTIFACT_ID_LEN
            tempdir = tempfile.mkdtemp()
            try:
                if ARTIFACT_ID_LEN is not None:
                    builder.ARTIFACT_ID_LEN = ARTIFACT_ID_LEN
                os.makedirs(pjoin(tempdir, 'src'))
                os.makedirs(pjoin(tempdir, 'opt'))
                os.makedirs(pjoin(tempdir, 'bld'))
                sc = source_cache.SourceCache(pjoin(tempdir, 'src'))
                bldr = builder.Builder(sc, pjoin(tempdir, 'bld'), pjoin(tempdir, 'opt'), logger,
                                       keep_policy)
                return func(tempdir, sc, bldr)
            finally:
                builder.ARTIFACT_ID_LEN = old_aid_len
                shutil.rmtree(tempdir)
        return decorated
    return decorator

@fixture()
def test_basic(tempdir, sc, bldr):
    script_key = sc.put('build.sh', dedent("""\
    echo hi stdout
    echo hi stderr>&2
    find > ${PREFIX}/hello
    """))
    spec = {
        "name": "foo",
        "version": "na",
        "sources": [
            {"target": ".", "key": script_key},
            {"target": "subdir", "key": script_key}
            ],
        "command": ["/bin/bash", "build.sh"]
        }
    assert not bldr.is_present(spec)
    name, path = bldr.ensure_present(spec)
    assert bldr.is_present(spec)
    assert ['build.json', 'build.log', 'hello'] == sorted(os.listdir(path))
    #assert os.listdir(pjoin(path, 'subdir')) == ['build.sh']
    with file(pjoin(path, 'hello')) as f:
        assert ''.join(sorted(f.readlines())) == dedent('''\
        .
        ./build.json
        ./build.log
        ./build.sh
        ./subdir
        ./subdir/build.sh
        ''')
    with file(pjoin(path, 'build.log')) as f:
        s =  f.read()
        assert 'hi stdout' in s
        assert 'hi stderr' in s


@fixture(keep_policy='error')
def test_failing_build(tempdir, sc, bldr):
    script_key = sc.put('build.sh', 'exit 1')
    spec = {"name": "foo", "version": "na",
            "sources": [{"key": script_key}],
            "command": ["/bin/bash", "build.sh"]}
    try:
        bldr.ensure_present(spec)
    except builder.BuildFailedError, e:
        assert os.path.exists(pjoin(e.build_dir, 'build.sh'))
    else:
        assert False

@fixture(keep_policy='never')
def test_failing_build_2(tempdir, sc, bldr):
    script_key = sc.put('build.sh', 'exit 1')
    spec = {"name": "foo", "version": "na",
            "sources": [{"key": script_key}],
            "command": ["/bin/bash", "build.sh"]}
    try:
        bldr.ensure_present(spec)
    except builder.BuildFailedError, e:
        assert e.build_dir is None
    else:
        assert False
    

@fixture()
def test_source_target_tries_to_escape(tempdir, sc, bldr):
    for target in ["..", "/etc"]:
        spec = {"name": "foo", "version": "na",
                "sources": [{"target": target, "key": "foo"}]
                }
        with assert_raises(builder.InvalidBuildSpecError):
            bldr.ensure_present(spec)


@fixture()
def test_fail_to_find_dependency(tempdir, sc, bldr):
    for target in ["..", "/etc"]:
        spec = {"name": "foo", "version": "na",
                "dependencies": {"bar": "bogushash"}}
        with assert_raises(builder.InvalidBuildSpecError):
            bldr.ensure_present(spec)

@fixture(ARTIFACT_ID_LEN=1)
def test_hash_prefix_collision(tempdir, sc, bldr):
    lines = []
    # do all build 
    for repeat in range(2):
        # by experimentation this was enough to get a couple of collisions;
        # changes to the hashing could change this a bit but assertions below will
        # warn in those cases
        hashparts = []
        for k in range(10):
            script_key = sc.put('build.sh', 'echo hello %d; exit 0' % k)
            spec = {"name": "foo", "version": "na",
                    "sources": [{"key": script_key}],
                    "command": ["/bin/bash", "build.sh"]}
            artifact_id, path = bldr.ensure_present(spec)
            hashparts.append(os.path.split(path)[-1])
        lines.append(hashparts)
    # please increase number of k-iterations above, or changes something
    # in the build spec, if this hits:
    assert any(len(x) > 1 for x in lines[0])

    # all repeats the same
    assert lines[1] == lines[0]

    # normal assertions
    hashparts = lines[0]
    for x in hashparts:
        if len(x) > 1:
            assert x[:1] in hashparts
    

# To test more complex relationship with packages we need to automate a bit:

class MockPackage:
    def __init__(self, name, deps):
        self.name = name
        self.deps = deps


def build_mock_packages(builder, packages):
    name_to_artifact = {} # name -> (artifact_id, path)
    for pkg in packages:
        script = 'touch ${PREFIX}/deps\n'
        script += '\n'.join(
            'echo %(x)s $%(x)s $%(x)s_abspath $%(x)s_relpath >> ${PREFIX}/deps' % dict(x=dep.name)
            for dep in pkg.deps)
        script_key = builder.source_cache.put('build.sh', script)
        spec = {"name": pkg.name, "version": "na",
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
        
@fixture()
def test_dependency_substitution(tempdir, sc, bldr):
    # Test that environment variables for dependencies are present in build environment
    libc = MockPackage("libc", [])
    blas = MockPackage("blas", [libc])
    numpy = MockPackage("numpy", [blas, libc])
    build_mock_packages(bldr, [libc, blas, numpy])
