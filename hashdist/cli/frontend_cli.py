import os
import sys
from pprint import pprint
from .main import register_subcommand

class ProfileFrontendBase(object):
    @classmethod
    def run(cls, ctx, args):
        from ..spec import Profile, ProfileBuilder, load_profile
        from ..core import BuildStore, SourceCache

        source_cache = SourceCache.create_from_config(ctx.config, ctx.logger)
        build_store = BuildStore.create_from_config(ctx.config, ctx.logger)
        profile = load_profile(source_cache, args.profile)
        builder = ProfileBuilder(ctx.logger, source_cache, build_store, profile)

        cls.profile_builder_action(ctx, builder, args)
    

@register_subcommand
class Build(ProfileFrontendBase):
    """
    Builds a profile in the Hashdist YAML profile spec format, and
    outputs a symlink to the resulting profile at the same location
    without the .yaml suffix.

    If you provide the package argument to build a single package, the
    profile symlink will NOT be updated.
    """
    command = 'build'

    @classmethod
    def setup(cls, ap):
        ap.add_argument('profile', help='profile yaml file')
        ap.add_argument('package', nargs='?', help='package to build (default: build all)')
    
    @classmethod
    def profile_builder_action(cls, ctx, builder, args):
        from ..core import atomic_symlink

        if not args.profile.endswith('.yaml'):
            ctx.error('profile filename must end with yaml')
        profile_symlink = args.profile[:-len('.yaml')]
        if args.package is not None:
            builder.build(args.package, ctx.config)
        else:
            while True:
                ready = builder.get_ready_list()
                if len(ready) == 0:
                    break
                builder.build(ready[0], ctx.config)
            artifact_id, artifact_dir = builder.build_profile(ctx.config)
            atomic_symlink(artifact_dir, profile_symlink)
        
            
@register_subcommand
class Status(ProfileFrontendBase):
    """
    Status a profile in the Hashdist YAML profile spec format, and
    outputs a symlink to the resulting profile at the same location
    without the .yaml suffix.
    """
    command = 'status'

    @classmethod
    def setup(cls, ap):
        ap.add_argument('profile', help='profile yaml file')
    
    @classmethod
    def profile_builder_action(cls, ctx, builder, args):
        report = builder.get_status_report()
        report = sorted(report.values())
        for name, is_built in report:
            short_name = name[:name.index('/') + 6] + '..'
            status = 'OK' if is_built else 'needs build'
            sys.stdout.write('%-50s [%s]\n' % (short_name, status))
        
@register_subcommand
class Show(ProfileFrontendBase):
    """
    Shows (debug) information for building a profile
    """
    command = 'show'

    @classmethod
    def setup(cls, ap):
        ap.add_argument('subcommand', choices=['buildspec', 'script'])
        ap.add_argument('profile', help='profile yaml file')
        ap.add_argument('package', help='package to show information about')
    
    @classmethod
    def profile_builder_action(cls, ctx, builder, args):
        if args.subcommand == 'buildspec':
            pprint(builder.get_build_spec(args.package).doc)
        elif args.subcommand == 'script':
            sys.stdout.write(builder.get_build_script(args.package))
        else:
            raise AssertionError()
