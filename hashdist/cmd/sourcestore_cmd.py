"""Command-line tools for interacting with the source store
"""

from .main import register_subcommand
import argparse


class Fetch(object):
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

    The ``--type`` argument decides how the source is interpreted. E.g.,
    if specifying ``targz`` then the unpack command will extract the sources,
    whereas if one specifies the same file as ``file`` then the unpack command
    will simply copy the archive to the target location. The point of this is
    to make build scripts agnostic to the method of source retrieval used.
    
    """

    @staticmethod
    def setup(ap):
        ap.add_argument('--type', choices=['git', 'targz', 'file', 'dir'],
                        help='type of sources (default: auto-detect), see above')
        ap.add_argument('file-or-url', help='What to put into the source store')
        ap.add_argument('hash', nargs='?')

    @staticmethod
    def run(ctx, args):
        pass

register_subcommand(Fetch)
