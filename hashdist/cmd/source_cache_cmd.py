"""Command-line tools for interacting with the source store
"""

from .main import register_subcommand
import argparse
import sys

from ..source_cache import SourceCache

class FetchGit(object):
    """
    Put files in/download files to the source store

    The idea of the source store is to help download source code from
    the net, or "upload" files from the local disk. Items in the store
    are identified with a cryptographic hash.

    Examples::

        $ hdist fetch http://python.org/ftp/python/2.7.3/Python-2.7.3.tar.bz2
        Downloading... progress indicator ...
        Done
        targz:mheIiqyFVX61qnGc53ZhR-uqVsY

        $ hdist fetch git://github.com/numpy/numpy.git master
        Fetching ...
        Done
        git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3

    One can then unpack results later only by using the keys::

        $ hdist unpack targz:mheIiqyFVX61qnGc53ZhR-uqVsY src/python
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
