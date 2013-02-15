from .utils import temp_working_dir

from ..ant_glob import glob_files

import os
from os.path import join as pjoin
from os import makedirs

def makefiles(lst):
    for x in lst:
        x = x.strip()
        dirname, basename = os.path.split(x)
        if dirname != '' and not os.path.exists(dirname):
            os.makedirs(dirname)
        with file(x, 'w') as f:
            pass

def test_basic():
    with temp_working_dir() as d:
        makefiles('a0/b0/c0/d0.txt a0/b0/c0/d1.txt a0/b1/c1/d0.txt a0/b.txt a0/b.txt2'.split())
        #os.system('find')
        #print '===='

        def check(expected, pattern):
            # check relative
            assert sorted(expected) == sorted(glob_files(pattern))
            # check absolute
            abs_expected = [os.path.realpath(e) for e in expected]
            with temp_working_dir() as not_d:
                assert sorted(abs_expected) == sorted(glob_files(pattern, d))
                # check with absolute glob
                assert sorted(abs_expected) == sorted(glob_files(pjoin(d, pattern), not_d))
        
        yield (check, ['a0/b0/c0/d0.txt'],
               'a0/b0/c0/d0.txt')
        yield (check, ['a0/b1/c1/d0.txt', 'a0/b0/c0/d0.txt'],
              'a0/**/d0.txt')
        yield (check, ['a0/b.txt', 'a0/b1/c1/d0.txt', 'a0/b0/c0/d0.txt', 'a0/b0/c0/d1.txt'],
              'a0/**/*.txt')
        yield (check, ['a0/b0/c0/d0.txt', 'a0/b0/c0/d1.txt'],
              '**/b0/**/*.txt')
