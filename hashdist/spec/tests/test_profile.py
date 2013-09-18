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


def gitify(dir):
    with working_directory(dir):
        subprocess.check_call(['git', 'init'], stdout=open(os.devnull, 'wb'))
        subprocess.check_call(['git', 'add', '.'], stdout=open(os.devnull, 'wb'))
        subprocess.check_call(['git', 'commit', '-m', 'Initial commit'], stdout=open(os.devnull, 'wb'))
        p = subprocess.Popen(['git', 'rev-parse', 'HEAD'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        commit = out.strip()
        assert p.wait() == 0
    return commit

def setup():
    """
    We set up a test setup with three directories, 'user', 'base1' and 'base2'.
    'base2' is made into a git repository which is checked out. 
    
    """
    global tmpdir, source_cache
    tmpdir = tempfile.mkdtemp()
    source_cache = SourceCache(tmpdir, logger)

def teardown():
    shutil.rmtree(tmpdir)


@temp_working_dir_fixture
def test_git_loading(d):
    dump(pjoin(d, 'gitrepo', 'in_parent_dir.yaml'), """\
    """)

    dump(pjoin(d, 'gitrepo', 'subdir', 'in_sub_dir.yaml'), """\
        extends:
          - profile: ../in_parent_dir.yaml
    """)

    commit = gitify(pjoin(d, 'gitrepo'))

    dump(pjoin(d, 'user', 'profile.yaml'), """\
        extends:
          - profile: subdir/in_sub_dir.yaml
            urls: [%s]
            key: git:%s
    """ % (pjoin(d, 'gitrepo'), commit))

    p = profile.load_profile(source_cache, {"profile": pjoin(d, 'user', 'profile.yaml')})
    git_tmp = os.path.dirname(p.parents[0].parents[0].filename)
    assert os.path.exists(git_tmp)
    assert os.path.exists(pjoin(git_tmp, 'subdir', 'in_sub_dir.yaml'))
    assert git_tmp != pjoin(d, 'gitrepo')
    del p
    assert not os.path.exists(git_tmp)

@temp_working_dir_fixture
def test_profile_parameters(d):
    dump(pjoin(d, "profile.yaml"), """\
        extends:
          - profile: base1.yaml
          - profile: base2.yaml
        parameters:
          global:
            a: 1
            b: 2
    """)
    
    dump("base1.yaml", """\
        parameters:
          global:
            a: 0
            c: 3
    """)

    dump("base2.yaml", """\
        parameters:
          global:
            d: 4
    """)
    
    p = profile.load_profile(source_cache, {"profile": "profile.yaml"})
    yield eq_, p.parameters, {'a': 1, 'b': 2, 'c': 3, 'd': 4}

@temp_working_dir_fixture
def test_resource_resolution(d):
    # test packages_dir, base_dir, and sys.path
    dump(pjoin(d, "level3", "profile.yaml"), """\
        extends:
          - profile: %s/level2/profiles/profile.yaml
    """ % d)

    dump(pjoin(d, "level2", "profiles", "profile.yaml"), """\
        extends:
          - profile: %s/level1/profile.yaml
        packages_dir: ../pkgs
        base_dir: ../base
    """ % d)

    dump(pjoin(d, "level1","profile.yaml"), """\
        packages_dir: pkgs
        base_dir: base
    """)

    dump(pjoin(d, "level2", "base", "base.txt"), "2")
    dump(pjoin(d, "level1", "base", "base.txt"), "1")
    dump(pjoin(d, "level1", "base", "base1.txt"), "1")
    dump(pjoin(d, "level2", "pkgs", "foo", "foo.yaml"), "2")
    dump(pjoin(d, "level1", "pkgs", "foo.yaml"), "1")
    dump(pjoin(d, "level1", "pkgs", "bar.yaml"), "1")

    p = profile.load_profile(source_cache, {"profile": pjoin(d, "level3", "profile.yaml")})
    assert pjoin(d, "level2", "pkgs", "foo", "foo.yaml") == p.find_package_file("foo")
    assert pjoin(d, "level1", "pkgs", "bar.yaml") == p.find_package_file("bar")
    os.unlink(pjoin(d, "level2", "pkgs", "foo", "foo.yaml"))
    assert pjoin(d, "level1", "pkgs", "foo.yaml") == p.find_package_file("foo")

    assert pjoin(d, "level2", "base", "base.txt") == p.find_base_file("base.txt")
    assert pjoin(d, "level1", "base", "base1.txt") == p.find_base_file("base1.txt")

    assert [pjoin(d, "level2", "base"), pjoin(d, "level1", "base")] == p.get_python_path()

@temp_working_dir_fixture
def test_packages(d):
    dump(pjoin(d, "user.yaml"), """\
        extends:
          - profile: base1.yaml
          - profile: base2.yaml

        packages:
          - gcc
          - numpy:
              host: false
          - to-be-deleted:
              skip: true

    """)

    dump(pjoin(d, "base1.yaml"), """\
        packages:
          - to-be-deleted # skipped in user/profile.yaml
          - mpi:
              use: openmpi
    """)

    dump(pjoin(d, "base2.yaml"), """\
        packages:
          - numpy:
              host: true # changed in user/profile.yaml
          - python:
              host: true # not changed
    """)


    p = profile.load_profile(source_cache, {"profile": pjoin(d, "user.yaml")})
    pkgs = p.get_packages()
    yield eq_, pkgs, {'python': {'host': True},
                      'numpy': {'host': False},
                      'gcc': {},
                      'mpi': {'use': 'openmpi'}}
