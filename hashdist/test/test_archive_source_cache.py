import os
import contextlib
import tempfile
import shutil
import subprocess

pjoin = os.path.join

from nose.tools import assert_raises

from ..source_cache import ArchiveSourceCache, SourceCache
from ..hash import create_hasher, encode_digest

from .utils import temp_dir

@contextlib.contextmanager
def temp_source_cache():
    tempdir = tempfile.mkdtemp()
    try:
        yield SourceCache(tempdir)
    finally:
        shutil.rmtree(tempdir)    


mock_archive = None
mock_archive_hash = None
mock_archive_tmpdir = None

def make_mock_archive():
    global mock_archive, mock_archive_tmpdir, mock_archive_hash
    mock_archive_tmpdir = tempfile.mkdtemp()
    mock_archive = pjoin(mock_archive_tmpdir, 'somearchive.tar.gz')
    tmp_d = tempfile.mkdtemp()
    try:
        with file(pjoin(tmp_d, 'README'), 'w') as f:
            f.write('file contents')
        subprocess.check_call(['tar', 'czf', mock_archive, 'README'], cwd=tmp_d)
    finally:
        shutil.rmtree(tmp_d)
    # get hash
    with file(mock_archive) as f:
        mock_archive_hash = encode_digest(create_hasher(f.read()))

def setup():
    make_mock_archive()

def teardown():
    shutil.rmtree(mock_archive_tmpdir)

def test_basic():
    with temp_source_cache() as sc:
        key = sc.fetch_archive('file:' + mock_archive)
        assert key == mock_archive_hash
        with temp_dir() as d:
            sc.unpack(key, d)
            with file(pjoin(d, 'README')) as f:
                assert f.read() == 'file contents'

def test_hash_check():
    with temp_source_cache() as sc:
        sc.fetch_archive('file:' + mock_archive, mock_archive_hash)

def test_corrupt_download():
    with temp_source_cache() as sc:
        with assert_raises(RuntimeError):
            sc.fetch_archive('file:' + mock_archive, mock_archive_hash[1:] + 'a')
        # Check that no temporary files are left
        assert len(os.listdir(pjoin(sc.cache_path, 'packs'))) == 0

def test_does_not_re_download():
    with temp_source_cache() as sc:
        sc.fetch_archive('file:' + mock_archive, mock_archive_hash)
        # next line does not error because it finds it already by hash
        sc.fetch_archive('file:does-not-exist', mock_archive_hash)

def test_ensure_type():
    with temp_source_cache() as sc:
        asc = ArchiveSourceCache(sc.cache_path)
        assert asc._ensure_type('test.tar.gz', None) == 'tar.gz'
        assert asc._ensure_type('test.tar.gz', 'zip') == 'zip'
        with assert_raises(ValueError):
            asc._ensure_type('test.foo', None)
        with assert_raises(ValueError):
            asc._ensure_type('test.bar', 'foo')

def test_put():
    with temp_source_cache() as sc:
        key = sc.put('foofile', 'the contents')
        with temp_dir() as d:
            sc.unpack(key, d)
            with file(pjoin(d, 'foofile')) as f:
                assert f.read() == 'the contents'
    

def test_simple_file_url_re():
    from ..source_cache import SIMPLE_FILE_URL_RE
    assert SIMPLE_FILE_URL_RE.match('file:foo')
    assert SIMPLE_FILE_URL_RE.match('file:foo/bar')
    assert SIMPLE_FILE_URL_RE.match('file:foo/bar/')
    assert SIMPLE_FILE_URL_RE.match('file:/foo')
    assert SIMPLE_FILE_URL_RE.match('file:/foo/bar')
    assert SIMPLE_FILE_URL_RE.match('file:/foo/bar/')
    assert not SIMPLE_FILE_URL_RE.match('file://foo')
    assert not SIMPLE_FILE_URL_RE.match('file:///foo')
    assert not SIMPLE_FILE_URL_RE.match('file://localhost/foo')

    
