"""
Unfortunately it was not straightforward to do the logging we want
with the Python `logging` module and it was simpler to just implement
from scratch.  We do however keep the API relatively similar.
"""

import os
import sys
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL

# Color handling for terminals (taken from waf)
COLORS = {
        'bold'  :'\x1b[01;1m',
        'red'   :'\x1b[01;31m',
        'green' :'\x1b[32m',
        'yellow':'\x1b[33m',
        'pink'  :'\x1b[35m',
        'blue'  :'\x1b[01;34m',
        'cyan'  :'\x1b[36m',
        'normal':'\x1b[0m',
        'cursor_on'  :'\x1b[?25h',
        'cursor_off' :'\x1b[?25l',
}

GOT_TTY = os.environ.get('TERM', 'dumb') not in ['dumb', 'emacs']
if GOT_TTY:
    try:
        GOT_TTY = sys.stderr.isatty()
    except AttributeError:
        GOT_TTY = False

USE_COLORS = GOT_TTY and 'NOCOLOR' not in os.environ

def colorize(s, color, use_colors=True):
    """
    Wraps `s` in color markers if sys.stderr is a terminal.

    Parameters
    ----------

    s : str
        String to colorize
    color : str
        Name of color (see `COLORS`). It can be prepended by "bold-" to
        make the font bold in addition.
    use_colors : bool
        If set to `False`, just return `s` regardless. Useful to pass through
        a coloring option without cluttering calling code with branches.
    """
    if not USE_COLORS or not use_colors:
        return s
    else:
        c = ''
        if color.startswith('bold-'):
            c += COLORS['bold']
            color = color[len('bold-'):]
        c += COLORS[color]
        return '%s%s%s' % (c, s, COLORS['normal'])

def get_log_color(level):
    if level >= WARNING:
        return 'bold-red'
    elif level >= INFO:
        return 'bold-blue'
    else:
        return 'yellow'

def get_level_name(level):
    if level >= CRITICAL:
        return 'CRITICAL'
    elif level >= ERROR:
        return 'ERROR'
    elif level >= WARNING:
        return 'WARNING'
    else:
        return None

class Logger(object):
    def __init__(self, level=INFO, names=(), stream=None):
        if stream is None:
            stream = sys.stderr
        if isinstance(names, str):
            names = tuple(names.split(':'))
        self.stream = stream
        self.names = names
        self.heading = ':'.join(names) if names else ''
        self.level = level

    def get_sub_logger(self, name):
        return Logger(self.level, self.names + (name,), self.stream)

    def log(self, level, msg, *args):
        if level < self.level:
            return
        if args:
            msg = msg % args

        heading = self.heading
        lname = get_level_name(level)
        if lname:
            heading += ' ' + lname
        heading = '[%s] ' % heading if heading else ''
        heading = colorize(heading, get_log_color(level))
        self.stream.write('%s%s\n' % (heading, msg))

    def debug(self, msg, *args):
        self.log(DEBUG, msg, *args)

    def info(self, msg, *args):
        self.log(INFO, msg, *args)

    def warning(self, msg, *args):
        self.log(WARNING, msg, *args)

    def error(self, msg, *args):
        self.log(ERROR, msg, *args)

    def critical(self, msg, *args):
        self.log(CRITICAL, msg, *args)

class _NullLogger(object):
    level = 0
    
    def get_sub_logger(self, *args, **kw):
        return self
    
    def _noop(self, *args, **kw):
        pass
    warning = error = debug = info = log = _noop

null_logger = _NullLogger()
