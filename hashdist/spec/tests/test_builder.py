import mock
from pprint import pprint
import os
import shutil
import tempfile
import subprocess
import logging
from os.path import join as pjoin
from nose.tools import eq_, ok_

from ...core import SourceCache
from ...core.test.utils import *
from ...core.test.test_build_store import fixture as build_store_fixture
from .. import profile
from .. import builder
from ..package import PackageInstance


null_logger = logging.getLogger('null_logger')


def setup():
    global mock_tarball_tmpdir, mock_tarball,  mock_tarball_hash
    mock_tarball_tmpdir, mock_tarball,  mock_tarball_hash = make_temporary_tarball(
        [('README', 'file contents')])

def teardown():
    shutil.rmtree(mock_tarball_tmpdir)


class MockSourceCache:
    def put(self, x):
        pass

@temp_working_dir_fixture
def test_ready(d):
    dump(pjoin(d, 'profile.yaml'), """\
        package_dirs: [pkgs]
        packages: {a:, b:, c:, d:}
    """)

    dump(pjoin(d, 'pkgs', 'a.yaml'), "dependencies: {build: [b, c]}")
    dump(pjoin(d, 'pkgs', 'b.yaml'), "dependencies: {build: [d]}")
    dump(pjoin(d, 'pkgs', 'c.yaml'), "dependencies: {build: [d]}")
    dump(pjoin(d, 'pkgs', 'd.yaml'), "{}")

    class ProfileBuilderSubclass(builder.ProfileBuilder):
        def _compute_specs(self):
            pass

    null_logger = logging.getLogger('null_logger')
    p = profile.load_profile(null_logger, profile.TemporarySourceCheckouts(None),
                             pjoin(d, "profile.yaml"))
    pb = ProfileBuilderSubclass(None, MockSourceCache(), None, p)
    assert ['d'] == pb.get_ready_dict().keys()
    pb._built.update(pb.get_ready_dict().values())
    assert ['b', 'c'] == sorted(pb.get_ready_dict().keys())
    pb._built.update(pb.get_ready_dict().values())
    assert ['a'] == pb.get_ready_dict().keys()


@build_store_fixture()
def test_basic_build(tmpdir, sc, bldr, config):
    # Tests that we can assemble build specs and build packages.
    # Incl testing that the correct names are used for environment variables
    d = pjoin(tmpdir, 'tmp', 'profile')
    dump(pjoin(d, 'profile.yaml'), """\
        package_dirs: [pkgs]
        packages:
          copy_readme:
            the_dependency_renamed: the_dependency
        parameters:
          BASH: /bin/bash
    """)

    dump(pjoin(d, 'pkgs/copy_readme.yaml'), """\
        sources:
          - url: file:%(tar_file)s
            key: %(tar_hash)s
        dependencies:
          build: [the_dependency_renamed]
        build_stages:
          - name: the_copy_readme_file_stage
            handler: bash
            bash: |
              /bin/cat ${THE_DEPENDENCY_RENAMED_DIR}/README_IN_DEPENDENCY
              /bin/cp README ${ARTIFACT}
    """ % dict(tar_file=mock_tarball, tar_hash=mock_tarball_hash))

    dump(pjoin(d, 'pkgs/the_dependency.yaml'), """\
        sources:
          - url: file:%(tar_file)s
            key: %(tar_hash)s
        build_stages:
          - name: the_copy_readme_file_stage
            handler: bash
            bash: |
              echo hi
              /bin/cp README ${ARTIFACT}/README_IN_DEPENDENCY
        when_build_dependency:
          - prepend_path: PATH
            value: '${ARTIFACT}/foo/bar'
    """ % dict(tar_file=mock_tarball, tar_hash=mock_tarball_hash))

    null_logger = logging.getLogger('null_logger')
    p = profile.load_profile(null_logger, profile.TemporarySourceCheckouts(None),
                             pjoin(d, "profile.yaml"))
    pb = builder.ProfileBuilder(logger, sc, bldr, p)
    pb.build('the_dependency', config, 1, "always", False)
    pb.build('copy_readme', config, 1, "always", False)


@mock.patch('hashdist.spec.builder.ProfileBuilder._init', lambda self: None)
@temp_working_dir_fixture
def test_profile_packages_section(d):
    # Test inclusion of packages and resolution of package parameters

    # - a and b are two different leaf packages that can be interchanged to some degree.
    # - c has b as a dependency, but we pass in a instead
    # - e depends on d which is a "virtual package", we assign it to c
    # - a has a hard dependency on x and an optional on y; so x should be pulled in
    #   and y not
    #

    dump(pjoin(d, 'profile.yaml'), """\
        package_dirs: [pkgs]
        parameters:
          barparam: 'fromprofile'
        packages:
           a:
           b:
           c:
             b: a  # pass a as the b package...
           d:
             use: c  # really just assigns d as alias for c
           e:
           y:
             myval: yup
    """)

    dump(pjoin(d, 'pkgs/a.yaml'), dedent("""\
        dependencies: {build: [x, +q, +y, +z], run: [x, +q, +w]}
        parameters:
          - name: fooparam  # default value filled in
            type: int
            default: 3
          - name: barparam  # set by profile.yaml
            type: str
            default: 'fromdefault'
        build_stages:
          - handler: bash
            bash: |
              {{y and y.myval}}
    """))
    dump(pjoin(d, 'pkgs/b.yaml'), "dependencies: {build: [q]}")
    dump(pjoin(d, 'pkgs/c.yaml'), "dependencies: {build: [b]}")
    dump(pjoin(d, 'pkgs/e.yaml'), "dependencies: {build: [d]}")
    dump(pjoin(d, 'pkgs/x.yaml'), "profile_links: [{link: '*/**/*'}]")
    dump(pjoin(d, 'pkgs/y.yaml'), "parameters: [{name: myval}]")
    dump(pjoin(d, 'pkgs/z.yaml'), "")
    dump(pjoin(d, 'pkgs/q.yaml'), "")

    p = profile.load_profile(null_logger, profile.TemporarySourceCheckouts(None),
                             pjoin(d, "profile.yaml"))
    mock_sc = mock.Mock()
    mock_sc.put = lambda files: 'files:thekey'
    mock_bs = mock.Mock()
    mock_bs.is_present = lambda *args: True
    pb = builder.ProfileBuilder(logger, mock_sc, mock_bs, p)
    pb._load_packages()
    pkgs = pb._packages

    # package parameter should be present
    for name, pkg in pkgs.items():
        assert pkg.package == name

    # x: required package not specified in profile, auto-pulled in
    assert 'x' in pkgs
    assert '_run_x' not in pkgs
    assert isinstance(pkgs['a'].x, PackageInstance)
    assert pkgs['a']._run_x is pkgs['a'].x
    assert pkgs['a'].y.myval == 'yup'
    # y: optional package specified in profile
    assert 'y' in pkgs
    assert isinstance(pkgs['a'].y, PackageInstance)
    # z: optional package not specified, NOT pulled in
    assert 'z' not in pkgs
    assert pkgs['a'].z is None
    # q: optional in a, required in b -- should be passed to a as well!
    assert 'q' in pkgs
    assert pkgs['a'].q is not None and pkgs['b'].q is not None
    assert pkgs['a']._run_q is not None
    # w: optional run-dep
    assert pkgs['a']._run_w is None

    # Check that each package loaded the right YAML file
    for x in ['a', 'b', 'c', 'e', 'x']:
        eq_(pkgs[x]._spec.name, x)
        package_yaml = pkgs[x]._spec.condition_to_yaml_file.values()[0]
        ok_(package_yaml.filename.endswith('/%s.yaml' % x))

    # Package e depends on 'd', and 'd' uses the 'use:'-construct so that c satisfies dependency
    eq_(pkgs['e'].d._spec.name, 'c')
    # Package c was [assed a instead of b...
    eq_(pkgs['c'].b._spec.name, 'a')
    # Should have found default value for fooparam
    eq_(pkgs['a'].fooparam, 3)
    # barparam should be inherited from profile
    eq_(pkgs['a'].barparam, 'fromprofile')

    # Test the profile build spec
    pb._compute_specs()

    assert 'yup' in pb.get_build_script('a')

    spec = pb.get_profile_build_spec()
    eq_(spec.doc, {
        'build': {
            'commands': [
                {'hit': ['create-links', '$in0'], 'inputs': [{'json': [
                    {'action': 'relative_symlink',
                     'dirs': False,
                     'prefix': '${X_DIR}',
                     'select': u'${X_DIR}/*/**/*',
                     'target': '${ARTIFACT}'}]}
                    ]},
                {'hit': ['build-postprocess', '--write-protect']}],
           'import': [{'id': 'q/deoatuqg6fqo6tcmoxvwbmtpkxitqyp6',
                       'ref': 'Q'},
                      {'id': 'x/cye2gqdezpn343yduqzttawplswxdubw',
                       'ref': 'X'},
                      {'id': 'a/cefcdsfgxmwf5aysx56yedb6zv3eiouw',
                       'ref': 'A'},
                      {'id': 'b/n3inim7xqv4vkqn5oc7pop23g4uslptu',
                       'ref': 'B'},
                      {'id': 'c/nzfy5wj3cavumi7kb3srcf352ouychrq',
                       'ref': 'C'},
                      {'id': 'e/ry4sqshmcartjaz2p2bmdmcswygh3rfv',
                       'ref': 'E'},
                      {'id': 'y/66vt2inbxuodtn3jilnpkoajwtsb46kk',
                       'ref': 'Y'}]},
        'name': 'profile',
        'version': 'n'})
