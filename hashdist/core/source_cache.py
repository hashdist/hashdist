import os
import re
import sys
import subprocess
import mimetypes
import tempfile
import urllib2
import json
import shutil
import hashlib

from ..deps import sh
from .hasher import Hasher, format_digest

pjoin = os.path.join

TAG_RE_S = r'^[a-zA-Z-_+=]+$'
TAG_RE = re.compile(TAG_RE_S)

class SourceNotFoundError(Exception):
    pass

class KeyNotFoundError(Exception):
    pass

class CorruptSourceCacheError(Exception):
    pass

def single_file_key(filename, contents):
    h = Hasher()
    h.update('file')
    h.update({'filename': filename,
              'contents': contents})
    return 'file:' + h.format_digest()

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
        self.cache_path = os.path.realpath(cache_path)

    def delete_all(self):
        shutil.rmtree(self.cache_path)
        os.mkdir(self.cache_path)

    @staticmethod
    def create_from_config(config, logger):
        """Creates a SourceCache from the settings in the configuration
        """
        return SourceCache(config.get_path('sourcecache', 'path'))

    def fetch_git(self, repository, rev):
        return GitSourceCache(self.cache_path).fetch_git(repository, rev)

    def fetch_archive(self, url, hash=None, type=None):
        return ArchiveSourceCache(self.cache_path).fetch_archive(url, hash, type)

    def put(self, filename, contents):
        """Utility method to put a single file with the given filename and contents.

        The resulting key is independent of the source store and can be retrieved
        from the function :func:`single_file_key`.
        """
        key = single_file_key(filename, contents)
        # Implementation is that create a temporary tar.gz and archive it
        tgz_d = tempfile.mkdtemp()
        stage_d = tempfile.mkdtemp()
        try:
            archive_filename = pjoin(tgz_d, 'put.tar.gz')
            with file(pjoin(stage_d, filename), 'w') as f:
                f.write(contents)
            subprocess.check_call(['tar', 'czf', archive_filename, filename], cwd=stage_d)
            
            ArchiveSourceCache(self.cache_path).fetch_archive('file:' + archive_filename,
                                                              type='tar.gz',
                                                              _force_key_as=key)
        finally:
            shutil.rmtree(tgz_d)
            shutil.rmtree(stage_d)
        return key

    def unpack(self, key, target_path, unsafe_mode=False):
        """
        Unpacks the sources identified by `key` to `target_path`

        The sources are verified against their secure hash to guard
        against corruption/security problems. `CorruptSourceCacheError`
        will be raised in this case. In normal circumstances this should
        never happen.

        Parameters
        ----------

        key : str
            The source item key/secure hash

        target_path : str
            Path to extract in

        unsafe_mode : bool (default: True)
            Whether a faster, memory-conserving mode should be used.
            It is safe to use `unsafe_mode` if `target_path` is
            a fresh directory which is removed in the event of a
            `CorruptSourceCacheError`. See "Security concerns" below.

        Returns
        -------

        `None`

        Unsafe mode details
        -------------------

        By default, the archive will be loaded into memory and
        checked, and if found corrupt nothing will be extracted. By
        setting `unsafe_mode`, extraction takes place on the fly while
        validating, which is faster and use less memory, but it means
        that a corrupt archive may be partially or fully extracted
        (though an exception is raised at the end). No removal of the
        extracted contents is attempted in this case.
        """
        if not os.path.exists(target_path):
            os.makedirs(target_path)
        if key.startswith('git:'):
            handler = GitSourceCache(self.cache_path)
        else:
            handler = ArchiveSourceCache(self.cache_path)
        handler.unpack(key, target_path, unsafe_mode)

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

    def unpack(self, key, target_path, unsafe_mode):
        assert key.startswith('git:')
        commit = key[4:]
        archive_p = sh.git('archive', '--format=tar', commit, _env=self._git_env, _piped=True)
        unpack_p = sh.tar(archive_p, 'x', _cwd=target_path)
        unpack_p.wait()


SIMPLE_FILE_URL_RE = re.compile(r'^file:/?[^/]+.*$')

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
        'tar.gz' :  (('application/x-tar', 'gzip'), ['tar', 'xz']),
        'tar.bz2' : (('application/x-tar', 'bzip2'), ['tar', 'xj']),
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
        # It's annoying to see curl for local files, so provide a special-case
        if SIMPLE_FILE_URL_RE.match(url):
            stream = file(url[len('file:'):])
        else:
            # Make request
            sys.stderr.write('Downloading %s...\n' % url)
            curl = subprocess.Popen(['curl', url], stdout=subprocess.PIPE,
                                    stdin=subprocess.PIPE)
            curl.stdin.close()
            stream = curl.stdout
        
        # Download file to a temporary file within self.packs_path, while hashing
        # it.
        hasher = hashlib.sha256()
        temp_fd, temp_path = tempfile.mkstemp(prefix='downloading-', dir=self.packs_path)
        try:
            f = os.fdopen(temp_fd, 'wb')
            try:
                while True:
                    chunk = stream.read(self.chunk_size)
                    if not chunk: break
                    hasher.update(chunk)
                    f.write(chunk)
            finally:
                stream.close()
                f.close()            
        except:
            # Remove temporary file if there was a failure
            os.unlink(temp_path)
            raise
        return temp_path, format_digest(hasher)

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

    def _write_archive_info(self, hash, type, url):
        info = {'type' : type, 'retrieved_from' : url}
        with file(pjoin(self.meta_path, '%s.info' % hash), 'w') as f:
            json.dump(info, f)

    def _read_archive_info(self, hash):
        """Returns information about the archive stored under the given digest-key;
        or None if it is not found.
        """
        try:
            f = file(pjoin(self.meta_path, '%s.info' % hash))
        except IOError:
            return None
        with f:
            r = json.load(f)
        return r

    def contains(self, hash):
        return os.path.exists(pjoin(self.meta_path, '%s.info' % hash))

    def fetch_archive(self, url, expected_hash=None, type=None, _force_key_as=None):
        """
        Parameters
        ----------
        
        _force_key_as : str
            Use this key instead of the one computed from hashing the archive.
        """
        if expected_hash is not None and self.contains(expected_hash):
            # found, so noop
            return expected_hash
        else:
            type = self._ensure_type(url, type)
            temp_file, hash = self._download_and_hash(url)
            if _force_key_as is not None:
                hash = _force_key_as
            try:
                if expected_hash is not None and expected_hash != hash:
                    raise RuntimeError('File downloaded from "%s" has hash %s but expected %s' %
                                       (url, hash, expected_hash))
                # We simply emit the info file without any checks,
                # in the case of a race it shouldn't matter to overwrite it
                self._write_archive_info(hash, type, url) 
                # Simply rename to the target; again a race shouldn't matter
                # with, in this case, identical content
                target_file = pjoin(self.packs_path, hash)
                os.rename(temp_file, target_file)
            finally:
                try:
                    os.unlink(temp_file)
                except:
                    pass
            return hash

    def unpack(self, key, target_path, unsafe_mode):
        info = self._read_archive_info(key)
        if info is None:
            raise KeyNotFoundError("Key '%s' not found in source cache" % key)
        type = info['type']
        archive_path = pjoin(self.packs_path, key)
        cmd = self.archive_types[type][1]
        if unsafe_mode:
            retcode = self._unpack_unsafe(key, target_path, archive_path, cmd)
        else:
            retcode = self._unpack_safe(key, target_path, archive_path, cmd)
        if retcode != 0:
            raise subprocess.CalledProcessError(retcode, cmd[0])

    def _key_check(self, archive_path, hasher, key):
        if format_digest(hasher) != key and not key.startswith('file:'):
            raise CorruptSourceCacheError("Corrupted file: '%s'" % archive_path)

    def _unpack_unsafe(self, key, target_path, archive_path, cmd):
        p  = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=target_path)
        hasher = hashlib.sha256()
        with file(archive_path) as archive_file:
            while True:
                chunk = archive_file.read(self.chunk_size)
                if not chunk: break
                hasher.update(chunk)
                p.stdin.write(chunk)
        p.stdin.close()
        retcode = p.wait()
        self._key_check(archive_path, hasher, key)
        return retcode

    def _unpack_safe(self, key, target_path, archive_path, cmd):
        with file(archive_path) as archive_file:
            archive_data = archive_file.read()
        hasher = hashlib.sha256(archive_data)
        self._key_check(archive_path, hasher, key)
        p  = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=target_path)
        p.stdin.write(archive_data)
        p.stdin.close()
        return p.wait()

supported_source_archive_types = sorted(ArchiveSourceCache.archive_types.keys())
