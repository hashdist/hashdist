import os
from os.path import join as pjoin
import functools
import tempfile
import shutil
from textwrap import dedent

from nose.tools import assert_raises, eq_

from .utils import logger, temp_dir
from . import utils

from .. import source_cache, build_store


#
# Simple tests
#
def test_shorten_artifact_id():
    assert 'foo/1.2/012' == build_store.build_spec.shorten_artifact_id('foo/1.2/01234567890', 3)
    with assert_raises(ValueError):
        build_store.build_spec.shorten_artifact_id('foo-1.2-01234567890', 3)

def test_rmtree_up_to():
    with temp_dir() as d:
        # Incomplete removal
        os.makedirs(pjoin(d, 'a', 'x', 'A', '2'))
        os.makedirs(pjoin(d, 'a', 'x', 'B', '2'))
        build_store.builder.rmtree_up_to(pjoin(d, 'a', 'x', 'A', '2'), d)
        assert ['B'] == os.listdir(pjoin(d, 'a', 'x'))

        # Invalid parent parameter
        with assert_raises(ValueError):
            build_store.builder.rmtree_up_to(pjoin(d, 'a', 'x', 'B'), '/nonexisting')

        # Complete removal -- do not actually remove the parent
        build_store.builder.rmtree_up_to(pjoin(d, 'a', 'x', 'B', '2'), d)
        assert os.path.exists(d)

        # Parent is exclusive
        build_store.builder.rmtree_up_to(d, d)
        assert os.path.exists(d)

def test_canonical_build_spec():
    doc = {
            "name" : "foo", "version": "r0",
            "sources" : [
              {"key": "git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3"},
              {"key": "tar.bz2:RB1JbykVljxdvL07mN60y9V9BVCruWRky2FpK2QCCow", "target": "sources", "strip": 1},
              {"key": "files:5fcANXHsmjPpukSffBZF913JEnMwzcCoysn-RZEX7cM"}
            ],
            "files" : [
              {"target": "zsh-build", "contents": []},
              {"target": "build.sh", "contents": []}
            ]
          }
    eq_({
          "name" : "foo", "version": "r0",
          "sources" : [
            {"key": "files:5fcANXHsmjPpukSffBZF913JEnMwzcCoysn-RZEX7cM", "target" : ".", "strip" : 0},
            {"key": "git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3", "target" : ".", "strip" : 0},
            {"key": "tar.bz2:RB1JbykVljxdvL07mN60y9V9BVCruWRky2FpK2QCCow", "target": "sources", "strip": 1},
          ],
          "files" : [
            {"target": "build.sh", "contents": []},
            {"target": "zsh-build", "contents": []},
          ]
        },
        build_store.build_spec.canonicalize_build_spec(doc))
        
#
# Tests requiring fixture
#
def fixture(ARTIFACT_ID_LEN=None):
    def decorator(func):
        @functools.wraps(func)
        def decorated():
            old_aid_len = build_store.builder.ARTIFACT_ID_LEN
            tempdir = tempfile.mkdtemp()
            try:
                if ARTIFACT_ID_LEN is not None:
                    build_store.builder.ARTIFACT_ID_LEN = ARTIFACT_ID_LEN
                os.makedirs(pjoin(tempdir, 'src'))
                os.makedirs(pjoin(tempdir, 'opt'))
                os.makedirs(pjoin(tempdir, 'bld'))
                sc = source_cache.SourceCache(pjoin(tempdir, 'src'))
                bldr = build_store.BuildStore(pjoin(tempdir, 'bld'), pjoin(tempdir, 'opt'), logger)
                return func(tempdir, sc, bldr)
            finally:
                build_store.builder.ARTIFACT_ID_LEN = old_aid_len
                shutil.rmtree(tempdir)
        return decorated
    return decorator

@fixture()
def test_basic(tempdir, sc, bldr):
    script_key = sc.put({'build.sh': dedent("""\
    echo hi stdout
    echo hi stderr>&2
    find > ${TARGET}/hello
    """)})
    spec = {
        "name": "foo",
        "version": "na",
        "sources": [
            {"target": ".", "key": script_key},
            {"target": "subdir", "key": script_key}
            ],
        "commands": [["/bin/bash", "build.sh"]]
        }
    assert not bldr.is_present(spec)
    name, path = bldr.ensure_present(spec, sc)
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


@fixture()
def test_failing_build_and_multiple_commands(tempdir, sc, bldr):
    spec = {"name": "foo", "version": "na",
            "commands": [["/bin/true"],
                         ["/bin/false"]],
            "files" : [{"target": "foo", "contents": ["foo"]}]
           }
    try:
        bldr.ensure_present(spec, sc, keep_build='error')
    except build_store.BuildFailedError, e_first:
        assert os.path.exists(pjoin(e_first.build_dir, 'foo'))
    else:
        assert False

    try:
        bldr.ensure_present(spec, sc, keep_build='never')
    except build_store.BuildFailedError, e_second:
        assert e_first.build_dir != e_second.build_dir
        assert not os.path.exists(pjoin(e_second.build_dir))
    else:
        assert False
    

@fixture()
def test_source_target_tries_to_escape(tempdir, sc, bldr):
    for target in ["..", "/etc"]:
        spec = {"name": "foo", "version": "na",
                "sources": [{"target": target, "key": "foo"}]
                }
        with assert_raises(build_store.InvalidBuildSpecError):
            bldr.ensure_present(spec, sc)


@fixture()
def test_fail_to_find_dependency(tempdir, sc, bldr):
    for target in ["..", "/etc"]:
        spec = {"name": "foo", "version": "na",
                "dependencies": [{"ref": "bar", "id": "bogushash"}]}
        with assert_raises(build_store.InvalidBuildSpecError):
            bldr.ensure_present(spec, sc)

@fixture(ARTIFACT_ID_LEN=1)
def test_hash_prefix_collision(tempdir, sc, bldr):
    lines = []
    # do all build 
    for repeat in range(2):
        # by experimentation this was enough to get a couple of collisions;
        # changes to the hashing could change this a bit but assertions below will
        # warn in those cases
        hashparts = []
        for k in range(12):
            script_key = sc.put({'build.sh': 'echo hello %d; exit 0' % k})
            spec = {"name": "foo", "version": "na",
                    "sources": [{"key": script_key}],
                    "commands": [["/bin/bash", "build.sh"]]}
            artifact_id, path = bldr.ensure_present(spec, sc)
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
    
@fixture()
def test_source_unpack_options(tempdir, sc, bldr):
    container_dir, tarball, tarball_key = utils.make_temporary_tarball([
        ('coolproject-2.3/README', 'Welcome!')
        ])
    try:
        sc.fetch_archive('file:' + tarball, tarball_key)
    finally:
        shutil.rmtree(container_dir)
    spec = {
           "name": "foo",
           "version": "na",
           "sources": [
               {"target": ".", "key": tarball_key, "strip": 1},
               {"target": "subdir", "key": tarball_key, "strip": 0},
               ],
           "commands": [["/bin/bash", "build.sh"]],
           "files": [
                {
                    "target": "build.sh",
                    "contents": [
                        "cp subdir/coolproject-2.3/README $TARGET/a",
                        "cp README $TARGET/b",
                    ]
                }
           ]
        }
    name, path = bldr.ensure_present(spec, sc)
    with file(pjoin(path, 'a')) as f:
        assert f.read() == "Welcome!"
    with file(pjoin(path, 'b')) as f:
        assert f.read() == "Welcome!"
    

# To test more complex relationship with packages we need to automate a bit:

class MockPackage:
    def __init__(self, name, deps):
        self.name = name
        self.deps = deps


def build_mock_packages(builder, source_cache, packages):
    name_to_artifact = {} # name -> (artifact_id, path)
    for pkg in packages:
        script = 'touch ${TARGET}/deps\n'
        script += '\n'.join(
            'echo %(x)s $%(x)s_id $%(x)s $%(x)s_relpath >> ${TARGET}/deps' % dict(x=dep.name)
            for dep in pkg.deps)
        script_key = source_cache.put({'build.sh': script})
        spec = {"name": pkg.name, "version": "na",
                "dependencies": [{"ref": dep.name, "id": name_to_artifact[dep.name][0]}
                                 for dep in pkg.deps],
                "sources": [{"key": script_key}],
                "commands": [["/bin/bash", "build.sh"]]}
        artifact, path = builder.ensure_present(spec, source_cache)
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
    build_mock_packages(bldr, sc, [libc, blas, numpy])
