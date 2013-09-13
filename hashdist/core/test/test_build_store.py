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

from .utils import logger, temp_dir, temp_working_dir, assert_raises
from . import utils

from .. import source_cache, build_store, InvalidBuildSpecError, BuildFailedError, InvalidJobSpecError
from ..common import SHORT_ARTIFACT_ID_LEN


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
                    {"id": "c", "in_env": False, "ref": "the_c"},
                    {"id": "a"}
                ]
            }
          }
    got = build_store.canonicalize_build_spec(doc)
    exp = {
          "build": {
            "import": [
              {'id': 'b', 'in_env': True, 'ref': None},
              {'id': 'c', 'in_env': False, 'ref': "the_c"},
              {'id': 'a', 'in_env': True, 'ref': None},
            ],
            "nohash_params": {},
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
def fixture(short_hash_len=SHORT_ARTIFACT_ID_LEN, dir_pattern='{name}/{shorthash}'):
    def decorator(func):
        @functools.wraps(func)
        def decorated():
            tempdir = tempfile.mkdtemp()
            try:
                os.makedirs(pjoin(tempdir, 'src'))
                os.makedirs(pjoin(tempdir, 'opt'))
                os.makedirs(pjoin(tempdir, 'bld'))
                os.makedirs(pjoin(tempdir, 'db'))

                config = {
                    'sourcecache/sources': pjoin(tempdir, 'src'),
                    'sourcecache/mirror': '',
                    'builder/artifacts': pjoin(tempdir, 'opt'),
                    'builder/build-temp': pjoin(tempdir, 'bld'),
                    'global/db': pjoin(tempdir, 'db'),
                    'builder/artifact-dir-pattern': dir_pattern,
                    }
                
                sc = source_cache.SourceCache.create_from_config(config, logger)
                bldr = build_store.BuildStore.create_from_config(config, logger,
                                                                 short_hash_len=short_hash_len)
                return func(tempdir, sc, bldr, config)
            finally:
                os.system("chmod -R +w %s" % tempdir)
                shutil.rmtree(tempdir)
        return decorated
    return decorator

@fixture()
def test_basic(tempdir, sc, bldr, config):
    script_key = sc.put({'build.sh': dedent("""\
    echo hi stdout path=[$PATH]
    echo hi stderr>&2
    /usr/bin/find > ${ARTIFACT}/hello
    """)})
    spec = {
        "name": "foo",
        "version": "na",
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
    name, path = bldr.ensure_present(spec, config)
    assert bldr.is_present(spec)
    assert ['artifact.json', 'bar', 'build.json', 'build.log.gz', 'hello'] == sorted(os.listdir(path))
    with file(pjoin(path, 'hello')) as f:
        got = sorted(f.readlines())
        eq_(''.join(got), dedent('''\
        .
        ./build.json
        ./build.log
        ./build.sh
        ./job
        ./subdir
        ./subdir/build.sh
        '''))
    with closing(gzip.open(pjoin(path, 'build.log.gz'))) as f:
        s = f.read()
        assert 'hi stdout path=[]' in s
        assert 'hi stderr' in s

    # files section
    assert 'foo' in os.listdir(pjoin(path, 'bar'))
    with file(pjoin(path, 'bar', 'foo')) as f:
        assert f.read() == 'foobarfoo'

@fixture()
def test_artifact_json(tempdir, sc, bldr, config):
    artifact = {
        "name": "fooname",
        "version": "na",
        "profile_install": {"foo": "bar"},
        "on_import": ["baz"],
        }
    spec = dict(artifact)
    spec.update({"build":{"commands": []}})
    name, path = bldr.ensure_present(spec, config)
    with open(pjoin(path, 'artifact.json')) as f:
        obj = json.load(f)
    assert obj == artifact


@fixture()
def test_failing_build_and_multiple_commands(tempdir, sc, bldr, config):
    spec = {"name": "foo", "version": "na",
            "build": {
                "commands": [
                    {"cmd": ["/bin/echo", "test"], "append_to_file": "foo2"},
                    {"cmd": ["/bin/true"]},
                    {"cmd": ["/bin/false"]},
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
        spec = {"name": "foo", "version": "na",
                "build": {
                    "import": [{"ref": "bar", "id": "foo/01234567890123456789012345678901"}]}
                }
        with assert_raises(BuildFailedError):
            bldr.ensure_present(spec, config)

@fixture(short_hash_len=1)
def test_hash_prefix_collision(tempdir, sc, bldr, config):
    lines = []
    # do all build 
    for repeat in range(2):
        # by experimentation this was enough to get a couple of collisions;
        # changes to the hashing could change this a bit but assertions below will
        # warn in those cases
        hashparts = []
        for k in range(15):
            spec = {"name": "foo", "version": "na",
                    "build": {
                        "commands": [{"cmd": ["/bin/echo", "hello", str(k)]}]
                        }
                    }
            artifact_id, path = bldr.ensure_present(spec, config)
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
            "version": "na",
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
        script = ['/bin/touch ${ARTIFACT}/deps\n']
        script += ['echo %(x)s $%(x)s_ID $%(x)s >> ${ARTIFACT}/deps' % dict(x=dep.name)
                   for dep in pkg.deps]
        spec = {"name": pkg.name, "version": "na",
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
    
