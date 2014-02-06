import sys
import os
from os.path import join as pjoin
import json
import shutil
from os import makedirs
from textwrap import dedent

from nose.tools import eq_, ok_
from .utils import (temp_working_dir, temp_working_dir_fixture, assert_raises,
                    cat)
from ..fileutils import touch

from .. import build_tools

from nose import SkipTest

def test_execute_files_dsl():
    def assertions(dirname):
        with file(pjoin(dirname, 'bin', 'hit')) as f:
            x = f.read().strip()
            assert x == ("sys.path.insert(0, sys.path.join('%s', 'lib'))" % dirname)
        assert os.stat(pjoin(dirname, 'bin', 'hit')).st_mode & 0100
        with file(pjoin(dirname, 'doc.json')) as f:
            assert json.load(f) == {"foo": "bar"}

    with temp_working_dir() as d:
        doc = [
            {
                "target": "$ARTIFACT/bin/hit",
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

class MockBuildStore:
    def __init__(self, is_in):
        self.is_in = is_in

    def is_path_in_build_store(self, d):
        return self.is_in

@temp_working_dir_fixture
def test_python_shebang(d):
    if 'linux' not in sys.platform:
        raise SkipTest('Linux only')

    from subprocess import Popen, PIPE

    makedirs(pjoin(d, 'my-python', 'bin'))
    makedirs(pjoin(d, 'profile', 'bin'))
    
    abs_interpreter = pjoin(d, 'my-python', 'bin', 'python')
    script_file = pjoin(d, 'profile', 'bin', 'myscript')
    os.symlink(sys.executable, abs_interpreter)
    os.symlink(abs_interpreter, pjoin(d, 'profile', 'bin', 'python'))

    script = dedent('''\
    #! %s
    
    # This is a comment
    # """
    
    u"""A test script
    """
    import sys
    print sys.executable
    print ':'.join(sys.argv)
    ''') % abs_interpreter

    # Should be no difference when path is not in build store
    new_script = ''.join(build_tools.make_relative_multiline_shebang(MockBuildStore(False),
                                                                     script_file,
                                                                     script.splitlines(True)))
    assert new_script == script
    # Path is in build store...
    new_script = ''.join(build_tools.make_relative_multiline_shebang(MockBuildStore(True),
                                                                     script_file,
                                                                     script.splitlines(True)))
    assert new_script != script

    with open(script_file, 'w') as f:
        f.write(new_script)
        
    os.chmod(script_file, 0o755)
    os.symlink('profile/bin/myscript', 'scriptlink')

    def runit(entry_point):
        p = Popen([entry_point, "a1 a2", "b "], stdout=PIPE)
        out, _ = p.communicate()
        outlines = out.splitlines()
        assert p.wait() == 0
        eq_("%s:a1 a2:b " % entry_point, outlines[1])
        return outlines[0]

    for relative in ['./scriptlink', 'profile/bin/myscript']:
        for entry_point in [relative, os.path.realpath(relative)]:
            touch(pjoin(d, 'profile', 'artifact.json'))
            #print cat(entry_point)
            intp = runit(entry_point)
            eq_("%s/profile/bin/python" % d, intp)

            os.unlink(pjoin(d, 'profile', 'artifact.json'))
            #intp = runit(entry_point)
            #assert "%s/my-python/bin/python" % d == intp

