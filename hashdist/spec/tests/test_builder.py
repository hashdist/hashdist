from pprint import pprint
import os
import shutil
import tempfile
import subprocess
from os.path import join as pjoin
from nose.tools import eq_, ok_

from ...core import SourceCache
from ...core.test.utils import *
from ...core.test.test_source_cache import temp_source_cache
from .. import profile
from .. import builder


@temp_working_dir_fixture
def test_ready(d):
    dump(pjoin(d, 'profile.yaml'), """\
        packages_dir: pkgs
        packages: [a, b, c, d]
    """)

    dump(pjoin(d, 'pkgs', 'a.yaml'), "dependencies: {build: [b, c]}")
    dump(pjoin(d, 'pkgs', 'b.yaml'), "dependencies: {build: [d]}")
    dump(pjoin(d, 'pkgs', 'c.yaml'), "dependencies: {build: [d]}")
    dump(pjoin(d, 'pkgs', 'd.yaml'), "")
    
    p = profile.load_profile(None, {"profile": pjoin(d, "profile.yaml")})
    pb = builder.ProfileBuildState(p)
    assert ['d'] == pb.get_ready_list()
    pb.built_packages.add('d')
    assert ['b', 'c'] == sorted(pb.get_ready_list())
    pb.built_packages.add('b')
    pb.built_packages.add('c')
    assert ['a'] == pb.get_ready_list()
