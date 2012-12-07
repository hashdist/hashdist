import os
import tempfile
import shutil
import subprocess
import contextlib

from .utils import with_temp_dir, working_directory
from ..source_cache import SourceCache

VERBOSE = True

@contextlib.contextmanager
def temp_source_cache():
    tempdir = tempfile.mkdtemp()
    try:
        yield SourceCache(tempdir)
    finally:
        shutil.rmtree(tempdir)    

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

mock_repo = None
mock_commit = None

def make_mock_git_repo():
    with working_directory(mock_repo):
        repo = os.path.join(mock_repo, '.git')
        git('init', repo=repo)
        cat('README', 'First revision',)
        git('add', 'README', repo=repo)
        git('commit', '-m', 'First revision', repo=repo)
        commit = git('rev-list', '-n1', 'HEAD', repo=repo).strip()
        return commit        

def setup():
    global mock_repo, mock_commit
    mock_repo = tempfile.mkdtemp()
    mock_commit = make_mock_git_repo()
        
def teardown():
    global mock_repo
    shutil.rmtree(mock_repo)
    mock_repo = None


def test_basic():
    with temp_source_cache() as sc:
        result = sc.fetch_git(mock_repo, 'master')
        assert result == 'git:%s' % mock_commit

def test_able_to_fetch_twice():
    # With 'master' rev
    with temp_source_cache() as sc:
        result = sc.fetch_git(mock_repo, 'master')
        assert result == 'git:%s' % mock_commit
        result = sc.fetch_git(mock_repo, 'master')
        assert result == 'git:%s' % mock_commit
    # with commit as rev
    with temp_source_cache() as sc:
        result = sc.fetch_git(mock_repo, mock_commit)
        assert result == 'git:%s' % mock_commit
        result = sc.fetch_git(mock_repo, mock_commit)
        assert result == 'git:%s' % mock_commit

