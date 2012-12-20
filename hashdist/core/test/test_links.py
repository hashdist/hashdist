import re
from shutil import copyfile
from os import symlink
from os.path import join as pjoin

from .utils import temp_working_dir, temp_dir, working_directory
from .test_ant_glob import makefiles

from .. import links
from ..links import silent_makedirs
from pprint import pprint

def test_dry_run_simple():
    rules = [dict(action='symlink', select='/bin/cp', prefix='/', target='$D'),
             dict(action='symlink', select='/usr/bin/gcc', prefix='/usr', target='$D'),
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
                           (symlink, '/usr/bin/gcc', pjoin(d, 'bin/gcc')),
                           (silent_makedirs, pjoin(d, 'foo')),
                           (copyfile, '/usr/bin/gcc', pjoin(d, 'foo', 'gcc'))]


        # absolute `select`, relative `target`
        for rule in rules:
            # remove $D from all targets
            if 'target' in rule:
                if rule['target'] == '$D':
                    rule['target'] = ''
                else:
                    rule['target'] = rule['target'][3:]
        with working_directory('/'):
            actions = links.dry_run_links_dsl(rules, env)
        assert actions == [(silent_makedirs, 'bin'),
                           (symlink, '/bin/cp', 'bin/cp'),
                           (symlink, '/usr/bin/gcc', 'bin/gcc'),
                           (silent_makedirs, 'foo'),
                           (copyfile, '/usr/bin/gcc', 'foo/gcc')]
        
        # relative `select`, relative target
        for rule in rules:
            # remove / from all selects
            if 'select' in rule:
                rule['select'] = rule['select'][1:]
            else:
                rule['source'] = rule['source'][1:]
            if 'prefix' in rule:
                rule['prefix'] = rule['prefix'][1:]
        with working_directory('/'):
            actions = links.dry_run_links_dsl(rules, env)
        assert actions == [(silent_makedirs, 'bin'),
                           (symlink, 'bin/cp', 'bin/cp'),
                           (symlink, 'usr/bin/gcc', 'bin/gcc'),
                           (silent_makedirs, 'foo'),
                           (copyfile, 'usr/bin/gcc', 'foo/gcc')
                           ]

            
def test_dry_run_glob():
    rules = [dict(action='symlink', select='**/*$SUFFIX', target='foo', prefix='')]
    env = dict(SUFFIX='.txt')
    with temp_working_dir() as d:
        makefiles('a0/b0/c0/d0.txt a0/b0/c0/d1.txt a0/b1/c1/d0.txt a0/b.txt'.split())

        actions = links.dry_run_links_dsl(rules, env)
        assert actions == [(silent_makedirs, 'foo/a0/b0/c0'),
                           (symlink, 'a0/b0/c0/d1.txt', 'foo/a0/b0/c0/d1.txt'),
                           (silent_makedirs, 'foo/a0'),
                           (symlink, 'a0/b.txt', 'foo/a0/b.txt'),
                           (symlink, 'a0/b0/c0/d0.txt', 'foo/a0/b0/c0/d0.txt'),
                           (silent_makedirs, 'foo/a0/b1/c1'),
                           (symlink, 'a0/b1/c1/d0.txt', 'foo/a0/b1/c1/d0.txt')]

        rules[0]['prefix'] = 'a0'
        actions = links.dry_run_links_dsl(rules, env)
        assert actions == [(silent_makedirs, 'foo/b0/c0'),
                           (symlink, 'a0/b0/c0/d1.txt', 'foo/b0/c0/d1.txt'),
                           (silent_makedirs, 'foo'),
                           (symlink, 'a0/b.txt', 'foo/b.txt'),
                           (symlink, 'a0/b0/c0/d0.txt', 'foo/b0/c0/d0.txt'),
                           (silent_makedirs, 'foo/b1/c1'),
                           (symlink, 'a0/b1/c1/d0.txt', 'foo/b1/c1/d0.txt')]
          
