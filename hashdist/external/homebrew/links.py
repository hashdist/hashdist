import subprocess
import os
import shutil
from ...core.fileutils import (silent_relative_symlink, silent_makedirs, silent_copy)

pjoin = os.path.join

def homebrew_init_action(target, store_path):
    # copy $ARTIFACT/bin/brew
    silent_makedirs(pjoin(target, 'bin'))
    src_brew = pjoin(store_path, 'bin', 'brew')
    dst_brew = pjoin(target, 'bin', 'brew')
    silent_copy(src_brew, dst_brew)
    # copy Library
    src_library = pjoin(store_path, 'Library')
    dst_library = pjoin(target, 'Library')
    shutil.copytree(src_library, dst_library, symlinks=True)

    # link $ARTIFACT/Cellar
    src_cellar = pjoin(store_path, 'Cellar')
    dst_cellar = pjoin(target, 'Cellar')
    silent_relative_symlink(src_cellar, dst_cellar)

def homebrew_link_action(target, keg):
    brew = pjoin(target,'bin','brew')
    p = subprocess.check_call([brew, 'link', keg],
                              stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                              stderr=subprocess.PIPE)


def homebrew_link(rule, actions, expand_template, env):
    keg = rule['keg']
    store_path = rule['store']
    target = expand_template(rule['target'], env)
    if (homebrew_init_action, target, store_path) not in actions:
        actions.insert(0, (homebrew_init_action, target, store_path))
    actions.append((homebrew_link_action, target, keg))


