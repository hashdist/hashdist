"""Main entry-point

Other ``hashdist.cmd.*`` modules register their sub-commands using the
:func:`subcommand` and :func:`subcommand_args` decorators.
"""

from __future__ import print_function

import functools
import sys
import textwrap
import os
import json
import traceback
import errno

from ..formats.config import (load_config_file, DEFAULT_CONFIG_FILENAME_REPR, DEFAULT_CONFIG_FILENAME,
                              ValidationError)
from ..formats.marked_yaml import ValidationError
from ..core.source_cache import RemoteFetchError

import logging
logger = logging.getLogger()
from hashdist.util.logger_setup import set_log_level, configure_logging, has_error_occurred

try:
    import argparse
except ImportError:
    from ..deps import argparse

#
# sub-command registration
#

_subcommands = {}

def register_subcommand(cls, command=None):
    """Register a subcommand for the ``hit`` command-line tool

    The provided `cls` should provide the following (see :cls:`Help` below
    for an example):

     - ``cls.__doc__`` is used as the help text; the first line is used as
       the one-liner in the command overview
     - ``cls.setup`` should be a function/static method that configures
       the passed-in argument parser
     - ``cls.run`` runs the command
    """
    if command is None:
        name = getattr(cls, 'command', cls.__name__.lower())
    _subcommands[name] = cls
    return cls

class HashDistCommandContext(object):
    def __init__(self, argparser, subcommand_parsers, out_stream, config_filename, env, logger):
        self.argparser = argparser
        self.subcommand_parsers = subcommand_parsers
        self.out_stream = out_stream
        self.env = env
        self.logger = logger
        self._config_filename = config_filename
        self._config = None

    def _ensure_home(self):
        from .manage_store_cli import InitHome
        InitHome.run(self, None)

    def _ensure_config(self):
        if self._config_filename is None and 'HDIST_CONFIG' in self.env:
            self._config = json.loads(env['HDIST_CONFIG'])
        else:
            try:
                config = load_config_file(self._config_filename, self.logger)
            except IOError as e:
                if e.errno == errno.ENOENT:
                    self.logger.info('Unable to find %s, running hit init-home.\n' % self._config_filename)
                    self._ensure_home()
                    config = load_config_file(self._config_filename, self.logger)
                else:
                    raise
        self._config = config

    def get_config(self):
        if self._config is None:
            self._ensure_config()
        return self._config

    def error(self, msg):
        self.argparser.error(msg)

def _parse_docstring(doc):
    # extract help one-liner
    for line in doc.splitlines():
        s = line.strip()
        if s:
            help = s
            break
    assert help
    # make description help text; do some light ReST->terminal for now
    description = textwrap.dedent(doc)
    description = description.replace('::\n', ':\n').replace('``', '"')
    return help, description

def command_line_entry_point(unparsed_argv, env, default_config_filename=None, secondary=False):
    """
    The main ``hit`` command-line entry point

    Arguments:
    ----------

    unparsed_argv : list of str
        The unparsed command line arguments

    env : dict
        Environment

    default_config_filename : unused (TODO)

    secondary : boolean
        Whether this is hit invoking itself. When set, avoids changing
        configuration. This is a bit of a hack and should be done
        better (TODO)
    """
    description = textwrap.dedent('''
    Entry-point for various HashDist command-line tools
    ''')

    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config-file',
                        help='Location of hashdist configuration file (default: %s)'
                        % DEFAULT_CONFIG_FILENAME_REPR,
                        default=DEFAULT_CONFIG_FILENAME)
    parser.add_argument('--ipdb',
                        help='Enable IPython debugging on error',
                        action='store_true')
    parser.add_argument('--log', default=None,
                        help='One of [DEBUG, INFO, ERROR, WARNING, CRITICAL]')

    subparser_group = parser.add_subparsers(title='subcommands')

    subcmd_parsers = {}
    for name, cls in sorted(_subcommands.items()):
        help, description = _parse_docstring(cls.__doc__)
        subcmd_parser = subparser_group.add_parser(
            name=name, help=help, description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter)

        cls.setup(subcmd_parser)
        subcmd_parser.add_argument('-v', '--verbose', action='store_true', help='More verbose output')


        subcmd_parser.set_defaults(subcommand_handler=cls.run, parser=parser,
                                   subcommand=name)
        # Can't find an API to access subparsers through parser? Pass along explicitly in ctx
        # (needed by Help)
        subcmd_parsers[name] = subcmd_parser

    if len(unparsed_argv) == 1:
        # Print help by default rather than an error about too few arguments
        parser.print_help()
        return 1
    args = parser.parse_args(unparsed_argv[1:])

    if not secondary:
        configure_logging(args.log)
        if args.verbose:
            set_log_level('INFO')
            if args.log is not None:
                logger.warn('-v overrides --log to INFO')

    ctx = HashDistCommandContext(parser, subcmd_parsers, sys.stdout, args.config_file, env, logger)

    retcode = args.subcommand_handler(ctx, args)
    if retcode is None:
        retcode = 0
    return retcode


def help_on_exceptions(func, *args, **kw):
    """Present exceptions in the form of a request to file an issue

    Calls func (typically a "main" function), and returns the return code.
    If an exception occurs, then a) if an error is logged to `logger`,
    we just return with 127, or b) otherwise, dump the stack trace and
    then return 127.

    If the 'DEBUG' environment variable is set then the exception is
    raised anyway.
    """
    try:
        debug = len(os.environ['DEBUG']) > 0
    except KeyError:
        debug = logging.getLogger().getEffectiveLevel() <= logging.DEBUG

    if '--ipdb' in sys.argv:
        from ipdb import launch_ipdb_on_exception
        with launch_ipdb_on_exception():
            return func(*args, **kw)

    try:
        return func(*args, **kw)

    except KeyboardInterrupt:
        if debug:
            raise
        else:
            logger.info('Interrupted')
            return 127
    except SystemExit:
        raise
    except ValidationError as e:
        if debug:
            raise
        else:
            logger.critical(str(e))
            return 127
    except IOError as e:
        if debug:
            raise
        else:
            logger.critical(str(e))
            return 127
    except RemoteFetchError as e:
        if debug:
            raise
        else:
            logger.critical("You may wish to check your Internet connection or the remote server")
            return 127
    except:
        if debug:
            raise
        else:
            if not has_error_occurred():
                logger.critical("Uncaught exception:")
                for line in traceback.format_exc().splitlines():
                    logger.critical(line)
                text = """\
                This exception has not been translated to a human-friendly error
                message, please file an issue at
                https://github.com/hashdist/hashdist/issues pasting this
                stack trace.
                """
                text = textwrap.fill(textwrap.dedent(text), width=78)
                logger.info('')
                for line in text.splitlines():
                    logger.critical(line)
            return 127

#
# help command
#

@register_subcommand
class Help(object):
    """
    Displays help about sub-commands
    """
    @staticmethod
    def setup(ap):
        ap.add_argument('command', help='The command to print help for', nargs='?')

    @staticmethod
    def run(ctx, args):
        if args.command is None:
            ctx.subcommand_parsers['help'].print_help()
        else:
            try:
                subcmd_parser = ctx.subcommand_parsers[args.command]
            except KeyError:
                ctx.error('Unknown sub-command: %s' % args.command)
            subcmd_parser.print_help()



if __name__ == '__main__':
    sys.exit(command_line_entry_point(sys.argv, os.environ))
