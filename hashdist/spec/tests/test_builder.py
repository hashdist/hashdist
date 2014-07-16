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
    assert ['d'] == pb.get_ready_list()
    pb._built.add('d')
    assert ['b', 'c'] == sorted(pb.get_ready_list())
    pb._built.add('b')
    pb._built.add('c')
    assert ['a'] == pb.get_ready_list()


@build_store_fixture()
def test_basic_build(tmpdir, sc, bldr, config):
    d = pjoin(tmpdir, 'tmp', 'profile')
    dump(pjoin(d, 'profile.yaml'), """\
        package_dirs: [pkgs]
        packages: {copy_readme:, the_dependency:}
        parameters:
          BASH: /bin/bash
    """)

    dump(pjoin(d, 'pkgs/copy_readme.yaml'), """\
        sources:
          - url: file:%(tar_file)s
            key: %(tar_hash)s
        dependencies:
          build: [the_dependency]
        build_stages:
          - name: the_copy_readme_file_stage
            handler: bash
            bash: |
              /bin/cat ${THE_DEPENDENCY_DIR}/README_IN_DEPENDENCY
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
    pb.build('the_dependency', config, 1, "never", False)
    pb.build('copy_readme', config, 1, "never", False)
