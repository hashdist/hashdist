"""
CLI for a user-defined software stack script
"""

import sys
import argparse
import os
import tempfile

from ..hdist_logging import Logger, DEBUG, INFO

from ..core import (InifileConfiguration, BuildStore, SourceCache, DEFAULT_CONFIG_FILENAME,
                    DiskCache)
from .recipes import build_recipes

__all__ = ['stack_script_cli']

def stack_script_cli(root_recipe):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',
                        default=os.path.expanduser(DEFAULT_CONFIG_FILENAME),
                        help='location of Hashdist config-file (default: %s))' % DEFAULT_CONFIG_FILENAME)
    parser.add_argument('-k', '--keep-always', action='store_true',
                        help='keep build directory even if there is no error')
    parser.add_argument('-K', '--keep-never', action='store_true',
                        help='never keep build directory, even if there is an error')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='verbose mode')
    parser.add_argument('-s', '--status', action='store_true',
                        help='do not run build, only show status')
    parser.add_argument('target', nargs='?',
                        help='name of symlink that should be created to results')
    args = parser.parse_args()

    if args.keep_always and args.keep_never:
        parser.error('-k and -K are incompatible')
    elif args.keep_always:
        args.keep = 'always'
    elif args.keep_never:
        args.keep = 'never'
    else:
        args.keep = 'error'

    if args.target and os.path.exists(args.target) and not os.path.islink(args.target):
        parser.error('"%s" exists and is not a symlink')
    logger = Logger(DEBUG if args.verbose else INFO)
        
    config = InifileConfiguration.create(args.config)
    build_store = BuildStore.create_from_config(config, logger)
    source_cache = SourceCache.create_from_config(config, logger)
    cache = DiskCache.create_from_config(config, logger)

    root_recipe.initialize(logger, cache)
    sys.stderr.write('Status:\n\n%s\n\n' % root_recipe.format_tree(build_store))
    if build_store.is_present(root_recipe.get_build_spec()):
        sys.stderr.write('Everything up to date!\n')
    else:
        sys.stderr.write('Build needed\n')

    if not args.status:
        build_recipes(build_store, source_cache, [root_recipe], keep_build=args.keep)

    artifact_dir = build_store.resolve(root_recipe.get_artifact_id())
    if not artifact_dir:
        if args.target:
            logger.warning('Not updating symlink "%s" since build is not up to date' % args.target)
        return

    if args.target:
        # create-&-rename in order to force-create symlink
        templink = args.target + '-temp-%d' % os.getpid()
        os.symlink(artifact_dir, templink)
        try:
            os.rename(templink, args.target)
        except:
            os.unlink(templink)
            raise
        logger.info('Created "%s" -> "%s"' % (args.target, artifact_dir))
    else:
        logger.info('Results in "%s"' % artifact_dir)
        

    
