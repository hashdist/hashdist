"""
:mod:`hashdist.core.ant_glob` -- ant-inspired globbing
======================================================


"""

import os
import re
from os.path import join as pjoin

from glob import glob

def glob_files(pattern, cwd='.'):
    """
    Generator that iterates over files matching the pattern.

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
    
    """
    if isinstance(pattern, (str, unicode)):
        if pattern.startswith('/'):
            pattern = pattern[1:]
            cwd = '/'
        parts = pattern.split('/')
    else:
        parts = list(pattern)

    if len(parts) == 0:
        raise ValueError('empty glob pattern')
    
    part = parts[0]
    is_last = len(parts) == 1
    if part == '**':
        if is_last:
            raise ValueError('does not make sense with ** at end of pattern with '
                             'glob_files')
        for dirpath, dirnames, filenames in os.walk(cwd):
            for x in glob_files(parts[1:], dirpath):
                yield x
    elif '**' in part:
        raise NotImplementedError('mixing ** and other strings in same path component not supported')
    else:
        part = re.escape(part)
        part = part.replace('\\*', '.*') + '$'
        part_re = re.compile(part)
        if is_last:
            for name in os.listdir(cwd):
                path = pjoin(cwd, name)
                if part_re.match(name) and os.path.isfile(path):
                    yield path
        else:
            for name in os.listdir(cwd):
                path = pjoin(cwd, name)
                if part_re.match(name) and os.path.isdir(path):
                    for x in glob_files(parts[1:], path):
                        yield x
        
