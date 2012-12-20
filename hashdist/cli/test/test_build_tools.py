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
                   {"action": "symlink", "target": "$FOO", "source" : "/bin/ls"},
                   {"action": "symlink", "target": "bar", "select" : "/bin/ls", "prefix": "/"}
                ]
              }
            }
            ''')
        env = dict(os.environ)
        env['FOO'] = 'foo'
        sh.hdist('create-links', '--key=section1/section2', 'build.json', _env=env)
        assert os.path.realpath('foo') == '/bin/ls'
        assert os.path.realpath('bar/bin/ls') == '/bin/ls'
