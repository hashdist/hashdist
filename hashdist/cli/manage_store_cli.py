import sys
import os
import shutil
from os.path import join as pjoin, exists as pexists
from textwrap import dedent

from ..formats.config import DEFAULT_CONFIG_FILENAME_REPR, DEFAULT_CONFIG_FILENAME, get_config_example_filename
from .main import register_subcommand

@register_subcommand
class InitHome(object):
    __doc__ = """
    Initializes the current user's home directory for Hashdist by
    creating the ~/.hashdist directory. Further configuration can then
    by done by modifying %s.
    """ % DEFAULT_CONFIG_FILENAME_REPR
    command = 'init-home'

    @staticmethod
    def setup(ap):
        pass

    @staticmethod
    def run(ctx, args):
        store_dir = os.path.expanduser('~/.hashdist')
        for x in [DEFAULT_CONFIG_FILENAME, store_dir]:
            if pexists(x):
                ctx.logger.error('%s already exists, aborting\n' % x)
                return 2

        for x in ['ba', 'bld', 'src', 'db', 'cache', 'gcroots']:
            os.makedirs(pjoin(store_dir, x))
        sys.stdout.write('Directory %s created.\n' % store_dir)
        shutil.copyfile(get_config_example_filename(), DEFAULT_CONFIG_FILENAME)
        sys.stdout.write('Default configuration file %s written.\n' % DEFAULT_CONFIG_FILENAME)

@register_subcommand
class ClearSources(object):
    """
    Empties the source cache. Must be used with the --force argument.

    Example::

        $ hit clearsource --force

    """

    @staticmethod
    def setup(ap):
        ap.add_argument('--force', action='store_true', help='Yes, actually do this')

    @staticmethod
    def run(ctx, args):
        from ..core import SourceCache
        source_cache = SourceCache.create_from_config(ctx.get_config(), ctx.logger)
        source_cache.delete_all()

@register_subcommand
class Purge(object):
    """
    Removes a build artifact from the build store. The specific artifact ID must be
    given, e.g.::

        $ hit purge python/2qbgsltd4mwz

    Alternatively, to wipe the entire build store::

        $ hit purge --force '*'

    Remember to quote in your shell.
    """

    @staticmethod
    def setup(ap):
        ap.add_argument('artifact_id')
        ap.add_argument('--force', action='store_true', help='Needed to delete more than 1 artifact')

    @staticmethod
    def run(ctx, args):
        from ..core import BuildStore
        store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
        if args.artifact_id == '*':
            if not args.force:
                ctx.logger.error('Did not use --force flag')
                return 1
            store.delete_all()
        else:
            path = store.delete(args.artifact_id)
            if path is None:
                sys.stderr.write('Artifact %s not found\n' % args.artifact_id)
            else:
                sys.stderr.write('Removed directory: %s\n' % path)
