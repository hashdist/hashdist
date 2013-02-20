import os
from os.path import join as pjoin

from .utils import temp_dir, assert_raises
from .. import fileutils

def test_rmtree_up_to():
    with temp_dir() as d:
        # Incomplete removal
        os.makedirs(pjoin(d, 'a', 'x', 'A', '2'))
        os.makedirs(pjoin(d, 'a', 'x', 'B', '2'))
        fileutils.rmtree_up_to(pjoin(d, 'a', 'x', 'A', '2'), d)
        assert ['B'] == os.listdir(pjoin(d, 'a', 'x'))

        # Invalid parent parameter
        with assert_raises(ValueError):
            fileutils.rmtree_up_to(pjoin(d, 'a', 'x', 'B'), '/nonexisting')

        # Complete removal -- do not actually remove the parent
        fileutils.rmtree_up_to(pjoin(d, 'a', 'x', 'B', '2'), d)
        assert os.path.exists(d)

        # Parent is exclusive
        fileutils.rmtree_up_to(d, d)
        assert os.path.exists(d)
