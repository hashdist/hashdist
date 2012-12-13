"""
:mod:`hashdist.core.source_cache` --- Source cache
==================================================

The source cache makes sure that one doesn't have to re-download source code
from the net every time one wants to rebuild. For consistency/simplicity, the
software builder also requires that local sources are first "uploaded" to the
cache.

The software cache currently has explicit support for tarballs, git,
and storing single files as-is. A "source item" (tarball, git commit, or file)
is identified by a secure hash. The generic API in :meth:`SourceCache.fetch` and
:meth:`SourceCache.unpack` works by using such hashes as keys. The retrieval
and unpacking methods are determined by the key prefix::

    sc.fetch('http://python.org/ftp/python/2.7.3/Python-2.7.3.tar.bz2',
             'tar.bz2:cmRX4RyxU63D9Ciq8ZAfxWGjdMMOXn2mdCwHQqM4Zjw')
    sc.unpack('tar.bz2:cmRX4RyxU63D9Ciq8ZAfxWGjdMMOXn2mdCwHQqM4Zjw', '/your/location/here')

    sc.fetch('https://github.com/numpy/numpy.git',
             'git:35dc14b0a59cf16be8ebdac04f7269ac455d5e43')

For cases where one don't know the key up front one uses the
key-retrieving API. This is typically done in interactive settings to
aid distribution/package developers::

    key1 = sc.fetch_git('https://github.com/numpy/numpy.git', 'master')
    key2 = sc.fetch_archive('http://python.org/ftp/python/2.7.3/Python-2.7.3.tar.bz2')

Features
--------

 * Native support for multiple retrieval mechanisms. This is important as
   one wants to use tarballs for slowly-changing stable code, but VCS for
   quickly-changing code.

 * Isolates dealing with various source code retrieval mechanisms from
   upper layers, who can simply pass along two strings regardless of method.

 * Aims at lock-free concurrency; it should be safe for multiple users
   to share a source cache directory on a shared file-system as long
   as all have write access.
   
 * Safety: Hashes are re-checked on the fly while unpacking, to protect
   against corruption or tainting of the source cache.

Source keys
-----------

By using secure hashing the keys for a given source item can be determined
a priori. The conventions are as follows:

Tarballs/archives:
    SHA-256, encoded in base64 using :func:`.format_digest`. The prefix
    is currently either ``tar.gz`` or ``tar.bz2``.

Git commits:
    Identified by their (SHA-1) commits prefixed with ``git:``.

Individual files or directories ("hdist-pack"):
    A tarball hash is not deterministic from the file
    contents alone (there's metadata, compression, etc.). In order to
    hash build scripts etc. with hashes based on the contents alone, we
    use a custom "archive format" as the basis of the hash stream.
    The format starts with the 8-byte magic string "HDSTPCK1",
    followed by each file sorted by their filename (potentially
    containing "/"). Each file is stored as

    ==========================  ==============================
    little-endian ``uint32_t``  length of filename
    little-endian ``uint32_t``  length of contents
    ---                         filename (no terminating null)
    ---                         contents
    ==========================  ==============================

    This stream is then encoded like archives (SHA-256 in base-64),
    and prefixed with ``files:`` to get the key.

"""

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
import struct
import errno

from ..deps import sh
from .hasher import Hasher, format_digest, HashingReadStream, HashingWriteStream

pjoin = os.path.join

TAG_RE_S = r'^[a-zA-Z-_+=]+$'
TAG_RE = re.compile(TAG_RE_S)

PACKS_DIRNAME = 'packs'
GIT_DIRNAME = 'all-git.git'

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


def mkdir_if_not_exists(path):
    try:
        os.mkdir(path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

class SourceCache(object):
    """
    """

    def __init__(self, cache_path):
        if not os.path.isdir(cache_path):
            raise ValueError('"%s" is not an existing directory' % cache_path)
        self.cache_path = os.path.realpath(cache_path)

    def _ensure_subdir(self, name):
        path = pjoin(self.cache_path, name)
        mkdir_if_not_exists(path)
        return path

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

    def put(self, files):
        """Put in-memory contents into the source cache.

        Parameters
        ----------
        files : dict or list of (filename, contents)
            The contents of the archive. `filename` may contain forward
            slashes ``/`` as path separators. `contents` is a pure bytes
            objects which will be dumped directly to `stream`.

        Returns
        -------

        The resulting key.

        """
        if isinstance(files, dict):
            files = files.items()
        key = hdist_pack(files)
        pack_filename = pjoin(self._ensure_subdir(PACKS_DIRNAME), key)
        if not os.path.exists(pack_filename):
            with file(pack_filename, 'w') as f:
                hdist_pack(files, f)
        return key

    def _extract_hdist_pack(self, key, target_path):
        pack_filename = pjoin(self._ensure_subdir(PACKS_DIRNAME), key)
        try:
            f = file(pack_filename)
        except IOError, e:
            if e.errno == errno.ENOENT:
                raise SourceNotFoundError(key)
        with f:
            files = hdist_unpack(f, key)
        scatter_files(files, target_path)        

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
            GitSourceCache(self.cache_path).unpack(key, target_path, unsafe_mode)
        elif key.startswith('files:'):
            self._extract_hdist_pack(key, target_path)
        else:
            ArchiveSourceCache(self.cache_path).unpack(key, target_path, unsafe_mode)


class GitSourceCache(object):
    # Group together methods for working with the part of the source
    # cache stored with git.

    def __init__(self, cache_path):
        self.repo_path = pjoin(cache_path, GIT_DIRNAME)
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
    # Group together methods for working with the part of the source
    # cache stored as archives.

    chunk_size = 16 * 1024

    archive_types = {
        'tar.gz' :  (('application/x-tar', 'gzip'), ['tar', 'xz']),
        'tar.bz2' : (('application/x-tar', 'bzip2'), ['tar', 'xj']),
        }

    mime_to_ext = dict((value[0], key) for key, value in archive_types.iteritems())

    def __init__(self, cache_path):
        self.packs_path = pjoin(cache_path, PACKS_DIRNAME)
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


def hdist_pack(files, stream=None):
    """
    Packs the given files in the "hdist-pack" format documented above,
    and returns the resulting key. This is
    useful to hash a set of files solely by their contents, not
    metadata, except the filename.

    Parameters
    ----------

    files : list of (filename, contents)
        The contents of the archive. `filename` may contain forward
        slashes ``/`` as path separators. `contents` is a pure bytes
        objects which will be dumped directly to `stream`.

    stream : file-like (optional)
        Result of the packing, or `None` if one only wishes to know
        the hash.

    Returns
    -------

    The key of the resulting pack
    (e.g., ``files:cmRX4RyxU63D9Ciq8ZAfxWGjdMMOXn2mdCwHQqM4Zjw``).
    """
    tee = HashingWriteStream(hashlib.sha256(), stream)
    tee.write('HDSTPCK1')
    files = sorted(files)
    for filename, contents in files:
        tee.write(struct.pack('<II', len(filename), len(contents)))
        tee.write(filename)
        tee.write(contents)
    return 'files:%s' % format_digest(tee)

def hdist_unpack(stream, key):
    """
    Unpacks the files in the "hdist-pack" format documented above,
    verifies that it matches the given key, and returns the contents
    (in memory).

    Parameters
    ----------

    stream : file-like

        Stream to read the pack from

    key : str

        Result from :func:`hdist_pack`.

    Returns
    -------

    list of (filename, contents)
    """
    if not key.startswith('files:'):
        raise ValueError('invalid key')
    digest = key[len('files:'):]
    tee = HashingReadStream(hashlib.sha256(), stream)
    if tee.read(8) != 'HDSTPCK1':
        raise CorruptSourceCacheError('Not an hdist-pack')
    files = []
    while True:
        buf = tee.read(8)
        if not buf:
            break
        filename_len, contents_len = struct.unpack('<II', buf)
        filename = tee.read(filename_len)
        contents = tee.read(contents_len)
        files.append((filename, contents))
    if digest != format_digest(tee):
        raise CorruptSourceCacheError('hdist-pack does not match key "%s"' % key)
    return files
        
def scatter_files(files, target_dir):
    """
    Given a list of filenames and their contents, write them to the file system

    This is typically used together with :func:`hdist_unpack`.

    Parameters
    ----------

    files : list of (filename, contents)

    target_dir : str
        Filesystem location to emit the files to
    """
    existing_dir_cache = set()
    existing_dir_cache.add(target_dir)
    for filename, contents in files:
        dirname, basename = os.path.split(filename)
        dirname = pjoin(target_dir, dirname)
        if dirname not in existing_dir_cache and not os.path.exists(dirname):
            os.makedirs(dirname)
            existing_dir_cache.add(dirname)
        with file(pjoin(dirname, basename), 'w') as f:
            f.write(contents)

