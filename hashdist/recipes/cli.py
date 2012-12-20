"""
CLI for a user-defined software stack script
"""

import sys
import argparse
import os

from ..hdist_logging import Logger, DEBUG, INFO

from ..core import InifileConfiguration, BuildStore, SourceCache, DEFAULT_CONFIG_FILENAME
from .recipes import build_recipes

__all__ = ['stack_script_cli']

def stack_script_cli(root_recipe):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',
                        default=os.path.expanduser(DEFAULT_CONFIG_FILENAME),
                        help='location of Hashdist config-file (default: %s))' % DEFAULT_CONFIG_FILENAME)
    parser.add_argument('-k', '--keep', choices=['never', 'always', 'error'], default='error',
                        help='when to keep build directories')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='verbose mode')
    parser.add_argument('command', nargs='?', choices=['status', 'build'], default='status')
    args = parser.parse_args()

    logger = Logger(DEBUG if args.verbose else INFO)
        
    config = InifileConfiguration.create(args.config)
    build_store = BuildStore.create_from_config(config, logger)
    source_cache = SourceCache.create_from_config(config, logger)
    
    sys.stderr.write('Status:\n\n%s\n\n' % root_recipe.format_tree(build_store))
    if build_store.is_present(root_recipe.get_build_spec()):
        sys.stderr.write('Everything up to date!\n')
    else:
        sys.stderr.write('Build needed\n')

    if args.command == 'build':
        build_recipes(build_store, source_cache, [root_recipe], keep_build=args.keep)

    artifact_dir = build_store.resolve(root_recipe.get_artifact_id())

    if artifact_dir:
        sys.stderr.write('Root artifact: %s\n' % artifact_dir)

    
