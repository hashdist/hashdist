r"""
ANSI Colors
===========

This module provides utility functions around colorization.

EXAMPLES::

    >>> from hashdist.util.ansi_color import color
    >>> color.red('hello')    # no ansi sequences since doctest output is redirected
    'hello'
"""

import os
import sys
import re


def want_color():
    """
    Whether colors should be used

    Returns:
    --------

    Boolean. Whether it is desirable to use ansi colors.

    EXAMPLES::

        >>> from hashdist.util.ansi_color import want_color
        >>> want_color()
        False
    """
    if 'NOCOLOR' in os.environ:
        return False
    if os.environ.get('TERM', None) in ['dumb', 'emacs']:
        return False
    try:
        return sys.stdout.isatty() and sys.stderr.isatty()
    except AttributeError:
        return False


_attrs = {
    'reset':     '39;49;00m',
    'bold':      '01m',
    'faint':     '02m',
    'standout':  '03m',
    'underline': '04m',
    'blink':     '05m',
}

_colors = [
    ('black',     'darkgray'),
    ('darkred',   'red'),
    ('darkgreen', 'green'),
    ('brown',     'yellow'),
    ('darkblue',  'blue'),
    ('purple',    'fuchsia'),
    ('turquoise', 'teal'),
    ('lightgray', 'white'),
]

class _Color(object):

    _codes = {}

    @classmethod
    def _add_code(cls, name, code):
        cls._codes[name] = code
        if want_color():
            def colorizer(self, text):
                return cls._codes.get(name) + text + cls._codes.get('reset')
        else:
            def colorizer(self, text):
                return text
        setattr(_Color, name, colorizer)

for _name, _value in _attrs.items():
    _Color._add_code(_name, '\x1b[' + _value)

for i, (dark, light) in enumerate(_colors):
    _Color._add_code(dark,  '\x1b[%im' % (i+30))
    _Color._add_code(light, '\x1b[%i;01m' % (i+30))

color = _Color()


_ANSI_COLOR_RE = re.compile(r'\x1b\[[0-9;]*m')

def monochrome(string):
    """
    Strip ANSI color sequences from the input

    Arguments:
    ----------

    string : str
        A string, possibly containing ANSI color sequences

    Returns:
    --------

    String containing the same content but without color sequences.

    EXAMPLES::

        >>> from hashdist.util.ansi_color import monochrome
        >>> monochrome(r'\x1b[31;01mhello\x1b[39;49;00m')
        'hello'
    """
    return re.sub(_ANSI_COLOR_RE, '', string)


