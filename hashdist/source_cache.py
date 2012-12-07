import os
import re
import sys
import subprocess
import mimetypes
import tempfile
import urllib2
import json

from .deps import sh
from .hash import create_hasher, encode_digest

pjoin = os.path.join

TAG_RE_S = r'^[a-zA-Z-_+=]+$'
TAG_RE = re.compile(TAG_RE_S)

class SourceNotFoundError(Exception):
    pass

class KeyNotFoundError(Exception):
    pass

class SourceCache(object):
    """
    Directory-based source object database

    Git
    ---

    All git sources are all pulled into one big repo containing
    commits from multiple projects, so that accessing a commit is 

    
    """

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
        return GitSourceCache(self.cache_path).fetch_git(repository, rev)

    def fetch_archive(self, url, type=None):
        return ArchiveSourceCache(self.cache_path).fetch_archive(url)

    def unpack(self, key, target_path):
        if os.path.exists(target_path):
            raise RuntimeError("Dir/file '%s' already exists" % target_path)
        os.makedirs(target_path)
        if key.startswith('git:'):
            handler = GitSourceCache(self.cache_path)
        else:
            handler = ArchiveSourceCache(self.cache_path)
        handler.unpack(key, target_path)

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

    def unpack(self, key, target_path):
        assert key.startswith('git:')
        commit = key[4:]
        archive_p = sh.git('archive', '--format=tar', commit, _env=self._git_env, _piped=True)
        unpack_p = sh.tar(archive_p, 'x', _cwd=target_path)
        unpack_p.wait()


class ArchiveSourceCache(object):
    """
    Group together methods for working with the part of the source cache stored
    as archives.

    The constructor constructs the repository if necesarry.

    Parameters
    ----------

    cache_path : str
        The root of the source cache (same as given to SourceCache)
    """

    chunk_size = 16 * 1024

    archive_types = {
        'tar.gz' :  (('application/x-tar', 'gzip'), ['tar', 'xzf']),
        'tar.bz2' : (('application/x-tar', 'bzip2'), ['tar', 'xjf']),
        'zip' : (('application/zip', None), ['unzip'])
        }

    mime_to_ext = dict((value[0], key) for key, value in archive_types.iteritems())

    def __init__(self, cache_path):
        self.packs_path = pjoin(cache_path, 'packs')
        self.meta_path = pjoin(cache_path, 'meta')
        if not os.path.exists(self.packs_path):
            # TODO not race safe
            os.makedirs(self.packs_path)
        if not os.path.exists(self.meta_path):
            # TODO not race safe
            os.makedirs(self.meta_path)

    def _download_and_hash(self, url):
        """Downloads file at url to a temporary location and hashes it

        Returns
        -------

        temp_file, digest
        """
        # Make request
        req = urllib2.urlopen(url)
        
        # Download file to a temporary file within self.packs_path, while hashing
        # it
        hasher = create_hasher()
        temp_fd, temp_path = tempfile.mkstemp(prefix='downloading-', dir=self.packs_path)
        try:
            f = os.fdopen(temp_fd, 'wb')
            try:
                while True:
                    chunk = req.read(self.chunk_size)
                    if not chunk: break
                    hasher.update(chunk)
                    f.write(chunk)
            finally:
                f.close()            
        except:
            # Remove temporary file if there was a failure
            os.unlink(temp_path)
            raise
        return temp_path, encode_digest(hasher)

    def _ensure_type(self, url, type):
        if type is not None:
            if type not in self.archive_types:
                raise ValueError('Unknown archive type: %s' % type)
        else:
            mime = mimetypes.guess_type(url)
            if mime not in self.mime_to_ext:
                raise ValueError('Unable to guess archive type of "%s"' % url)
            type = self.mime_to_ext[mime]
        return type

    def _write_archive_info(self, digest, type, url):
        info = {'type' : type, 'retrieved_from' : url}
        with file(pjoin(self.meta_path, '%s.info' % digest), 'w') as f:
            json.dump(info, f)

    def _read_archive_info(self, digest):
        """Returns information about the archive stored under the given digest-key;
        or None if it is not found.
        """
        try:
            f = file(pjoin(self.meta_path, '%s.info' % digest))
        except IOError:
            return None
        with f:
            r = json.load(f)
        return r

    def fetch_archive(self, url, type=None):
        type = self._ensure_type(url, type)
        temp_file, digest = self._download_and_hash(url)
        # Simply rename to the target; in the event of a race it is
        # ok to overwrite any existing files since content is the same
        target_file = pjoin(self.packs_path, digest)
        os.rename(temp_file, target_file)
        # Similarly we simply emit the info file without any checks,
        # in the case of a race it shouldn't matter
        self._write_archive_info(digest, type, url)
        return digest

    def unpack(self, digest, target_path):
        info = self._read_archive_info(digest)
        if info is None:
            raise KeyNotFoundError("Key '%s' not found in source cache" % digest)
        type = info['type']
        archive_path = pjoin(self.packs_path, digest)
        cmd = self.archive_types[type][1] + [archive_path]
        subprocess.check_call(cmd, cwd=target_path)

