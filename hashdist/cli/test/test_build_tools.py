import sys
import os
from os.path import join as pjoin
import subprocess

from nose.tools import eq_, ok_


from ...core.test import utils
from ...core.test.utils import which
from ...core.test.test_build_store import fixture


def setup():
    global hdist_script, projdir
    projdir = os.path.realpath(pjoin(os.path.dirname(__file__), '..', '..', '..'))
    hdist_script = pjoin(projdir, 'bin', 'hit')

def hit(*args, **kw):
    env = dict(kw['env'])
    env['PYTHONPATH'] = projdir
    p = subprocess.Popen([sys.executable, hdist_script] + list(args), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    r = p.communicate()
    if p.wait() != 0:
        assert False
    return r

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
        hit('create-links', '--key=section1/section2', 'build.json', env=env)
        assert os.path.realpath('foo') == '/bin/ls'
        assert os.path.realpath('bar/bin/ls') == '/bin/ls'

