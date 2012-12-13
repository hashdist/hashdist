import os
import contextlib
import tempfile
import shutil
import subprocess
import hashlib
from StringIO import StringIO

pjoin = os.path.join

from nose.tools import assert_raises

from ..source_cache import (ArchiveSourceCache, SourceCache, CorruptSourceCacheError,
                            hdist_pack, hdist_unpack, scatter_files)
from ..hasher import Hasher, format_digest

from .utils import temp_dir, working_directory, VERBOSE

#
# Fixture
#

mock_archive = None
mock_archive_hash = None
mock_archive_tmpdir = None

mock_git_repo = None
mock_git_commit = None

@contextlib.contextmanager
def temp_source_cache():
    tempdir = tempfile.mkdtemp()
    try:
        yield SourceCache(tempdir)
    finally:
        shutil.rmtree(tempdir)    


def setup():
    global mock_git_repo, mock_git_commit
    mock_git_repo = tempfile.mkdtemp()
    mock_git_commit = make_mock_git_repo()
    make_mock_archive()
        
def teardown():
    shutil.rmtree(mock_git_repo)
    shutil.rmtree(mock_archive_tmpdir)


# Mock tarball

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
        mock_archive_hash = format_digest(hashlib.sha256(f.read()))

# Mock git repo

def git(*args, **kw):
    repo = kw['repo']
    git_env = dict(os.environ)
    git_env['GIT_DIR'] = repo
    p = subprocess.Popen(['git'] + list(args), env=git_env, stdout=subprocess.PIPE,
                         stderr=None if VERBOSE else subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError('git call %r failed with code %d' % (args, p.returncode))
    return out

def cat(filename, what):
    with file(filename, 'w') as f:
        f.write(what)

def make_mock_git_repo():
    with working_directory(mock_git_repo):
        repo = os.path.join(mock_git_repo, '.git')
        git('init', repo=repo)
        cat('README', 'First revision',)
        git('add', 'README', repo=repo)
        git('commit', '-m', 'First revision', repo=repo)
        commit = git('rev-list', '-n1', 'HEAD', repo=repo).strip()
        return commit        

#
# Tests
#

def test_archive():
    with temp_source_cache() as sc:
        key = sc.fetch_archive('file:' + mock_archive)
        assert key == mock_archive_hash
        with temp_dir() as d:
            sc.unpack(key, d)
            with file(pjoin(d, 'README')) as f:
                assert f.read() == 'file contents'

def test_git():
    with temp_source_cache() as sc:
        key = sc.fetch_git(mock_git_repo, 'master')
        assert key == 'git:%s' % mock_git_commit
        with temp_dir() as d:
            sc.unpack(key, pjoin(d, 'foo'))
            with file(pjoin(d, 'foo', 'README')) as f:
                assert f.read() == 'First revision'

def test_able_to_fetch_twice():
    # With 'master' rev
    with temp_source_cache() as sc:
        result = sc.fetch_git(mock_git_repo, 'master')
        assert result == 'git:%s' % mock_git_commit
        result = sc.fetch_git(mock_git_repo, 'master')
        assert result == 'git:%s' % mock_git_commit
    # with commit as rev
    with temp_source_cache() as sc:
        result = sc.fetch_git(mock_git_repo, mock_git_commit)
        assert result == 'git:%s' % mock_git_commit
        result = sc.fetch_git(mock_git_repo, mock_git_commit)
        assert result == 'git:%s' % mock_git_commit

def test_hash_check():
    with temp_source_cache() as sc:
        sc.fetch_archive('file:' + mock_archive, mock_archive_hash)

def test_corrupt_download():
    with temp_source_cache() as sc:
        with assert_raises(RuntimeError):
            sc.fetch_archive('file:' + mock_archive, mock_archive_hash[1:] + 'a')
        # Check that no temporary files are left
        assert len(os.listdir(pjoin(sc.cache_path, 'packs'))) == 0

def test_corrupt_store():
    with temp_source_cache() as sc:
        key = sc.fetch_archive('file:' + mock_archive)
        with file(pjoin(sc.cache_path, 'packs', mock_archive_hash), 'w') as f:
            f.write('corrupt archive')
        with temp_dir() as d:
            with assert_raises(CorruptSourceCacheError):
                sc.unpack(mock_archive_hash, d, unsafe_mode=False)
            assert os.listdir(d) == []
        with temp_dir() as d:
            with assert_raises(CorruptSourceCacheError):
                sc.unpack(mock_archive_hash, d, unsafe_mode=True)        


def test_does_not_re_download():
    with temp_source_cache() as sc:
        sc.fetch_archive('file:' + mock_archive, mock_archive_hash)
        # next line does not error because it finds it already by hash
        sc.fetch_archive('file:does-not-exist', mock_archive_hash)

def test_ensure_type():
    with temp_source_cache() as sc:
        asc = ArchiveSourceCache(sc.cache_path)
        assert asc._ensure_type('test.tar.gz', None) == 'tar.gz'
        assert asc._ensure_type('test.tar.gz', 'tar.bz2') == 'tar.bz2'
        with assert_raises(ValueError):
            asc._ensure_type('test.foo', None)
        with assert_raises(ValueError):
            asc._ensure_type('test.bar', 'foo')

def test_put():
    with temp_source_cache() as sc:
        key = sc.put({'foofile': 'the contents'})
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

def test_hdist_pack():
    files = [('foo', 'contains foo'),
             ('bar', 'contains bar'),
             ('a/b', 'in a subdir'),
             ('a/c', 'also in subdir')]
    stream = StringIO()
    key = hdist_pack(files, stream)
    pack = stream.getvalue()
    assert key == 'files:jSynkRp09Ff-7MN03TeTmQtABAFWMIE7o+SYLTI6oXg'
    assert hdist_pack(files[::-1]) == key
    unpacked_files = hdist_unpack(StringIO(pack), key)
    assert sorted(files) == sorted(unpacked_files)

def test_scatter_files():
    files = [('foo', 'contains foo'),
             ('bar', 'contains bar'),
             ('a/b', 'in a subdir'),
             ('a/c', 'also in subdir'),
             ('a/x/y', 'further subdir')]
    with temp_dir() as d:
        scatter_files(files, d)
        assert sorted(os.listdir(d)) == ['a', 'bar', 'foo']
        assert sorted(os.listdir(pjoin(d, 'a'))) == ['b', 'c', 'x']
        assert sorted(os.listdir(pjoin(d, 'a', 'x'))) == ['y']
        with file(pjoin(d, 'a', 'b')) as f:
            assert f.read() == 'in a subdir'
