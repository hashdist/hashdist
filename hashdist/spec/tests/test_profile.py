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

    # base2 is stored in a git repo; linux.yaml refers to common.yaml so that
    # we have two profiles with the same repo, which should not be deleted twice...
    dump(pjoin(base2, "profiles", "linux.yaml"), """\
        include:
          - profile: common.yaml  # tests: resolution relative to current file, and refcount of tempdirs
        packages:
          - numpy/host # changed to numpy/latest in user/profile.yaml
          - python/host # not changed
    """)
    dump(pjoin(base2, "profiles", "common.yaml"), """\
        parameters:
          global:
            d: 4
    """)
    commit = gitify(base2)

    dump(pjoin(user, "profile.yaml"), """\
        extends:
          - profile: profiles/linux.yaml
            dir: %(base1)s

          # Git import; define both profile, package_dir and base_dir relative to root of
          # git repo given
          - profile: profiles/linux.yaml
            package_dir: pkgs
            base_dir: base
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


@temp_working_dir_fixture
def test_git_loading(d):
    dump(pjoin(d, 'gitrepo', 'in_parent_dir.yaml'), """\
    """)

    dump(pjoin(d, 'gitrepo', 'subdir', 'in_sub_dir.yaml'), """\
        include:
          - profile: ../in_parent_dir.yaml
    """)

    commit = gitify(pjoin(d, 'gitrepo'))

    dump(pjoin(d, 'user', 'profile.yaml'), """\
        include:
          - profile: subdir/in_sub_dir.yaml
            urls: [%s]
            key: git:%s
    """ % (pjoin(d, 'gitrepo'), commit))

    p = profile.load_profile(source_cache, {"profile": pjoin(d, 'user', 'profile.yaml')})
    git_tmp = os.path.dirname(p.includes[0].includes[0].filename)
    assert os.path.exists(git_tmp)
    assert os.path.exists(pjoin(git_tmp, 'subdir', 'in_sub_dir.yaml'))
    assert git_tmp != pjoin(d, 'gitrepo')
    del p
    assert not os.path.exists(git_tmp)

@temp_working_dir_fixture
def test_profile_parameters(d):
    dump(pjoin(d, "profile.yaml"), """\
        include:
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
def test_find_file(d):
    dump(pjoin(d, "level3", "profile.yaml"), """\
        include:
          - profile: %s/level2/profiles/profile.yaml
    """ % d)

    dump(pjoin(d, "level2", "profiles", "profile.yaml"), """\
        include:
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
