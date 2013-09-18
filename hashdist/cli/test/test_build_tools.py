import sys
import os
from os.path import join as pjoin
import subprocess

from nose.tools import eq_, ok_


from ...core.test import utils

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

@fixture()
def test_build_profile(tempdir, sc, bldr, cfg):

    # First build something we can depend on
    corelib_spec = {
        'name': 'corelib',
        'version': 'n',
        'build': {
            'commands': [
                {"hit": ["build-write-files", "$in0"],
                 "inputs": [
                     {"json": [
                         {'target': '$ARTIFACT/should-be-removed/hello', 'text': ["Hello world!"]},
                         # "share" should not be removed 
                         {'target': '$ARTIFACT/share/hello', 'text': ["Hello world!"]}
                         ],
                      }
                     ]
                 }
                ]
            },
        'profile_install': {
            "commands": [
                {"hit": ["create-links", "$in0"],
                 "inputs": [
                     {"json": [{"action": "symlink",
                                "select": "$ARTIFACT/*/**/*",
                                "prefix": "$ARTIFACT",
                                "target": "$PROFILE"}]
                      }]
                 },
                ]
            }
        }
    corelib_id, corelib_path = bldr.ensure_present(corelib_spec, cfg)

    # Do a build which pushes and pops the temporary environment. We test that:
    # 1) None of the linked-in files are present afterwards
    # 2) That link to $CORELIB/should-be-removed/hello is present between push/pop
    # 3) That "share" does not disappear (contains another file created in meantime),
    #    but "should-be-removed" does (empty after popping profile).

    if os.path.exists('/usr/bin/readlink'):
        readlink = '/usr/bin/readlink'
    elif os.path.exists('/bin/readlink'):
        readlink = '/bin/readlink'
    else:
        raise OSError('Unable to find system readlink')

    app_spec = {
        "name": "app",
        "version": "n",
        "build": {
            "import": [{"id": corelib_id}],
            "commands": [
                {"cmd": ["/bin/echo", "hello world"], "append_to_file": "$ARTIFACT/hello"}, # must not be removed by pop
                {"hit": ["build-profile", "push"]},
                {"cmd": ["/bin/echo", "hello world"], "append_to_file": "$ARTIFACT/share/foo"}, # preserve "share" dir
                {"cmd": [readlink, "$ARTIFACT/should-be-removed/hello"], "append_to_file": "$ARTIFACT/result"},
                {"hit": ["build-profile", "pop"]},
                ]
            }
        }
    app_id, app_path = bldr.ensure_present(app_spec, cfg)

    files = os.listdir(app_path)
    assert 'share' in files
    assert 'should-be-removed' not in files
    assert ['foo'] == os.listdir(pjoin(app_path, 'share'))

    with open(pjoin(app_path, 'result')) as f:
        # target of the link that was temporarily present
        eq_(pjoin(corelib_path, 'should-be-removed', 'hello'), f.read().strip())
