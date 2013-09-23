import os
import errno
import shutil
import gzip
from contextlib import closing

def silent_copy(src, dst):
    try:
        shutil.copy(src, dst)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

def silent_relative_symlink(src, dst):
    dstdir = os.path.dirname(dst)
    rel_src = os.path.relpath(src, dstdir)
    try:
        os.symlink(rel_src, dst)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

def silent_absolute_symlink(src, dst):
    try:
        os.symlink(os.path.abspath(src), dst)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

def silent_makedirs(path):
    """like os.makedirs, but does not raise error in the event that the directory already exists"""
    try:
        os.makedirs(path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

def silent_unlink(path):
    """like os.unlink but does not raise error if the file does not exist"""
    try:
        os.unlink(path)
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise

def rmtree_up_to(path, parent, silent=False):
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
        raise valueError('must have part.startswith(parent)')
    while path != parent:
        if path == parent:
            break
        try:
            os.rmdir(path)
        except OSError, e:
            if e.errno != errno.ENOTEMPTY:
                raise
            break
        path, child = os.path.split(path)

def gzip_compress(source_filename, dest_filename):
    chunk_size = 16 * 1024
    with file(source_filename, 'rb') as src:
        with closing(gzip.open(dest_filename, 'wb')) as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk: break
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
        except OSError, e:
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

def write_protect(filename):
    if not os.path.islink(filename):
        mode = os.stat(filename).st_mode
        os.chmod(filename, mode & ~0o222)

def touch(filename, readonly=False):
    with open(filename, 'w') as f:
        pass
    if readonly:
        write_protect(filename)

