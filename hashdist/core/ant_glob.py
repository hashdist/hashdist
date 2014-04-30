"""
:mod:`hashdist.core.ant_glob` -- ant-inspired globbing
======================================================


"""

import os
import re
from os.path import join as pjoin

from glob import glob

def ant_iglob(pattern, cwd='', include_dirs=True):
    """
    Generator that iterates over files/directories matching the pattern.

    The syntax is ant-glob-inspired but currently only a small subset
    is implemented.

    Examples::

        *.txt         # matches "a.txt", "b.txt"
        foo/**/bar    # matches "foo/bar" and "foo/a/b/c/bar"
        foo*/**/*.bin # matches "foo/bar.bin", "foo/a/b/c/bar.bin", "foo3/a.bin"

    Illegal patterns::

        foo/**.bin  # '**' can only match 0 or more entire directories
        

    Issues
    ------

     * Does not support escaped / characters
     * Does not support any regular globbing-patterns besides *

    Parameters
    ----------

    pattern : str or list
        Glob pattern as described above. If a str, will be split by /;
        if a list, each item is a path component. It is only possible to
        specify a non-relative glob if `pattern` is a string.

    cwd : str
        Directory to start in. Pass an empty string or '.' for current directory;
        the former will emit 'rel/path/to/file' while the latter './rel/path/to/file'.
        (This added complexity is present in order to be able to reliably match
        prefixes by string value).

    include_dirs : bool
        Whether to include directories, or only glob files.
    
    """
    def should_include(fname):
        if include_dirs:
            return True
        else:
            return os.path.isfile(fname) or os.path.islink(fname)
        
    if isinstance(pattern, (str, unicode)):
        if pattern.startswith('/'):
            pattern = pattern[1:]
            cwd = '/'
        parts = pattern.split('/')
    else:
        parts = list(pattern)

    # if cwd is '', we want to search in '.' but not prepend output with './'
    assert cwd != '.'
    ret_cwd = cwd
    if cwd == '':
        cwd = '.'

    if len(parts) == 0:
        raise ValueError('empty glob pattern')
    
    part = parts[0]
    is_last = len(parts) == 1
    if part == '**':
        # do an os.walk over all sub-directories and re-launch glob_files in each
        # dirpath
        if is_last:
            raise ValueError('does not make sense with ** at end of pattern with '
                             'glob_files')
        for dirpath, dirnames, filenames in os.walk(cwd):
            if cwd == '.' and ret_cwd == '': # fixup relative path printing
                if len(dirpath) == 1:
                    dirpath = ''
                else:
                    assert dirpath[:2] == './'
                    dirpath = dirpath[2:]
            for x in ant_iglob(parts[1:], dirpath, include_dirs):
                yield x
    elif '**' in part:
        raise NotImplementedError('mixing ** and other strings in same path component not supported')
    else:
        # convert glob to a regex and recurse to next level within os.listdir
        part = re.escape(part)
        part = part.replace('\\*', '.*') + '$'
        part_re = re.compile(part)
        if is_last:
            for name in os.listdir(cwd):
                path = pjoin(ret_cwd, name)
                if part_re.match(name) and should_include(path):
                    yield path
        else:
            for name in os.listdir(cwd):
                path = pjoin(ret_cwd, name)
                if part_re.match(name) and os.path.isdir(path):
                    parts_ = parts[1:]
                    while not has_permission(path):
                        if '**' in parts[0]:
                            raise NotImplementedError('Cannot use ** in directories without read permission')
                        path = pjoin(path, parts_[0])
                        parts_ = parts_[1:]
                    for x in ant_iglob(parts_, path, include_dirs):
                        yield x

def has_permission(path):
    """
    Returns True if we have 'listdir' permissions. False otherwise.
    """
    return os.access(path, os.R_OK)
