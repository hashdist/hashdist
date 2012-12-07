"""Command-line tools for interacting with the source store
"""

from .main import register_subcommand
import argparse
import sys

from ..source_cache import SourceCache

class FetchGit(object):
    """
    Fetch git sources to the source cache

    Example::

        $ hdist fetchgit git://github.com/numpy/numpy.git master
        Fetching ...
        Done
        git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3

    One can then unpack results later only by using the keys::

        $ hdist unpack git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3 numpy
    
    """

    @staticmethod
    def setup(ap):
        ap.add_argument('repository', help='Local or remote path/URL to git repository')
        ap.add_argument('rev', help='Branch/tag/commit to fetch')

    @staticmethod
    def run(ctx, args):
        store = SourceCache.create_from_config(ctx.config)
        key = store.fetch_git(args.repository, args.rev)
        sys.stderr.write('\n')
        sys.stdout.write('%s\n' % key)

register_subcommand(FetchGit)


class Unpack(object):
    """
    Unpacks sources that are stored in the source cache to a local directory

    E.g.,

    ::
    
        $ hdist unpack targz:mheIiqyFVX61qnGc53ZhR-uqVsY src/python
        $ hdist unpack git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3 numpy

    """

    @staticmethod
    def setup(ap):
        ap.add_argument('key', help='Key of stored sources previously returned from a fetch command')
        ap.add_argument('target', help='Where to unpack sources')

    @staticmethod
    def run(ctx, args):
        store = SourceCache.create_from_config(ctx.config)
        store.unpack(args.key, args.target)

register_subcommand(Unpack)

