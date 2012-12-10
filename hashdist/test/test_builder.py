import os
from os.path import join as pjoin
import contextlib
import tempfile
import shutil
from textwrap import dedent

from nose.tools import assert_raises

from .. import source_cache, builder

@contextlib.contextmanager
def fixture():
    tempdir = tempfile.mkdtemp()
    try:
        os.makedirs(pjoin(tempdir, 'sources'))
        os.makedirs(pjoin(tempdir, 'artifacts'))
        sc = source_cache.SourceCache(pjoin(tempdir, 'sources'))
        bldr = builder.Builder(sc, pjoin(tempdir, 'artifacts'))
        yield tempdir, sc, bldr
    finally:
        shutil.rmtree(tempdir)

def test_basic():
    with fixture() as (tempdir, sc, bldr):
        script_key = sc.put('build.sh', dedent('''\
        echo hi stdout
        echo hi stderr>&2
        echo hello > hello
        '''))
        
        spec = {
            "name" : "foo",
            "version" : "1.6",
            "dependencies" : {},
            "sources" : [
                {"target" : ".", "key" : script_key}
                ],
            "command" : ["/bin/bash", "build.sh"]
            }
        assert not bldr.is_present(spec)
        
        name, path = bldr.ensure_present(spec)
        assert ['build.json', 'build.log', 'build.sh', 'hello'] == sorted(os.listdir(path))
        with file(pjoin(path, 'hello')) as f:
            assert f.read() == 'hello\n'
        with file(pjoin(path, 'build.log')) as f:
            s =  f.read()
            assert 'hi stdout' in s
            assert 'hi stderr' in s

def test_escape():
    with fixture() as (tempdir, sc, bldr):
        for target in ["..", "/etc"]:
            spec = {"name" : "foo",
                    "sources" : [{"target" : target, "key" : "foo"}]
                    }
            with assert_raises(builder.InvalidBuildSpecError):
                bldr.ensure_present(spec)

