import os
from os.path import join as pjoin
import contextlib
import tempfile
import shutil
from textwrap import dedent

from nose.tools import assert_raises

from .utils import logger

from .. import source_cache, builder


@contextlib.contextmanager
def fixture():
    tempdir = tempfile.mkdtemp()
    try:
        os.makedirs(pjoin(tempdir, 'sources'))
        os.makedirs(pjoin(tempdir, 'artifacts'))
        sc = source_cache.SourceCache(pjoin(tempdir, 'sources'))
        bldr = builder.Builder(sc, pjoin(tempdir, 'artifacts'), logger)
        yield tempdir, sc, bldr
    finally:
        shutil.rmtree(tempdir)

def test_basic():
    with fixture() as (tempdir, sc, bldr):
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


def test_failing_build():
    with fixture() as (tempdir, sc, bldr):
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
    

def test_source_target_tries_to_escape():
    with fixture() as (tempdir, sc, bldr):
        for target in ["..", "/etc"]:
            spec = {"name": "foo",
                    "sources": [{"target": target, "key": "foo"}]
                    }
            with assert_raises(builder.InvalidBuildSpecError):
                bldr.ensure_present(spec)

