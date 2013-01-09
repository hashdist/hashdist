import os
import errno
import shutil

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
    while path != parent:
        path, child = os.path.split(path)
        if path == parent:
            break
        try:
            os.rmdir(path)
        except OSError, e:
            if e.errno != errno.ENOTEMPTY:
                raise
            break

