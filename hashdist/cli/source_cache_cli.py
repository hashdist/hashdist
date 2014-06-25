"""Command-line tools for interacting with the source store
"""

from .main import register_subcommand
import sys

from ..core import archive_types, SourceCache

class FetchGit(object):
    """
    Fetch git sources to the source cache

    Example::

        $ hit fetchgit -p numpy git://github.com/numpy/numpy.git master
        Fetching ...
        Done
        git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3

    One can then unpack results later only by using the keys::

        $ hit unpack git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3 numpy

    The argument to -p is a unique ID for project (since there can be
    several repo URLs for one project), hopefully the need for this
    can be removed in the future, but for now it is mandatory.
    
    """

    @staticmethod
    def setup(ap):
        ap.add_argument('-p', '--project', help='Unique ID for git repository')
        ap.add_argument('repo_url', help='Local or remote path/URL to git repository')
        ap.add_argument('rev', help='Branch/tag/commit to fetch')

    @staticmethod
    def run(ctx, args):
        if args.project is None:
            ctx.error('Must set the --project flag to avoid name collisions.')
        store = SourceCache.create_from_config(ctx.get_config(), ctx.logger)
        key = store.fetch_git(args.repo_url, args.rev, args.project)
        sys.stderr.write('\n')
        sys.stdout.write('%s\n' % key)

register_subcommand(FetchGit)


_archive_types_doc = ', '.join(archive_types)

def as_url(url):
    """Prepends "file:" to ``url`` if it is likely to refer to a local file
    """
    if ':' in url and url.split(':')[0] in ('http', 'https', 'ftp', 'scp', 'file'):
        return url
    else:
        return 'file:' + url

class Fetch(object):
    __doc__ = """
    Fetch an archive to the source cache

    The ``--type`` switch can be used to set the archive type (default
    is to guess by the filename extension). The following archive
    types are supported: %(archive_types)s
    
    """ % dict(archive_types=_archive_types_doc)

    @staticmethod
    def setup(ap):
        ap.add_argument('--type', type=str, help='What kind of archive')
        ap.add_argument('url', help='Local or remote path/URL to archive')
        ap.add_argument('key', nargs='?', help='Expected key of archive')

    @staticmethod
    def run(ctx, args):
        store = SourceCache.create_from_config(ctx.get_config(), ctx.logger)
        # Simple heuristic for whether to prepend file: to url or not;
        # could probably do a better job
        args.url = as_url(args.url)
        key = store.fetch_archive(args.url, args.type)
        sys.stderr.write('\n')
        sys.stdout.write('sources:\n')
        sys.stdout.write('- key: %s\n' % key)
        sys.stdout.write('  url: %s\n' % args.url)
        if args.key and key != args.key:
            sys.stderr.write('Keys did not match\n')
            return 2
        else:
            return 0

register_subcommand(Fetch)

class Unpack(object):
    """
    Unpacks sources that are stored in the source cache to a local directory

    E.g.,

    ::
    
        $ hit unpack targz:mheIiqyFVX61qnGc53ZhR-uqVsY src/python
        $ hit unpack git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3 numpy

    """

    @staticmethod
    def setup(ap):
        ap.add_argument('key', help='Key of stored sources previously returned from a fetch command')
        ap.add_argument('target', help='Where to unpack sources')

    @staticmethod
    def run(ctx, args):
        store = SourceCache.create_from_config(ctx.get_config(), ctx.logger)
        store.unpack(args.key, args.target)

register_subcommand(Unpack)

