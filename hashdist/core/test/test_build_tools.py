import os
from os.path import join as pjoin
import json

from nose.tools import assert_raises
from .utils import temp_working_dir

from .. import build_tools


def test_execute_files_dsl():
    def assertions(dirname):
        with file(pjoin(dirname, 'bin', 'hdist')) as f:
            x = f.read().strip()
            assert x == ("sys.path.insert(0, sys.path.join('%s', 'lib'))" % dirname)
        assert os.stat(pjoin(dirname, 'bin', 'hdist')).st_mode & 0100
        with file(pjoin(dirname, 'doc.json')) as f:
            assert json.load(f) == {"foo": "bar"}

    with temp_working_dir() as d:
        doc = [
            {
                "target": "$ARTIFACT/bin/hdist",
                "executable": True,
                "expandvars": True,
                "text": [
                    "sys.path.insert(0, sys.path.join('$ARTIFACT', 'lib'))"
                ]
            },
            {
                "target": "$ARTIFACT/doc.json",
                "object": {"foo": "bar"}
            }
        ]
        # relative paths
        build_tools.execute_files_dsl(doc, dict(ARTIFACT='A'))
        assertions('A')

        # error on collisions for both types
        with assert_raises(OSError):
            build_tools.execute_files_dsl([doc[0]], dict(ARTIFACT='A'))
        with assert_raises(OSError):
            build_tools.execute_files_dsl([doc[1]], dict(ARTIFACT='A'))
        
        # absolute paths
        with temp_working_dir() as another_dir:
            build_tools.execute_files_dsl(doc, dict(ARTIFACT=pjoin(d, 'B')))
        assertions(pjoin(d, 'B'))

        # test with a plain file and relative target
        doc = [{"target": "foo/bar/plainfile", "text": ["$ARTIFACT"]}]
        build_tools.execute_files_dsl(doc, dict(ARTIFACT='ERROR_IF_USED'))
        with file(pjoin('foo', 'bar', 'plainfile')) as f:
            assert f.read() == '$ARTIFACT'
        assert not (os.stat(pjoin('foo', 'bar', 'plainfile')).st_mode & 0100)

        # test with a file in root directory
        doc = [{"target": "plainfile", "text": ["bar"]}]
        build_tools.execute_files_dsl(doc, {})
        with file(pjoin('plainfile')) as f:
            assert f.read() == 'bar'

