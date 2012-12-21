"""Main entry-point

Other ``hashdist.cmd.*`` modules register their sub-commands using the
:func:`subcommand` and :func:`subcommand_args` decorators.
"""

import functools
import argparse
import sys
import textwrap
import os

        
from ..core import InifileConfiguration, DEFAULT_CONFIG_FILENAME
from ..hdist_logging import Logger, DEBUG, INFO

#
# sub-command registration
#

_subcommands = {}

def register_subcommand(cls, command=None):
    """Register a subcommand for the ``hdist`` command-line tool

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

class HashdistCommandContext(object):
    def __init__(self, argparser, subcommand_parsers, out_stream, config, env, logger):
        self.argparser = argparser
        self.subcommand_parsers = subcommand_parsers
        self.out_stream = out_stream
        self.config = config
        self.env = env
        self.logger = logger

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

def main(unparsed_argv, env, logger=None):
    """The main ``hdist`` command-line entry point
    """

    description = textwrap.dedent('''
    Entry-point for various Hashdist command-line tools
    ''')

    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config-file',
                        help='Location of hashdist configuration file (default: %s)' % DEFAULT_CONFIG_FILENAME,
                        default=os.path.expanduser(DEFAULT_CONFIG_FILENAME))
    subparser_group = parser.add_subparsers(title='subcommands')

    subcmd_parsers = {}
    for name, cls in sorted(_subcommands.items()):
        help, description = _parse_docstring(cls.__doc__)
        subcmd_parser = subparser_group.add_parser(
            name=name, help=help, description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter)

        cls.setup(subcmd_parser)
        
        subcmd_parser.set_defaults(subcommand_handler=cls.run, parser=parser)
        # Can't find an API to access subparsers through parser? Pass along explicitly in ctx
        # (needed by Help)
        subcmd_parsers[name] = subcmd_parser

    if len(unparsed_argv) == 1:
        # Print help by default rather than an error about too few arguments
        parser.print_help()
    else:
        args = parser.parse_args(unparsed_argv[1:])

        if logger is None:
            logger = Logger(DEBUG)
        config = InifileConfiguration.create(args.config_file)
        ctx = HashdistCommandContext(parser, subcmd_parsers, sys.stdout, config, env, logger)

        retcode = args.subcommand_handler(ctx, args)
        if retcode is None:
            retcode = 0

    return retcode

#
# help command
#

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

register_subcommand(Help)


if __name__ == '__main__':
    sys.exit(main(sys.argv, os.environ))
