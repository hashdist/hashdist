import sys
import os
from os.path import join as pjoin, exists as pexists
from textwrap import dedent

from .main import register_subcommand

@register_subcommand
class InitHome(object):
    """
    Initializes the current user's home directory for Hashdist by
    creating ~/.hdistconfig configuration file and ~/.hit directory.
    """
    
    @staticmethod
    def setup(ap):
        pass

    @staticmethod
    def run(ctx, args):
        config_file = os.path.expanduser('~/.hdistconfig')
        store_dir = os.path.expanduser('~/.hit')
        for x in [config_file, store_dir]:
            if pexists(x):
                sys.stderr.write('%s already exists, aborting\n' % x)
                return 2

        for x in ['opt', 'bld', 'src', 'db', 'cache']:
            os.makedirs(pjoin(store_dir, x))
        with file(config_file, 'w') as f:
            f.write(dedent("""\
            [global]
            cache = ~/.hit/cache
            db = ~/.hit/db
            
            [sourcecache]
            sources = ~/.hit/src

            [builder]
            build-temp = ~/.hit/bld
            artifacts = ~/.hit/opt
            artifact-dir-pattern = {name}/{shorthash}
            """))

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
