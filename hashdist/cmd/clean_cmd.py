from .main import register_subcommand
from ..core import Builder, SourceCache

class ResetStore(object):
    """
    Resets the entire store to scratch. Must be used with the --force argument.

    Example::

        $ hdist resetstore --force

    """

    @staticmethod
    def setup(ap):
        ap.add_argument('--force', action='store_true', help='Yes, actually do this')
        ap.add_argument('--build', action='store_true', help='Reset the build store')
        ap.add_argument('--source', action='store_true', help='Reset the source cache')

    @staticmethod
    def run(ctx, args):
        if not args.force or not (args.build or args.source):
            ctx.logger.error('Did not use --force flag or did not specify something to reset')
            return 1
        if args.source:
            source_cache = SourceCache.create_from_config(ctx.config)
            source_cache.delete_all()
        if args.build:
            build_store = Builder.create_from_config(ctx.config, ctx.logger)
            build_store.delete_all()

register_subcommand(ResetStore)
