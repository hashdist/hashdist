import os
from os.path import join as pjoin
from ...core.test import utils
from ...deps import sh

oldpath = None

def setup():
    global oldpath
    oldpath = os.environ['PATH']
    bindir = os.path.realpath(pjoin(os.path.dirname(__file__), '..', '..', '..', 'bin'))
    os.environ['PATH'] = bindir + os.pathsep + os.environ['PATH']

def teardown():
    os.environ['PATH'] = oldpath

def test_symlinks():
    with utils.temp_working_dir() as d:
        with file('build.json', 'w') as f:
            f.write('''\
            {
              "section1" : {
                "section2" : [
                  {"target": "foo", "link-to" : ["/bin/ls", "/bin/cp"]},
                  {"target": "bar", "link-to" : ["/bin/ls", "/bin/mv"]}
                ]
              }
            }
            ''')
        sh.hdist('buildtool-symlinks', '--key=section1/section2')
        assert os.path.realpath('foo/ls') == '/bin/ls'
        assert os.path.realpath('bar/mv') == '/bin/mv'
