import os
from os.path import join as pjoin
from nose.tools import eq_, ok_

from ...core.test.utils import *
from .. import profile

@temp_working_dir_fixture
def test_profile_resolution(d):
    #
    # setup
    #
    dump("user/profile.yaml", """\
    extends:
      - profile: profiles/linux.yaml
        dir: %(d)s/base1
      - profile: profiles/linux.yaml
        dir: %(d)s/base2
    
    parameters:
      a: 1
      b: 2
    """ % dict(d=d))

    dump("base1/profiles/linux.yaml", """\
    parameters:
      a: 0
      c: 3
    """ % dict(d=d))

    dump("base2/profiles/linux.yaml", """\
    parameters:
      d: 4
    """ % dict(d=d))

    # foo.txt from base1 overridden
    dump("user/foo.txt", "foo.txt in user")
    dump("base1/foo.txt", "foo.txt in base1")
    # separate files
    dump("user/user.txt", "in user")
    dump("base1/base1.txt", "in base1")
    dump("base2/base2.txt", "in base2")
    # conflicting files, raise error
    dump("base1/conflicting.txt", "in base1")
    dump("base2/conflicting.txt", "in base2")

    #
    # tests
    #
    p = profile.load_profile({"dir": pjoin(d, "user"), "profile": "profile.yaml"})
    yield eq_, p.parameters, {'a': 1, 'b': 2, 'c': 3, 'd': 4}

    yield eq_, pjoin(d, 'user', 'foo.txt'), p.find_file('foo.txt')
    yield eq_, pjoin(d, 'user', 'user.txt'), p.find_file('user.txt')
    yield eq_, pjoin(d, 'base1', 'base1.txt'), p.find_file('base1.txt')
    yield eq_, pjoin(d, 'base2', 'base2.txt'), p.find_file('base2.txt')
    yield eq_, None, p.find_file('nonexisting.txt')

    def conflict():
        with assert_raises(profile.ConflictingProfilesError):
            p.find_file('conflicting.txt')
    yield conflict
    
    yield eq_, p.get_python_path(), [pjoin(d, 'user', 'base'), pjoin(d, 'base2', 'base'),
                                     pjoin(d, 'base1', 'base')]
