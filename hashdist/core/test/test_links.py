import re
from shutil import copyfile
from os import symlink
from os.path import join as pjoin
import os
import shutil

from nose.tools import assert_raises

from .utils import temp_working_dir, temp_dir, working_directory, eqsorted_, cat
from .test_ant_glob import makefiles

from .. import links
from ..links import silent_makedirs, silent_unlink
from pprint import pprint

def test_dry_run_simple():
    rules = [dict(action='symlink', select=['/bin/cp', '/bin/ls'], prefix='/', target='$D'),
             dict(action='symlink', select=['/usr/bin/gcc'], prefix='/usr', target='$D'),
             dict(action='copy', source='/usr/bin/gcc', target='$D/foo/gcc'),
             dict(action='exclude', source='/usr/bin/gcc'),
             dict(action='symlink', source='/usr/bin/gcc', target='$D/gcc2'),
             ]

    with temp_dir() as d:
        # absolute `select` and `target`
        env = dict(D=d)
        actions = links.dry_run_links_dsl(rules, env)
        assert actions == [(silent_makedirs, pjoin(d, 'bin')),
                           (symlink, '/bin/cp', pjoin(d, 'bin/cp')),
                           (symlink, '/bin/ls', pjoin(d, 'bin/ls')),
                           (symlink, '/usr/bin/gcc', pjoin(d, 'bin/gcc')),
                           (silent_makedirs, pjoin(d, 'foo')),
                           (copyfile, '/usr/bin/gcc', pjoin(d, 'foo', 'gcc'))]


        # absolute `select`, relative `target`
        env['D'] = 'subdir'
        with working_directory('/'):
            actions = links.dry_run_links_dsl(rules, env)
        assert actions == [(silent_makedirs, 'subdir/bin'),
                           (symlink, '/bin/cp', 'subdir/bin/cp'),
                           (symlink, '/bin/ls', 'subdir/bin/ls'),
                           (symlink, '/usr/bin/gcc', 'subdir/bin/gcc'),
                           (silent_makedirs, 'subdir/foo'),
                           (copyfile, '/usr/bin/gcc', 'subdir/foo/gcc')]
        
        # relative `select`, relative target
        for rule in rules:
            # remove / from all selects
            if 'select' in rule:
                rule['select'] = [x[1:] for x in rule['select']]
            else:
                rule['source'] = rule['source'][1:]
            if 'prefix' in rule:
                rule['prefix'] = rule['prefix'][1:]
        with working_directory('/'):
            actions = links.dry_run_links_dsl(rules, env)
        assert actions == [(silent_makedirs, 'subdir/bin'),
                           (symlink, 'bin/cp', 'subdir/bin/cp'),
                           (symlink, 'bin/ls', 'subdir/bin/ls'),
                           (symlink, 'usr/bin/gcc', 'subdir/bin/gcc'),
                           (silent_makedirs, 'subdir/foo'),
                           (copyfile, 'usr/bin/gcc', 'subdir/foo/gcc')
                           ]

        # force
        for rule in rules:
            rule['force'] = True
        with working_directory('/'):
            actions = links.dry_run_links_dsl(rules, env)
        assert actions == [(silent_makedirs, 'subdir/bin'),
                           (silent_unlink, 'subdir/bin/cp'),
                           (symlink, 'bin/cp', 'subdir/bin/cp'),
                           (silent_unlink, 'subdir/bin/ls'),
                           (symlink, 'bin/ls', 'subdir/bin/ls'),
                           (silent_unlink, 'subdir/bin/gcc'),
                           (symlink, 'usr/bin/gcc', 'subdir/bin/gcc'),
                           (silent_makedirs, 'subdir/foo'),
                           (silent_unlink, 'subdir/foo/gcc'),
                           (copyfile, 'usr/bin/gcc', 'subdir/foo/gcc')
                           ]

def findfiles(path):
    r = []
    for dirname, subdirs, filenames in os.walk(path):
        for filename in filenames:
            r.append(pjoin(dirname, filename))
    return r
            
def test_run_glob():
    rules = [dict(action='symlink', select='**/*$SUFFIX', target='foo', prefix='')]
    env = dict(SUFFIX='.txt')
    with temp_working_dir() as d:
        makefiles('a0/b0/c0/d0.txt a0/b0/c0/d1.txt a0/b1/c1/d0.txt a0/b.txt'.split())

        links.execute_links_dsl(rules, env)
        eqsorted_(['foo/a0/b.txt', 'foo/a0/b1/c1/d0.txt', 'foo/a0/b0/c0/d0.txt', 'foo/a0/b0/c0/d1.txt'],
                  findfiles('foo'))
        shutil.rmtree('foo')

        rules[0]['prefix'] = 'a0'
        links.execute_links_dsl(rules, env)

        eqsorted_(['foo/b.txt', 'foo/b0/c0/d0.txt', 'foo/b0/c0/d1.txt', 'foo/b1/c1/d0.txt'],
                  findfiles('foo'))

def test_force():
    rules = [dict(action='symlink', select='**/*.txt', target='foo', prefix='')]
    env = {}
    with temp_working_dir() as d:
        makefiles('a0/b0/c0/d0.txt a0/b0/c0/d1.txt a0/b1/c1/d0.txt a0/b.txt'.split())

        links.execute_links_dsl(rules, env)
        with assert_raises(OSError):
            links.execute_links_dsl(rules, env)
        rules[0]['force'] = True
        links.execute_links_dsl(rules, env)
        # should also work if target *doesn't* exist...
        shutil.rmtree('foo')
        links.execute_links_dsl(rules, env)
        
def test_launcher():
    # we just use the /bin/cp program as a mock and check that the structure is correct
    rules = [dict(action='launcher', select=['a', 'b'], target='foo', prefix='')]
    with temp_working_dir() as d:
        makefiles(['a', 'b'])
        links.execute_links_dsl(rules, {}, launcher_program='/bin/cp')
        os.chdir('foo')
        assert os.path.exists('launcher')
        assert os.stat('launcher').st_mode | 0o111
        assert os.readlink('a') == 'launcher'
        assert os.readlink('b') == 'launcher'
        assert cat('a.link') == '../a'
        assert cat('b.link') == '../b'
