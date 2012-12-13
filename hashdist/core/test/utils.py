import os
import tempfile
import shutil
import functools
import contextlib

@contextlib.contextmanager
def temp_dir():
    tempdir = tempfile.mkdtemp()
    try:
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

#
# Logger to use during unit-testing
#
class NullLogger(object):
    def _noop(self, *args, **kw):
        pass
    warning = error = debug = info = _noop

VERBOSE = bool(int(os.environ.get('VERBOSE', '0')))

if VERBOSE:
    import logging
    logging.basicConfig(format='log: %(message)s')
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
else:
    logger = NullLogger()
