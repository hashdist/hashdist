import os
import sys
import tempfile
import shutil
import functools
import contextlib
import subprocess
import hashlib
import inspect
from textwrap import dedent
from contextlib import closing

from nose.tools import eq_

from ..fileutils import silent_makedirs

import logging
from hashdist.util.logger_setup import configure_logging

from os.path import join as pjoin

def which(filename):
    """Checks PATH for the location of filename"""

    locations = os.environ.get("PATH").split(os.pathsep)
    for location in locations:
        candidate = os.path.join(location, filename)
        if os.path.isfile(candidate):
            return candidate
    raise OSError('Unable to find system %s' % filename,)


def make_abs_temp_dir():
    """Create a temporary directory and get its absolute path"""
    return os.path.realpath(tempfile.mkdtemp())


# Make our own assert_raises, as nose.tools doesn't have it on Python 2.6
# We always use the context manager form
class AssertRaisesResult(object):
    pass

@contextlib.contextmanager
def assert_raises(wanted_exc_type):
    r = AssertRaisesResult()
    try:
        yield r
    except:
        exc_type, exc_val, exc_tb = sys.exc_info()
        if not issubclass(exc_type, wanted_exc_type):
            assert False, 'Wanted exception %r but got %r' % (
                wanted_exc_type, exc_type)
        r.exc_type = exc_type
        r.exc_val = exc_val
        r.exc_tb = exc_tb
    else:
        assert False, 'Expected exception not raised'


@contextlib.contextmanager
def temp_dir():
    tempdir = make_abs_temp_dir()
    try:
        yield tempdir
    finally:
        shutil.rmtree(tempdir)

@contextlib.contextmanager
def temp_working_dir():
    tempdir = make_abs_temp_dir()
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

def dump(filename, contents):
    d = os.path.dirname(filename)
    if d:
        silent_makedirs(d)
    with open(filename, 'w') as f:
        f.write(dedent(contents))

def temp_working_dir_fixture(func):
    if inspect.isgeneratorfunction(func):
        @functools.wraps(func)
        def replacement():
            with temp_working_dir() as d:
                for x in func(d): yield x
    else:
        @functools.wraps(func)
        def replacement():
            with temp_working_dir() as d:
                return func(d)
    return replacement


def ctxmgr_to_fixture(ctxmgr_func):
    def decorator(func):
        if inspect.isgeneratorfunction(func):
            @functools.wraps(func)
            def replacement(*args, **kw):
                with ctxmgr_func() as ctx:
                    for x in func(ctx, *args, **kw): yield x
        else:
            @functools.wraps(func)
            def replacement(*args, **kw):
                with ctxmgr_func as ctx:
                    return func(ctx, *args, **kw)
        return replacement
    return decorator



VERBOSE = bool(int(os.environ.get('VERBOSE', '0')))
if VERBOSE:
    configure_logging('DEBUG')
    logger = logging.getLogger()
else:
    configure_logging('WARNING')
    logger = logging.getLogger('null_logger')

#
# Mock archives
#
def make_temporary_tarball(files):
    """Make a tarball in a temporary directory under /tmp; returns
    (name of directory, name of archive, source cache key)
    """
    import tarfile
    from ..source_cache import scatter_files
    from ..hasher import format_digest

    container_dir = make_abs_temp_dir()
    archive_filename = pjoin(container_dir, 'archive.tar.gz')

    tmp_d = make_abs_temp_dir()
    try:
        scatter_files(files, tmp_d)
        with closing(tarfile.open(archive_filename, 'w:gz')) as archive:
            with working_directory(tmp_d):
                for dirpath, dirnames, filenames in os.walk('.'):
                    archive.add(dirpath)
                    for fname in filenames:
                        archive.add(pjoin(dirpath, fname))
    finally:
        shutil.rmtree(tmp_d)
    with file(archive_filename) as f:
        key = 'tar.gz:' + format_digest(hashlib.sha256(f.read()))
    return container_dir, archive_filename, key
