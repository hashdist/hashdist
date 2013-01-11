import os
from os.path import join as pjoin
from textwrap import dedent
from .. import config

from .utils import temp_dir, working_directory


def test_ini():
    contents = dedent(
        '''\
        [global]
        cache = subdir
        db = ~/subdir
        bogus = foo

        [bogus]
        bar = foo

        [builder]
        artifact-dir-pattern = ~/str
        ''')
    
    with temp_dir() as d:
        ini_filename = pjoin(d, 'foo.ini')
        with file(ini_filename, 'w') as f:
            f.write(contents)

        # When reading from file, interpret relative to file location
        with working_directory('/'):
            cfg = config.load_configuration_from_inifile(ini_filename)
            assert cfg['global/cache'] == pjoin(d, 'subdir')
            assert cfg['global/db'] == os.path.expanduser('~/subdir')
            assert cfg['builder/artifact-dir-pattern'] == '~/str'

