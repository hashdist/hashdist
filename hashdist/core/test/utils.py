import os
import tempfile
import shutil
import functools
import contextlib
import subprocess
import hashlib

from nose.tools import eq_

from ...hdist_logging import Logger, null_logger, DEBUG
from logging import getLevelName

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

def cat(filename):
    with open(filename) as f:
        return f.read()

def temp_working_dir_fixture(func):
    @functools.wraps(func)
    def replacement():
        with temp_working_dir() as d:
            func(d)
    return replacement

#
# Logger to use during unit-testing
#

VERBOSE = bool(int(os.environ.get('VERBOSE', '0')))

if VERBOSE:
    logger = Logger(DEBUG, 'tests')
else:
    logger = null_logger

class MemoryLogger(Logger):
    def __init__(self, names=[], lines=None):
        if lines is None:
            lines = []
        self.lines = lines
        self.level = DEBUG
        self.names = names
    
    def get_sub_logger(self, name):
        return MemoryLogger(self.names + [name], self.lines)
    
    def log(self, level, msg, *args):
        if args:
            msg = msg % args
        if self.names:
            msg = '%s:%s' % ('/'.join(self.names), msg)
        msg = "%s:%s" % (getLevelName(level), msg)
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
