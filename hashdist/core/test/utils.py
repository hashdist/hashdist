import os
import tempfile
import shutil
import functools
import contextlib
import subprocess
import hashlib

from nose.tools import eq_

from ...hdist_logging import Logger, null_logger, DEBUG, INFO, WARNING, ERROR, CRITICAL

from os.path import join as pjoin

@contextlib.contextmanager
def temp_dir():
    tempdir = tempfile.mkdtemp()
    try:
        yield tempdir
    finally:
        shutil.rmtree(tempdir)

@contextlib.contextmanager
def temp_working_dir():
    tempdir = tempfile.mkdtemp()
    try:
        with working_directory(tempdir):
            yield tempdir
    finally:
        shutil.rmtree(tempdir)

@contextlib.contextmanager
def working_directory(path):
    old = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(old)

def eqsorted_(a, b):
    eq_(sorted(a), sorted(b))
#
# Logger to use during unit-testing
#

VERBOSE = bool(int(os.environ.get('VERBOSE', '0')))

if VERBOSE:
    logger = Logger(DEBUG, 'tests')
else:
    logger = null_logger

def get_level_name(level):
    if level >= CRITICAL:
        return 'CRITICAL'
    elif level >= ERROR:
        return 'ERROR'
    elif level >= WARNING:
        return 'WARNING'
    elif level >= INFO:
        return 'INFO'
    else:
        return 'DEBUG'

class MemoryLogger(Logger):
    def __init__(self):
        self.lines = []
    
    def get_sub_logger(self):
        pass
    
    def log(self, level, msg, *args):
        if args:
            msg = msg % args
        msg = "%s:%s" % (get_level_name(level), msg)
        self.lines.append(msg)


#
# Mock archives
#
def make_temporary_tarball(files):
    """Make a tarball in a temporary directory under /tmp; returns
    (name of directory, name of archive, source cache key)
    """
    from ..source_cache import scatter_files
    from ..hasher import format_digest
    
    container_dir = tempfile.mkdtemp()
    archive_filename = pjoin(container_dir, 'archive.tar.gz')

    tmp_d = tempfile.mkdtemp()
    try:
        scatter_files(files, tmp_d)
        subprocess.check_call(['tar', 'czf', archive_filename] + os.listdir(tmp_d), cwd=tmp_d)
    finally:
        shutil.rmtree(tmp_d)
    # get key
    with file(archive_filename) as f:
        key = 'tar.gz:' + format_digest(hashlib.sha256(f.read()))
    return container_dir, archive_filename, key
