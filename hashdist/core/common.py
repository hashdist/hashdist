import os
import contextlib

class InvalidBuildSpecError(ValueError):
    pass


class BuildFailedError(Exception):
    def __init__(self, msg, build_dir):
        Exception.__init__(self, msg)
        self.build_dir = build_dir

json_formatting_options = dict(indent=2, separators=(', ', ' : '),
                               sort_keys=True, allow_nan=False)

SHORT_ARTIFACT_ID_LEN = 4

@contextlib.contextmanager
def working_directory(path):
    old = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(old)
