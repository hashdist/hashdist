import os
import contextlib
import tempfile
import shutil
import subprocess

pjoin = os.path.join

from nose.tools import assert_raises

from ..source_cache import ArchiveSourceCache, SourceCache

from .utils import temp_dir

@contextlib.contextmanager
def temp_source_cache():
    tempdir = tempfile.mkdtemp()
    try:
        yield SourceCache(tempdir)
    finally:
        shutil.rmtree(tempdir)    


mock_archive = None
mock_archive_tmpdir = None

def make_mock_archive():
    global mock_archive, mock_archive_tmpdir
    mock_archive_tmpdir = tempfile.mkdtemp()
    mock_archive = pjoin(mock_archive_tmpdir, 'somearchive.tar.gz')

    tmp_d = tempfile.mkdtemp()
    with file(pjoin(tmp_d, 'README'), 'w') as f:
        f.write('file contents')
    subprocess.check_call(['tar', 'czf', mock_archive, 'README'], cwd=tmp_d)
    shutil.rmtree(tmp_d)

def setup():
    make_mock_archive()

def teardown():
    shutil.rmtree(mock_archive_tmpdir)

def test_basic():
    with temp_source_cache() as sc:
        key = sc.fetch_archive('file:' + mock_archive, None)
        with temp_dir() as d:
            sc.unpack(key, pjoin(d, 'foo'))
            with file(pjoin(d, 'foo', 'README')) as f:
                assert f.read() == 'file contents'

def test_ensure_type():
    with temp_source_cache() as sc:
        asc = ArchiveSourceCache(sc.cache_path)
        assert asc._ensure_type('test.tar.gz', None) == 'tar.gz'
        assert asc._ensure_type('test.tar.gz', 'zip') == 'zip'
        with assert_raises(ValueError):
            asc._ensure_type('test.foo', None)
        with assert_raises(ValueError):
            asc._ensure_type('test.bar', 'foo')
