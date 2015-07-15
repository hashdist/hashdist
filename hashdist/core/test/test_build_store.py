import os
from os.path import join as pjoin
import functools
import tempfile
import shutil
from textwrap import dedent
from pprint import pprint
import gzip
import json
from contextlib import closing
import subprocess
from pprint import pprint

from nose.tools import eq_
from nose import SkipTest

from .utils import which, logger, temp_dir, temp_working_dir, assert_raises
from . import utils

from .. import source_cache, build_store, InvalidBuildSpecError, BuildFailedError, InvalidJobSpecError
from ..common import SHORT_ARTIFACT_ID_LEN, IllegalBuildStoreError


#
# Simple tests
#
def test_shorten_artifact_id():
    assert ('foo/4ni' ==
            build_store.shorten_artifact_id('foo/4niostz3iktlg67najtxuwwgss5vl6k4', 3))
    with assert_raises(ValueError):
        build_store.shorten_artifact_id('foo-1.2-01234567890', 3)

def test_canonical_build_spec():
    doc = {
            "name" : "foo", "version": "r0",
            "build": {
                "import": [
                    {"id": "b"},
                    {"id": "c", "ref": "the_c"},
                    {"id": "a"}
                ]
            }
          }
    got = build_store.canonicalize_build_spec(doc)
    exp = {
          "build": {
            "import": [
              {'id': 'b', 'ref': None},
              {'id': 'c', 'ref': "the_c"},
              {'id': 'a', 'ref': None},
            ],
          },
          "name" : "foo", "version": "r0"
        }
    eq_(exp, got)

def test_strip_comments():
    raise SkipTest()
    doc = {"dependencies": [{"id": "a", "desc": "foo"}]}
    got = build_store.strip_comments(doc)
    eq_({"dependencies": [{"id": "a"}]}, got)
    eq_(got, build_store.strip_comments(got))


#
# Tests requiring fixture
#
def fixture():
    def decorator(func):
        @functools.wraps(func)
        def decorated():
            tempdir = tempfile.mkdtemp()
            try:
                os.makedirs(pjoin(tempdir, 'src'))
                os.makedirs(pjoin(tempdir, 'tmp'))
                os.makedirs(pjoin(tempdir, 'bld'))
                os.makedirs(pjoin(tempdir, 'gcroots'))

                config = {
                    'source_caches': [{'dir': pjoin(tempdir, 'src')}],
                    'build_stores': [{'dir': pjoin(tempdir, 'bld')}],
                    'build_temp': pjoin(tempdir, 'tmp'),
                    'gc_roots': pjoin(tempdir, 'gcroots'),
                    }

                sc = source_cache.SourceCache.create_from_config(config, logger)
                bldr = build_store.BuildStore.create_from_config(config, logger)
                return func(tempdir, sc, bldr, config)
            finally:
                os.system("chmod -R +w %s" % tempdir)
                shutil.rmtree(tempdir)
        return decorated
    return decorator

@fixture()
def test_basic(tempdir, sc, bldr, config):
    script_key = sc.put({'build.sh': dedent("""\
    echo hi stdout path=[$PATH] $EXTRA
    echo hi stderr>&2
    /usr/bin/find . > ${ARTIFACT}/hello
    """)})
    spec = {
        "name": "foo",
        "sources": [
            {"target": ".", "key": script_key},
            {"target": "subdir", "key": script_key}
            ],
        "files" : [{"target": "$ARTIFACT/$BAR/foo", "text": ["foo${BAR}foo"], "expandvars": True}],
        "build": {
            "commands": [
                {"set": "BAR", "value": "bar"},
                {"hit": ["build-write-files", "--key=files", "build.json"]},
                {"cmd": ["/bin/bash", "build.sh"]}
                ]
            }
        }

    assert not bldr.is_present(spec)
    name, path = bldr.ensure_present(spec, config, extra_env={'EXTRA': 'extra'})
    assert bldr.is_present(spec)
    eq_(['artifact.json', 'bar', 'build.json', 'build.log.gz', 'hello', 'id'],
        sorted(os.listdir(path)))
    with file(pjoin(path, 'hello')) as f:
        got = sorted(f.readlines())
        eq_(''.join(got), dedent('''\
        .
        ./_hashdist
        ./_hashdist/build.log
        ./build.json
        ./build.sh
        ./job
        ./subdir
        ./subdir/build.sh
        '''))
    with closing(gzip.open(pjoin(path, 'build.log.gz'))) as f:
        s = f.read()
        assert 'hi stdout path=[] extra' in s
        assert 'hi stderr' in s

    # files section
    assert 'foo' in os.listdir(pjoin(path, 'bar'))
    with file(pjoin(path, 'bar', 'foo')) as f:
        assert f.read() == 'foobarfoo'

@fixture()
def test_artifact_json(tempdir, sc, bldr, config):
    spec = {
        "name": "fooname",
        "build":{"commands": []}
        }
    name, path = bldr.ensure_present(spec, config)
    with open(pjoin(path, 'artifact.json')) as f:
        obj = json.load(f)

    expected = {
        "name": "fooname",
        "id": "fooname/cwfxs3bhjvlxoczwlxlexklpeoewybcn",
        "dependencies": []
        }
    assert expected == obj

@fixture()
def test_failing_build_and_multiple_commands(tempdir, sc, bldr, config):
    spec = {"name": "foo",
            "build": {
                "commands": [
                    {"cmd": [which("echo"), "test"], "append_to_file": "foo2"},
                    {"cmd": [which("true")]},
                    {"cmd": [which("false")]},
                ]
           }}
    try:
        bldr.ensure_present(spec, config, keep_build='error')
    except BuildFailedError, e_first:
        assert e_first.wrapped[0] is subprocess.CalledProcessError
        assert os.path.exists(pjoin(e_first.build_dir, 'foo2'))
    else:
        assert False

    try:
        bldr.ensure_present(spec, config, keep_build='never')
    except BuildFailedError, e_second:
        assert e_second.wrapped[0] is subprocess.CalledProcessError
        assert e_first.build_dir != e_second.build_dir
        assert not os.path.exists(pjoin(e_second.build_dir))
    else:
        assert False


@fixture()
def test_fail_to_find_dependency(tempdir, sc, bldr, config):
    for target in ["..", "/etc"]:
        spec = {"name": "foo",
                "build": {
                    "import": [{"ref": "bar", "id": "foo/01234567890123456789012345678901"}]}
                }
        with assert_raises(BuildFailedError):
            bldr.ensure_present(spec, config)

@fixture()
def test_hash_prefix_collision(tempdir, sc, bldr, config):
    spec = {"name": "foo",
            "build": {"commands": []}}
    artifact_id, path = bldr.ensure_present(spec, config)
    assert not artifact_id.endswith('x')
    patched_id = artifact_id[:-1] + 'x'
    with assert_raises(IllegalBuildStoreError) as e:
        bldr.resolve(patched_id)
    assert "collide in first 12 chars" in e.exc_val.message


@fixture()
def test_source_unpack_options(tempdir, sc, bldr, config):
    container_dir, tarball, tarball_key = utils.make_temporary_tarball([
        ('coolproject-2.3/README', 'Welcome!')
        ])
    try:
        sc.fetch('file:' + tarball, tarball_key)
    finally:
        shutil.rmtree(container_dir)
    spec = {
            "name": "foo",
            "sources": [
                {"target": ".", "key": tarball_key},
                {"target": "subdir", "key": tarball_key},
                ],
            "build": {
                "commands": [
                    {"cmd": ["/bin/cp", "subdir/README", "$ARTIFACT/a"]},
                    {"cmd": ["/bin/cp", "README", "$ARTIFACT/b"]},
                ]
            },
           }
    name, path = bldr.ensure_present(spec, config)
    with file(pjoin(path, 'a')) as f:
        assert f.read() == "Welcome!"
    with file(pjoin(path, 'b')) as f:
        assert f.read() == "Welcome!"


# To test more complex relationship with packages we need to automate a bit:

class MockPackage:
    def __init__(self, name, deps):
        self.name = name
        self.deps = deps


def build_mock_packages(builder, config, packages, virtuals={}, name_to_artifact=None):
    if name_to_artifact is None:
        name_to_artifact = {} # name -> (artifact_id, path)
    for pkg in packages:
        script = [which('touch') + ' ${ARTIFACT}/deps\n']
        script += ['echo %(x)s $%(x)s_ID $%(x)s_DIR >> ${ARTIFACT}/deps' % dict(x=dep.name)
                   for dep in pkg.deps]
        spec = {"name": pkg.name,
                "files" : [{"target": "build.sh", "text": script}],
                "build": {
                    "import": [{"ref": dep.name, "id": name_to_artifact[dep.name][0]}
                               for dep in pkg.deps],
                    "commands": [
                        {"hit": ["build-write-files", "--key=files", "build.json"]},
                        {"cmd": ["/bin/bash", "build.sh"]}
                        ]
                    },
                }
        artifact, path = builder.ensure_present(spec, config, virtuals=virtuals)
        name_to_artifact[pkg.name] = (artifact, path)

        with file(pjoin(path, 'deps')) as f:
            for line, dep in zip(f.readlines(), pkg.deps):
                d, artifact_id, abspath = line.split()
                assert d == dep.name
                assert abspath == name_to_artifact[d][1]
    return name_to_artifact

@fixture()
def test_dependency_substitution(tempdir, sc, bldr, config):
    # Test that environment variables for dependencies are present in build environment
    libc = MockPackage("libc", [])
    blas = MockPackage("blas", [libc])
    numpy = MockPackage("numpy", [blas, libc])
    build_mock_packages(bldr, config, [libc, blas, numpy])

@fixture()
def test_virtual_dependencies(tempdir, sc, bldr, config):
    blas = MockPackage("blas", [])
    blas_id, blas_path = build_mock_packages(bldr, config, [blas])["blas"]

    numpy = MockPackage("numpy", [MockPackage("blas", "virtual:blas/1.2.3")])

    with assert_raises(BuildFailedError):
        build_mock_packages(bldr, config, [numpy],
                            name_to_artifact={"blas": ("virtual:blas/1.2.3", blas_path)})

    build_mock_packages(bldr, config, [numpy], virtuals={"virtual:blas/1.2.3": blas_id},
                        name_to_artifact={"blas": ("virtual:blas/1.2.3", blas_path)})

