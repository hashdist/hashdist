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


def setup():
    global tmpdir, base1, base2, user, source_cache
    tmpdir = tempfile.mkdtemp()
    base1 = pjoin(tmpdir, 'base1')
    base2 = pjoin(tmpdir, 'base2')
    user = pjoin(tmpdir, 'user')

    # foo.txt from base1 overridden
    dump(pjoin(user, "foo.txt"), "foo.txt in user")
    dump(pjoin(base1, "foo.txt"), "foo.txt in base1")
    # separate files
    dump(pjoin(user, "user.txt"), "in user")
    dump(pjoin(base1, "base1.txt"), "in base1")
    dump(pjoin(base2, "base2.txt"), "in base2")
    # conflicting files, raise error
    dump(pjoin(base1, "conflicting.txt"), "in base1")
    dump(pjoin(base2, "conflicting.txt"), "in base2")

    # base2 is stored in a git repo
    dump(pjoin(base2, "profiles", "linux.yaml"), """\
        parameters:
          global:
            d: 4
        packages:
          - numpy/host # changed to numpy/latest in user/profile.yaml
          - python/host # not changed
    """)
    with working_directory(base2):
        subprocess.check_call(['git', 'init'], stdout=open(os.devnull, 'wb'))
        subprocess.check_call(['git', 'add', 'profiles/linux.yaml', 'base2.txt', 'conflicting.txt'],
                              stdout=open(os.devnull, 'wb'))
        subprocess.check_call(['git', 'commit', '-m', 'Initial commit'], stdout=open(os.devnull, 'wb'))
        p = subprocess.Popen(['git', 'rev-parse', 'HEAD'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        commit = out.strip()
        assert p.wait() == 0
    

    dump(pjoin(user, "profile.yaml"), """\
        extends:
          - profile: profiles/linux.yaml
            dir: %(base1)s
          - profile: profiles/linux.yaml
            urls: [%(base2)s]
            key: git:%(commit)s

        parameters:
          global:
            a: 1
            b: 2

        packages:
          - gcc/host
          - numpy
          - to-be-deleted/skip
    """ % dict(base1=base1, base2=base2, commit=commit))

    dump(pjoin(base1, "profiles", "linux.yaml"), """\
        parameters:
          global:
            a: 0
            c: 3
        packages:
          - to-be-deleted # skipped in user/profile.yaml
          - mpi: openmpi/1.4.3
    """)


    os.mkdir(pjoin(tmpdir, 'src'))
    source_cache = SourceCache(pjoin(tmpdir, 'src'), logger)

def teardown():
    shutil.rmtree(tmpdir)


def test_git_loading():
    with profile.load_profile(source_cache, {"dir": user, "profile": "profile.yaml"}) as p:
        git_temp_unpacked_to = p.extends[1].basedir
        assert os.path.exists(git_temp_unpacked_to)
    assert not os.path.exists(git_temp_unpacked_to)

def test_profile_parameters():
    with profile.load_profile(source_cache, {"dir": user, "profile": "profile.yaml"}) as p:
        yield eq_, p.parameters, {'a': 1, 'b': 2, 'c': 3, 'd': 4}

def test_find_file():
    with profile.load_profile(source_cache, {"dir": user, "profile": "profile.yaml"}) as p:
        yield eq_, pjoin(user, 'foo.txt'), p.find_file('foo.txt')
        yield eq_, pjoin(user, 'user.txt'), p.find_file('user.txt')
        yield eq_, pjoin(base1, 'base1.txt'), p.find_file('base1.txt')
        yield ok_, pjoin(base2, 'base2.txt') != p.find_file('base2.txt') # from git repo
        yield ok_, os.path.exists(p.find_file('base2.txt')) # from git repo
        yield eq_, None, p.find_file('nonexisting.txt')

        def conflict():
            with assert_raises(profile.ConflictingProfilesError):
                p.find_file('conflicting.txt')
        yield conflict

def test_python_path():
    with profile.load_profile(source_cache, {"dir": user, "profile": "profile.yaml"}) as p:
        path = p.get_python_path()
        assert pjoin(user, 'base') in path
        assert pjoin(base1, 'base') in path
        # base2 is in git repo

def test_packages():
    with profile.load_profile(source_cache, {"dir": user, "profile": "profile.yaml"}) as p:
        pkgs = p.get_packages()
        yield eq_, pkgs, {'python': ('python', 'host'),
                          'numpy': ('numpy', None),
                          'gcc': ('gcc', 'host'),
                          'mpi': ('openmpi', '1.4.3')}
