import os
import tempfile
import shutil
import functools
import contextlib

def with_temp_dir(func):
    @functools.wraps(func)
    def wrapper():
        tempdir = tempfile.mkdtemp()
        try:
            func(tempdir)
        finally:
            shutil.rmtree(tempdir)
    return wrapper

@contextlib.contextmanager
def working_directory(path):
    old = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(old)
