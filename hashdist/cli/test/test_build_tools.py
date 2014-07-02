import sys
import os
from os.path import join as pjoin
import subprocess

from nose.tools import eq_, ok_


from ...core.test import utils
from ...core.test.utils import which, temp_working_dir_fixture, dump
from ...core.test.test_build_store import fixture

def setup():
    global hdist_script, projdir
    projdir = os.path.realpath(pjoin(os.path.dirname(__file__), '..', '..', '..'))
    hdist_script = pjoin(projdir, 'bin', 'hit')

def hit(*args, **kw):
    env = dict(kw['env'])
    expected_status = kw.get('expected_status', 0)
    env['PYTHONPATH'] = projdir
    p = subprocess.Popen([sys.executable, hdist_script] + list(args), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    assert p.wait() == expected_status
    return out, err

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
        assert os.path.realpath('foo') == os.path.realpath('/bin/ls')
        assert os.path.realpath('bar/bin/ls') == os.path.realpath('/bin/ls')

@temp_working_dir_fixture
def test_postprocess_check_relocatable_ok(d):
    # should ignore pyo and pyc files with the right flags
    dump(pjoin(d, 'a', 'b', 'c.pyc'), 'foo%sfoo' % d)
    dump(pjoin(d, 'a', 'b', 'c.pyo'), 'foo%sfoo' % d)
    env = dict(os.environ)
    env['ARTIFACT'] = d
    hit('build-postprocess', '--check-relocatable', '--check-ignore=.*\\.pyc$', '--check-ignore=.*\\.pyo$',
        env=env)


@temp_working_dir_fixture
def test_postprocess_check_relocatable_fails(d):
    # should ignore pyo and pyc files with the right flags
    dump(pjoin(d, 'a', 'b', 'c.txt'), 'foo%sfoo' % d)
    env = dict(os.environ)
    env['ARTIFACT'] = d
    hit('build-postprocess', '--check-relocatable', expected_status=127, env=env)
