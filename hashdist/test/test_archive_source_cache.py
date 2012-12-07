import contextlib
import tempfile
import shutil

from nose.tools import assert_raises

from ..source_cache import ArchiveSourceCache

@contextlib.contextmanager
def temp_source_cache():
    tempdir = tempfile.mkdtemp()
    try:
        yield ArchiveSourceCache(tempdir)
    finally:
        shutil.rmtree(tempdir)    

def test_ensure_type():
    with temp_source_cache() as sc:
        assert sc._ensure_type('test.tar.gz', None) == 'tar.gz'
        assert sc._ensure_type('test.tar.gz', 'zip') == 'zip'
        with assert_raises(ValueError):
            sc._ensure_type('test.foo', None)
        with assert_raises(ValueError):
            sc._ensure_type('test.bar', 'foo')
