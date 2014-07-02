"""
Unfortunately it was not straightforward to do the logging we want
with the Python `logging` module and it was simpler to just implement
from scratch.  We do however keep the API relatively similar.
"""

import os
import sys
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
import textwrap

NOLOGGING = 10**6

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
    """
    Parameters
    ----------

    level : int
        For pretty-printing, ignore all log messages below this level.
        Has no effect for raw streams.

    names : str or list
        Header to put at the left of each formatted log message

    streams : list of (stream, is_raw)
        Streams to emit log messages too. If `is_raw` is set, the
        logged messages are printed to the stream without any formatting,
        the only thing that changes is adding a newline "\n" for each
        call.
    """
    def __init__(self, level=INFO, names=(), streams=None, parent_logger=None):
        if streams is None:
            streams = [(sys.stderr, False)]
        if isinstance(names, str):
            names = tuple(names.split(':'))
        self.names = names
        self.heading = ':'.join(names) if names else ''
        self.level = level
        self.streams = streams
        self.parent_logger = parent_logger
        if self.parent_logger:
            self.error_occurred = self.parent_logger.error_occurred
        else:
            self.error_occurred = False

    def set_level(self, level):
        self.level = level

    def get_sub_logger(self, name):
        return Logger(self.level, self.names + (name,), self.streams, self)

    def push_stream(self, stream, raw=False):
        self.streams.append((stream, raw))

    def pop_stream(self):
        self.streams.pop()

    def set_error_occurred(self, value):
        self.error_occurred = value
        a = self
        while a.parent_logger:
            a = a.parent_logger
            a.error_occurred = value

    def log(self, level, msg, *args):
        if args:
            msg = msg % args
        heading = self.heading
        lname = get_level_name(level)
        if lname and heading:
            heading += ' ' + lname
        elif lname:
            heading = lname
        heading = '[%s] ' % heading if heading else ''
        heading = colorize(heading, get_log_color(level))
        for stream, is_raw in self.streams:
            if is_raw:
                stream.write(('%s\n' % (msg)).encode('ascii', 'ignore'))
                stream.flush()
            elif level >= self.level:
                stream.write(u'%s%s\n' % (heading, msg))
        if level >= ERROR:
            self.set_error_occurred(True)

    def log_lines(self, level, text):
        for line in textwrap.wrap(textwrap.dedent(text), 70):
            self.log(level, line)

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

# using null_logger one will still be able to attach raw streams
null_logger = Logger(NOLOGGING)
