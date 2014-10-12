import os
import errno
import filecmp
import shutil
import time
import gzip
from os.path import join as pjoin
from contextlib import closing, contextmanager


@contextmanager
def allow_writes(path):
    modified = False
    if not os.path.islink(path):
        old_mode = os.stat(path).st_mode
        os.chmod(path, old_mode | 0o222)
        modified = True
    yield
    if modified:
        os.chmod(path, old_mode)


def silent_copy(src, dst):
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy(src, dst)
    except OSError:
        if not filecmp.cmp(src, dst):
            raise


def silent_relative_symlink(src, dst):
    try:
        dstdir = os.path.dirname(dst)
        rel_src = os.path.relpath(src, dstdir)
        os.symlink(rel_src, dst)
    except OSError:
        if not os.path.exists(dst):
            raise


def silent_absolute_symlink(src, dst):
    try:
        os.symlink(os.path.abspath(src), dst)
    except OSError:
        if not os.path.exists(dst):
            raise


def silent_makedirs(path):
    """like os.makedirs, but does not raise error in the event that the directory already exists"""
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise

def silent_unlink(path):
    """like os.unlink but does not raise error if the file does not exist"""
    try:
        os.unlink(path)
    except OSError:
        if os.path.exists(path):
            raise


def robust_rmtree(path, logger=None, max_retries=6):
    """Robustly tries to delete paths.

    Retries several times (with increasing delays) if an OSError
    occurs.  If the final attempt fails, the Exception is propagated
    to the caller.
    """
    dt = 1
    for i in range(max_retries):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            if logger:
                logger.info('Unable to remove path: %s' % path)
                logger.info('Retrying after %d seconds' % dt)
            time.sleep(dt)
            dt *= 2

    # Final attempt, pass any Exceptions up to caller.
    shutil.rmtree(path)


def rmtree_up_to(path, parent):
    """Executes ``shutil.rmtree(path, ignore_errors=True)``,
    and then removes any empty parent directories
    up until (and excluding) parent.
    """
    path = os.path.realpath(path)
    parent = os.path.realpath(parent)
    if path == parent:
        return
    if not path.startswith(parent):
        raise ValueError('must have path.startswith(parent)')
    shutil.rmtree(path, ignore_errors=True)
    path, child = os.path.split(path)
    rmdir_empty_up_to(path, parent)


def rmdir_empty_up_to(path, parent):
    """Removes the directory `path` and any empty parent directories
    up until and excluding parent.
    """
    if not os.path.isabs(path):
        raise ValueError('only absolute paths supported')
    if not path.startswith(parent):
        raise ValueError('must have part.startswith(parent)')
    while path != parent:
        if path == parent:
            break
        try:
            os.rmdir(path)
        except OSError as e:
            if e.errno != errno.ENOTEMPTY:
                raise
            break
        path, child = os.path.split(path)


def gzip_compress(source_filename, dest_filename):
    chunk_size = 16 * 1024
    with open(source_filename, 'rb') as src:
        with closing(gzip.open(dest_filename, 'wb')) as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                dst.write(chunk)


def atomic_symlink(source, dest):
    """Overwrites a destination symlink atomically without raising error
    if target exists (by first creating link to `source`, then renaming it to `dest`)
    """
    # create-&-rename in order to force-create symlink
    i = 0
    while True:
        try:
            templink = dest + '-%d' % i
            os.symlink(source, templink)
        except OSError as e:
            if e.errno == errno.EEXIST:
                i += 1
            else:
                raise
        else:
            break
    try:
        os.rename(templink, dest)
    except:
        os.unlink(templink)
        raise


def write_protect(path):
    if not os.path.islink(path):
        mode = os.stat(path).st_mode
        os.chmod(path, mode & ~0o222)


def write_allow(path):
    if not os.path.islink(path):
        mode = os.stat(path).st_mode
        os.chmod(path, mode | 0o222)


def rmtree_write_protected(rootpath):
    """
    Like shutil.rmtree, but removes files/directories that are write-protected.
    """
    for dirpath, dirnames, filenames in os.walk(rootpath, followlinks=False, topdown=False):
        os.chmod(dirpath, 0o777)
        for fname in filenames:
            qname = pjoin(dirpath, fname)
            if not os.path.islink(qname):
                os.chmod(qname, 0o777)
            os.unlink(qname)
        for fname in dirnames:
            qname = pjoin(dirpath, fname)
            if os.path.islink(qname):
                os.unlink(qname)
            else:
                os.chmod(qname, 0o777)
                os.rmdir(qname)
    os.rmdir(rootpath)


def touch(filename, readonly=False):
    open(filename, 'wa').close()
    if readonly:
        write_protect(filename)


def realpath_to_symlink(filename):
    """Acts like ``os.path.realpath`` on the parent directory of the given file

    The reason to use this is that realpath would follow a symlink. This
    function just follows symlinks in parent directories, but not the link
    we are pointing to.
    """
    parent_dir, basename = os.path.split(filename)
    result = pjoin(os.path.realpath(parent_dir), basename)
    return result
