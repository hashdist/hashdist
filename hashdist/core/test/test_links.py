import re
from shutil import copyfile
from os import symlink
from os.path import join as pjoin

from .utils import temp_working_dir, temp_dir, working_directory

from .. import links
from ..links import silent_makedirs
from pprint import pprint

def test_dry_run():
    rules = [dict(action='symlink', select='/bin/cp', prefix='/', target='$D'),
             dict(action='symlink', select='/usr/bin/gcc', prefix='/usr', target='$D'),
             dict(action='copy', select='/usr/bin/gcc', target='$D/foo/gcc'),
             dict(action='exclude', select='/usr/bin/gcc'),
             dict(action='symlink', select='/usr/bin/gcc', target='$D/gcc2'),
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
                           (copyfile, '/usr/bin/gcc', pjoin('foo', 'gcc'))]
        
        # relative `select`, relative target
        for rule in rules:
            rule['select'] = rule['select'][1:]
            if 'prefix' in rule:
                rule['prefix'] = rule['prefix'][1:]
        with working_directory('/'):
            actions = links.dry_run_links_dsl(rules, env)
        assert actions == [(silent_makedirs, 'bin'),
                           (symlink, 'bin/cp', 'bin/cp'),
                           (symlink, 'usr/bin/gcc', 'bin/gcc'),
                           (silent_makedirs, 'foo'),
                           (copyfile, 'usr/bin/gcc', pjoin('foo', 'gcc'))]
            
        
