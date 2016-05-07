import os
import contextlib
import tempfile
import shutil
import subprocess
import hashlib
from StringIO import StringIO
import stat
import errno
import logging
from contextlib import closing

pjoin = os.path.join

from ..source_cache import (ArchiveSourceCache, SourceCache,
        CorruptSourceCacheError, hit_pack, hit_unpack, scatter_files,
        KeyNotFoundError, SourceNotFoundError, SecurityError, RemoteFetchError)
from ..hasher import Hasher, format_digest

from .utils import temp_dir, working_directory, VERBOSE, logger, assert_raises
from . import utils
from hashdist.util.logger_fixtures import log_capture

from nose.tools import eq_

#
# Fixture
#

mock_tarball = None
mock_tarball_hash = None
mock_tarball_tmpdir = None

mock_git_repo = None
mock_git_commit = None

@contextlib.contextmanager
def temp_source_cache(logger=logger):
    tempdir = tempfile.mkdtemp()
    try:
        yield SourceCache(tempdir, logger)
    finally:
        shutil.rmtree(tempdir)


def setup():
    global mock_git_repo, mock_git_commit, mock_git_devel_branch_commit, mock_container_dir
    mock_container_dir = tempfile.mkdtemp()
    mock_git_repo, mock_git_commit, mock_git_devel_branch_commit = make_mock_git_repo(mock_git_repo)
    make_mock_tarball()
    make_mock_zipfile()

def teardown():
    shutil.rmtree(mock_git_repo)
    shutil.rmtree(mock_tarball_tmpdir)
    shutil.rmtree(mock_container_dir)

# Mock packs

def make_mock_tarball():
    import tarfile

    global mock_tarball, mock_tarball_tmpdir, mock_tarball_hash
    global mock_dangerous_tarballs

    mock_tarball_tmpdir, mock_tarball,  mock_tarball_hash = utils.make_temporary_tarball(
        [('a/b/0/README', 'file contents'),
         ('a/b/1/README', 'file contents')])

    import tarfile
    mock_dangerous_tarballs = [pjoin(mock_container_dir, 'danger%d.tar.gz' % i) for i in range(2)]
    contentsfile = pjoin(mock_container_dir, 'tmp')
    with open(contentsfile, 'w') as f:
        f.write('hello')
    for attackname, filename in zip(['/escapes', '../escapes'], mock_dangerous_tarballs):
        with closing(tarfile.open(filename, 'w:gz')) as f:
            info = tarfile.TarInfo(attackname)
            info.size = len('hello')
            with open(pjoin(mock_container_dir, 'tmp')) as f2:
                f.addfile(info, f2)

def make_mock_zipfile():
    global mock_zipfile, mock_zipfile_hash
    from zipfile import ZipFile
    mock_zipfile = pjoin(mock_container_dir, 'test.zip')
    with closing(ZipFile(mock_zipfile, 'a')) as z:
        # a/b is common prefix and should be stripped on unpacking
        z.writestr(pjoin('a', 'b', '0', 'README'), 'file contents')
        z.writestr(pjoin('a', 'b', '1', 'README'), 'file contents')
    with open(mock_zipfile) as f:
        mock_zipfile_hash = 'zip:' + format_digest(hashlib.sha256(f.read()))


# Mock git repo

def git(*args, **kw):
    repo = kw['repo']
    git_env = dict(os.environ)
    git_env['CWD'] = repo
    p = subprocess.Popen(['git'] + list(args), env=git_env, stdout=subprocess.PIPE,
                         stderr=None if VERBOSE else subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError('git call %r failed with code %d' % (args, p.returncode))
    return out

def cat(filename, what):
    with file(filename, 'w') as f:
        f.write(what)

def make_mock_git_repo(submodules=None):
    mock_git_repo = tempfile.mkdtemp()
    with working_directory(mock_git_repo):
        repo = os.path.join(mock_git_repo, '.git')
        git('init', repo=repo)
        git('config', 'user.name', 'Hashdist User', repo=repo)
        git('config', 'user.email', 'hashdistuser@example.com', repo=repo)
        cat('README', 'First revision')
        git('add', 'README', repo=repo)
        if submodules:
            #config = '\n'.join(
            #    '[submodule "%s"]        path = %s\n        url = %s\n' % (name, name, url)
            #    for name, url in submodules.items())
            #cat('.gitmodules', config)
            #git('add', '.gitmodules')
            for name, url in submodules.items():
                git('submodule', 'add', url, name, repo=repo)
        git('commit', '-m', 'First revision', repo=repo)
        master_commit = git('rev-list', '-n1', 'HEAD', repo=repo).strip()
        cat('README', 'Second revision')
        git('checkout', '-b', 'devel', repo=repo)
        git('add', 'README', repo=repo)
        git('commit', '-m', 'Second revision', repo=repo)
        devel_commit = git('rev-list', '-n1', 'HEAD', repo=repo).strip()
        return mock_git_repo, master_commit, devel_commit

#
# Tests
#

def test_common_prefix():
    from ..source_cache import common_path_prefix
    def f(lst):
        return common_path_prefix([pjoin(*x.split('/')) for x in lst])

    eq_('a/b/c/d/', f(['a/b/c/d/e']))
    eq_('a/', f(['a/c', 'a/d']))
    eq_('a/b/', f(['a/b/c', 'a/b/d']))
    eq_('', f(['a/b/c', 'a/b/d', 'a']))
    eq_('', f(['a', 'a/b/c', 'a/b/d']))
    eq_('a/b/c/d/', f(['a/b/c/d/e/0', 'a/b/c/d/e/1', 'a/b/c/d/1']))


def test_trap_tarball_attack():
    logger = logging.getLogger()
    with temp_source_cache(logger) as sc:
        for tb in mock_dangerous_tarballs:
            with log_capture() as logger:
                key = sc.fetch_archive('file:' + tb)
                with temp_dir() as d:
                    with assert_raises(SecurityError):
                        sc.unpack(key, d)
            logger.assertLogged('^ERROR:.*attempted to break out')

def test_tarball():
    with temp_source_cache() as sc:
        key = sc.fetch_archive('file:' + mock_tarball)
        assert key == mock_tarball_hash
        with temp_dir() as d:
            sc.unpack(key, d)
            with file(pjoin(d, '0', 'README')) as f:
                assert f.read() == 'file contents'
            with file(pjoin(d, '1', 'README')) as f:
                assert f.read() == 'file contents'


def test_zipfile():
    with temp_source_cache() as sc:
        key = sc.fetch_archive('file:' + mock_zipfile)
        assert key == mock_zipfile_hash
        with temp_dir() as d:
            sc.unpack(key, d)
            with file(pjoin(d, '0', 'README')) as f:
                assert f.read() == 'file contents'
            with file(pjoin(d, '1', 'README')) as f:
                assert f.read() == 'file contents'


def test_curl_errors():
    with temp_source_cache() as sc:
        with assert_raises(ValueError):
            sc.fetch_archive('/tmp/foo/garbage.tar.gz') # malformed, would need file: prefix
        with assert_raises(RemoteFetchError):
            sc.fetch_archive('http://localhost:999/foo.tar.gz')


def test_stable_archive_hash():
    fixed_tarball = pjoin(os.path.dirname(__file__), 'archive.tar.gz')
    with temp_source_cache() as sc:
        key = sc.fetch_archive('file:' + fixed_tarball)
        assert key == 'tar.gz:4niostz3iktlg67najtxuwwgss5vl6k4'
        assert key != mock_tarball_hash

def test_git_fetch_git():
    with temp_source_cache() as sc:
        key = sc.fetch_git(mock_git_repo, 'master', 'foo')
        assert key == 'git:%s' % mock_git_commit

        devel_key = sc.fetch_git(mock_git_repo, 'devel', 'foo')
        assert devel_key == 'git:%s' % mock_git_devel_branch_commit

        with temp_dir() as d:
            sc.unpack(key, pjoin(d, 'foo'))
            with file(pjoin(d, 'foo', 'README')) as f:
                assert f.read() == 'First revision'
            # The unpack should be a git checkout positioned in the right commit
            with working_directory(pjoin(d, 'foo')):
                assert os.path.isdir('.git')
                p = subprocess.Popen(['git', 'rev-parse', 'HEAD'], stdout=subprocess.PIPE,
                                     stderr=None if VERBOSE else subprocess.PIPE)
                out, err = p.communicate()
                assert p.wait() == 0
                assert out.strip() == mock_git_commit

def test_git_fetch():
    with temp_source_cache() as sc:
        sc.fetch(mock_git_repo, 'git:' + mock_git_commit, 'foo')
        sc.fetch(mock_git_repo, 'git:' + mock_git_devel_branch_commit, 'foo')
        sc.fetch('git://not-valid', 'git:' + mock_git_commit, 'foo')
        sc.fetch(None, 'git:' + mock_git_commit, 'foo')

def test_git_fetch_submodules():
    root_repo, master_commit, devel_commit = make_mock_git_repo(submodules={'subdir/submod': mock_git_repo,
                                                                            'submod': mock_git_repo})
    with temp_source_cache() as sc:
        # A 'fetch' should recursively fetch the submodules and give them dotted names
        sc.fetch(root_repo, 'git:' + master_commit, 'rootproject')
        assert (os.listdir(pjoin(sc.cache_path, 'git')).sort() ==
                ['rootproject', 'rootproject.submod', 'rootproject.subdir.submod'].sort())
        # An unpack should include the submodules
        with temp_dir() as d:
            sc.unpack('git:' + master_commit, d)
            for path, content in {('README',): 'First revision',
                                  ('submod', 'README'): 'Second revision',
                                  ('subdir', 'submod', 'README'): 'Second revision'}.items():
                with open(pjoin(d, *path)) as f:
                    s = f.read()
                    assert s == content

def test_unpack_nonexisting_git():
    with temp_source_cache() as sc:
        with temp_dir() as d:
            with assert_raises(KeyNotFoundError):
                sc.unpack('git:267897bb6a35ad602943612ab61d252341fe27b2', pjoin(d, 'foo'))

def test_unpack_nonexisting_tarball():
    with temp_source_cache() as sc:
        with temp_dir() as d:
            with assert_raises(KeyNotFoundError):
                sc.unpack('tar.gz:4niostz3iktlg67najtxuwwgss5vl6k4', pjoin(d, 'bar'))

def test_able_to_fetch_twice():
    # With 'master' rev
    with temp_source_cache() as sc:
        result = sc.fetch_git(mock_git_repo, 'master', 'foo')
        assert result == 'git:%s' % mock_git_commit
        result = sc.fetch_git(mock_git_repo, 'master', 'foo')
        assert result == 'git:%s' % mock_git_commit

def test_hash_check():
    with temp_source_cache() as sc:
        sc.fetch('file:' + mock_tarball, mock_tarball_hash)

def test_corrupt_download():
    with temp_source_cache() as sc:
        with assert_raises(RuntimeError):
            corrupt_hash = mock_tarball_hash[:-8] + 'aaaaaaaa'
            sc.fetch('file:' + mock_tarball, corrupt_hash)
        with assert_raises(RuntimeError):
            corrupt_hash = mock_zipfile_hash[:-8] + 'aaaaaaaa'
            sc.fetch('file:' + mock_zipfile, corrupt_hash)
        # Check that no temporary files are left
        assert len(os.listdir(pjoin(sc.cache_path, 'packs', 'tar.gz'))) == 0

def test_corrupt_store():
    with temp_source_cache() as sc:
        key = sc.fetch_archive('file:' + mock_tarball)
        pack_filename = pjoin(sc.cache_path, 'packs', 'tar.gz', mock_tarball_hash.split(':')[1])
        os.chmod(pack_filename, stat.S_IRUSR | stat.S_IWUSR)
        with file(pack_filename, 'w') as f:
            f.write('corrupt archive')
        with temp_dir() as d:
            with assert_raises(CorruptSourceCacheError):
                sc.unpack(mock_tarball_hash, d)
            assert os.listdir(d) == []


def test_does_not_re_download():
    with temp_source_cache() as sc:
        sc.fetch('file:' + mock_tarball, mock_tarball_hash)
        # next line does not error because it finds it already by hash
        sc.fetch('file:does-not-exist', mock_tarball_hash)
        # passing None is ok too
        sc.fetch(None, mock_tarball_hash)

def test_ensure_type():
    with temp_source_cache() as sc:
        asc = ArchiveSourceCache(sc)
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
    key = hit_pack(files, stream)
    pack = stream.getvalue()
    assert key == 'files:ruwkpei2ot2fp77myn2n2n4ttefuabab'
    assert hit_pack(files[::-1]) == key
    unpacked_files = hit_unpack(StringIO(pack), key)
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

        # duplicate file error
        try:
            scatter_files(files, d)
        except OSError, e:
            assert e.errno == errno.EEXIST
        else:
            assert False

def test_corrupt_archive():
    with temp_dir() as d:
        archive_path1 = pjoin(d, 'foo.tar.gz')
        with open(archive_path1, "w") as f:
            f.write('foo') # definitely not a tar.gz archive
        archive_path2 = pjoin(d, 'foo.tar.bz2')
        with open(archive_path2, "w") as f:
            f.write('foo') # definitely not a tar.gz archive
        with temp_source_cache() as sc:
            with assert_raises(SourceNotFoundError):
                sc.fetch_archive('file:' + archive_path1)
            with assert_raises(SourceNotFoundError):
                sc.fetch_archive('file:' + archive_path2)

def test_mirrors():
    with temp_dir() as sc_dir:
        with temp_dir() as mirror1:
            with temp_dir() as mirror2:
                destdir = pjoin(mirror2, 'packs', 'tar.gz')
                sha = mock_tarball_hash.split(':')[1]
                os.makedirs(destdir)
                shutil.copy(mock_tarball, pjoin(destdir, sha))

                sc = SourceCache(sc_dir, logger, mirrors=['file:' + mirror1, 'file:' + mirror2])
                sc.fetch('http://nonexisting.com', mock_tarball_hash)
                assert [sha] == os.listdir(pjoin(sc_dir, 'packs', 'tar.gz'))

