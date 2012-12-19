from .main import register_subcommand
from ..core import BuildStore, SourceCache

@register_subcommand
class CleanBuilds(object):
    """
    Resets the build store to scratch, deleting all software ever built in this
    Hashdist setup. Must be used with the --force argument.

    Example::

        $ hdist cleanbuilds --force

    """

    @staticmethod
    def setup(ap):
        ap.add_argument('--force', action='store_true', help='Yes, actually do this')

    @staticmethod
    def run(ctx, args):
        if not args.force:
            ctx.logger.error('Did not use --force flag')
            return 1
        build_store = BuildStore.create_from_config(ctx.config, ctx.logger)
        build_store.delete_all()

@register_subcommand
class CleanSources(object):
    """
    Empties the source cache. Must be used with the --force argument.

    Example::

        $ hdist cleansource --force

    """

    @staticmethod
    def setup(ap):
        ap.add_argument('--force', action='store_true', help='Yes, actually do this')

    @staticmethod
    def run(ctx, args):
        if not args.force:
            ctx.logger.error('Did not use --force flag')
            return 1
        source_cache = SourceCache.create_from_config(ctx.config, ctx.logger)
        source_cache.delete_all()
