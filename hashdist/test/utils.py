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
