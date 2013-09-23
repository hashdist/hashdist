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

        for x in ['ba', 'bld', 'src', 'db', 'cache']:
            os.makedirs(pjoin(store_dir, x))
        sys.stdout.write('Directory %s created.\n' % store_dir)
        shutil.copyfile(get_config_example_filename(), DEFAULT_CONFIG_FILENAME)
        sys.stdout.write('Default configuration file %s written.\n' % DEFAULT_CONFIG_FILENAME)

@register_subcommand
class ClearBuilds(object):
    """
    Resets the build store to scratch, deleting all software ever built in this
    Hashdist setup. Must be used with the --force argument.

    Example::

        $ hit clearbuilds --force

    """

    @staticmethod
    def setup(ap):
        ap.add_argument('--force', action='store_true', help='Yes, actually do this')

    @staticmethod
    def run(ctx, args):
        from ..core import BuildStore
        if not args.force:
            ctx.logger.error('Did not use --force flag')
            return 1
        build_store = BuildStore.create_from_config(ctx.config, ctx.logger)
        build_store.delete_all()

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
        if not args.force:
            ctx.logger.error('Did not use --force flag')
            return 1
        source_cache = SourceCache.create_from_config(ctx.config, ctx.logger)
        source_cache.delete_all()
