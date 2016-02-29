"""Helpers to reduce the repetitive work of creating e.g. a pypi package.

Example usage:

hit skeleton-pypi Django

Note that pypi is case sensitive.
"""
import json
import os
import ssl
import urllib2

from .main import register_subcommand
from ..core import SourceCache


PACKAGE_TEMPLATE = """\
extends: [setuptools_package]

dependencies:
  build: [{build_dependencies}]
  run: [{run_dependencies}]

sources:
 - key: {key}
   url: {url}
"""

@register_subcommand
class SkeletonPypi(object):
    """
    Fetches a pypi package and creates a yaml package for it.

    Example:

    hit skeleton-pypi Django

    This will create ./pkgs/Django.yaml from the pypi package.  By
    default this command will refuse to override an existing file.

    Note that while pypi packages support specifying dependencies, they
    are almost always missing; you have to add dependencies manually.
    """
    command = 'skeleton-pypi'

    @staticmethod
    def setup(ap):
        ap.add_argument('project', help='name of the pipy project')
        ap.add_argument(
            '--overwrite-existing', default=False, action='store_true',
            help='Replace an existing yaml file.'
        )
        ap.add_argument(
            '-N', '--no-check-certificate', default=False, action='store_true',
            help='Skip SSL certification verification for downloading over HTTPS.'
        )

    @staticmethod
    def run(ctx, args):
        c = ssl.create_default_context()
        if args.no_check_certificate:
            # Skip SSL certificate verification
            c.check_hostname = False
            c.verify_mode = ssl.CERT_NONE
        try:
            response = urllib2.urlopen(
                'https://pypi.python.org/pypi/{}/json'.format(args.project),
                context=c)
        except IOError as e:
            ctx.logger.error('Error retrieving metadata: %s', e)
            return 2

        try:
            metadata = json.load(response)
        except ValueError as e:
            ctx.logger.error('Could not load pypi json  metadata: %s', e)
            return 2

        dest_path = os.path.join('.', 'pkgs', '{}.yaml'.format(args.project))
        try:
            os.makedirs('pkgs')
        except os.error:
            pass

        if os.path.exists(dest_path) and not args.overwrite_existing:
            ctx.logger.error(
                'Package already exists: %s. '
                'Use --overwrite-existing to overwrite.', dest_path)
            return 2

        store = SourceCache.create_from_config(ctx.get_config(), ctx.logger)

        # todo: -1 is probably not the correct way to get the latest version?
        try:
            archive_url = [
                x['url'] for x in metadata['urls'] if x['packagetype'] == 'sdist'
            ][-1]
        except IndexError:
            ctx.logger.error('Could not find sdist distribution in URLs.')
            return 2

        key = store.fetch_archive(archive_url,
                no_check_certificate=args.no_check_certificate)

        # todo - discover build dependencies
        build_dependencies = []
        run_dependencies = []

        with open(dest_path, 'w') as yaml_file:
            yaml_file.write(PACKAGE_TEMPLATE.format(
                build_dependencies=', '.join(build_dependencies),
                run_dependencies=', '.join(run_dependencies),
                url=archive_url,
                key=key,
            ))

        ctx.logger.info('Succesfully created %s', dest_path)
        ctx.logger.info('Please check build and run dependencies.')
        return 0
