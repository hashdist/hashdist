import os
from os.path import join as pjoin

from nose.tools import eq_, ok_


from ...core.test import utils
from ...deps import sh

from ...core.test.test_build_store import fixture


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

@fixture()
def test_build_profile(tempdir, sc, bldr, cfg):

    # First build something we can depend on
    corelib_spec = {
        'name': 'corelib',
        'version': 'n',
        'build': {
            'script': [['hdist', 'build-write-files']]
            },
        'files': [
            {
                'target': '$ARTIFACT/artifact.json',
                "object": {
                    "install": {
                        "script": [["@hdist", "create-links", "--key=install/links", "artifact.json"]],
                        "links": [{"action": "symlink",
                                   "select": "$ARTIFACT/*/**/*",
                                   "prefix": "$ARTIFACT",
                                   "target": "$PROFILE"}]
                     }
                 }
             },
            {
                'target': '$ARTIFACT/should-be-removed/hello',
                'text': ["Hello world!"]
            },
            {
                'target': '$ARTIFACT/share/hello', # "share" should not be removed
                'text': ["Hello world!"]
            },
           
            ]
        }
    corelib_id, corelib_path = bldr.ensure_present(corelib_spec, cfg)

    # Do a build which pushes and pops the temporary environment. We test that:
    # 1) None of the linked-in files are present afterwards
    # 2) That link to $CORELIB/should-be-removed/hello is present between push/pop
    # 3) That "share" does not disappear (contains another file created in meantime),
    #    but "should-be-removed" does (empty after popping profile).
    app_spec = {
        "name": "app",
        "version": "n",
        "build": {
            "import": [{"id": corelib_id}],
            "script": [
                ["/bin/echo>$ARTIFACT/hello", "hello world"], # must not be removed by pop
                ["hdist", "build-profile", "push"],
                ["/bin/echo>$ARTIFACT/share/foo", "hello world"], # preserve "share" dir
                ["/bin/readlink>$ARTIFACT/result", "$ARTIFACT/should-be-removed/hello"],
                ["hdist", "build-profile", "pop"],
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
