
import os
import re
import sys
import subprocess

pjoin = os.path.join

TAG_RE_S = r'^[a-zA-Z-_+=]+$'
TAG_RE = re.compile(TAG_RE_S)

class SourceNotFoundError(Exception):
    pass

class WrongHashError(Exception):
    pass

class SourceCache(object):
    """
    Directory-based source object database

    Git
    ---

    All git sources are all pulled into one big repo containing
    commits from multiple projects, so that accessing a commit is 

    
    """

    possible_types = ['git', 'tar.gz', 'file', 'dir']
    
    def __init__(self, cache_path):
        if not os.path.isdir(cache_path):
            raise ValueError('"%s" is not an existing directory' % cache_path)
        self.cache_path = cache_path

    @staticmethod
    def create_from_config(config):
        """Creates a SourceCache from the settings in the configuration
        """
        return SourceCache(config.get_path('sourcecache', 'path'))


    def fetch_git(self, repository, rev):
        """Fetches an object to the source cache.
        """
        return GitSourceCache(self.cache_path).fetch_git(repository, rev)
            

class GitSourceCache(object):
    """
    Group together methods for working with the part of the source cache stored
    with git.

    The constructor constructs the repository if necesarry.

    Parameters
    ----------

    cache_path : str
        The root of the source cache (same as given to SourceCache)
    """
    def __init__(self, cache_path):
        self.repo_path = pjoin(cache_path, 'all-git.git')        
        self._git_env = dict(os.environ)
        self._git_env['GIT_DIR'] = self.repo_path
        self._ensure_repo()

    def git_interactive(self, *args):
        # Inherit stdin/stdout in order to interact with user about any passwords
        # required to connect to any servers and so on
        subprocess.check_call(['git'] + list(args), env=self._git_env)

    def git(self, *args):
        p = subprocess.Popen(['git'] + list(args), env=self._git_env,
                             stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()
        return p.returncode, out, err

    def checked_git(self, *args):
        retcode, out, err = self.git(*args)
        # Just fetch the output
        if retcode != 0:
            raise RuntimeError('git call %r failed with code %d' % (args, retcode))
        return out


    def _ensure_repo(self):
        if not os.path.exists(self.repo_path):
            # TODO: This is not race-safe
            os.makedirs(self.repo_path)
            self.checked_git('init', '--bare', '-q', self.repo_path)

    def _resolve_remote_rev(self, repository, rev):
        # Resolve the rev (if it is a branch/tag) to a commit hash
        p = self.checked_git('ls-remote', repository, rev)
        lines = str(p).splitlines()
        if len(lines) == 0:
            if len(rev) != 40:
                raise ValueError('When using a git SHA1 commit hash one needs to use all 40 '
                                 'characters')
                # If not, one could risk getting another commit
                # returned transparently with the current
                # implementation; resolving the hash in only the
                # fetched repo would perhaps work...
            commit = rev
        elif len(lines) == 1:
            # Use the hash for the rev instead
            commit = lines[0].split('\t')[0]
        else:
            raise SourceNotFoundError('"%s" resolves to multiple branches/tags in "%s"' %
                                      (rev, repository))
        return commit

    def _does_branch_exist(self, branch):
        retcode, out, err = self.git('show-ref', '--verify', '--quiet', 'refs/heads/%s' % branch)
        return retcode == 0        

    def fetch_git(self, repository, rev):
        if len(rev) == 40 and self._does_branch_exist('inuse/%s' % rev):
            # If the exact commit is given and it is present we don't want to
            # connect to remote server
            return 'git:%s' % rev
        
        commit = self._resolve_remote_rev(repository, rev)
        # Fetch everything from the repository to us. (We don't pass rev here, but fetch
        # everything, because newer versions of git don't accept commits as revs...)
        self.git_interactive('fetch', repository)
            
        # Assert that the commit is indeed present and is a commit hash and not a revspec
        retcode, out, err = self.git('rev-list', '-n1', '--quiet', commit)
        if retcode != 0:
            raise SourceNotFoundError('Repository "%s" did not contain commit "%s"' %
                                      (repository, commit))

        # Create a branch so that 'git gc' doesn't collect it
        retcode, out, err = self.git('branch', 'inuse/%s' % commit, commit)
        if retcode != 0:
            # race with another fetch? If so we're good.
            # This strategy doesn't cover races with hashdist gc
            if not self._does_branch_exist('inuse/%s' % commit):
                raise RuntimeError('git branch failed with code %d: %s' % (retcode, err))

        return 'git:%s' % commit
