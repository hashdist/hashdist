import os
import sys
import shutil
from pprint import pprint
from .main import register_subcommand

class ProfileFrontendBase(object):
    def __init__(self, ctx, args):
        from ..spec import Profile, ProfileBuilder, load_profile
        from ..core import BuildStore, SourceCache
        self.ctx = ctx
        self.args = args
        self.source_cache = SourceCache.create_from_config(ctx.config, ctx.logger)
        self.build_store = BuildStore.create_from_config(ctx.config, ctx.logger)
        self.profile = load_profile(self.source_cache, args.profile)
        self.builder = ProfileBuilder(self.ctx.logger, self.source_cache, self.build_store, self.profile)
        
    @classmethod
    def run(cls, ctx, args):
        cls(ctx, args).profile_builder_action()
    

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
    
    def profile_builder_action(self):
        from ..core import atomic_symlink

        if not self.args.profile.endswith('.yaml'):
            self.ctx.error('profile filename must end with yaml')
        profile_symlink = self.args.profile[:-len('.yaml')]
        if self.args.package is not None:
            self.builder.build(args.package, self.ctx.config)
        else:
            while True:
                ready = self.builder.get_ready_list()
                if len(ready) == 0:
                    break
                self.builder.build(ready[0], self.ctx.config)
            artifact_id, artifact_dir = self.builder.build_profile(self.ctx.config)
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
    
    def profile_builder_action(self):
        report = self.builder.get_status_report()
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
    
    def profile_builder_action(self):
        if self.args.subcommand == 'buildspec':
            pprint(self.builder.get_build_spec(args.package).doc)
        elif self.args.subcommand == 'script':
            sys.stdout.write(self.builder.get_build_script(args.package))
        else:
            raise AssertionError()

@register_subcommand
class BuildDir(ProfileFrontendBase):
    """
    Creates the build directory, ready for build, in a given location, for debugging purposes
    """
    command = 'builddir'

    @classmethod
    def setup(cls, ap):
        ap.add_argument('-f', '--force', action='store_true', help='overwrite output directory')
        ap.add_argument('profile', help='profile yaml file')
        ap.add_argument('package', help='package to show information about')
        ap.add_argument('target', help='directory to use for build dir')

    def profile_builder_action(self):
        if os.path.exists(self.args.target):
            if self.args.force:
                shutil.rmtree(self.args.target)
            else:
                self.ctx.error("%d already exists (use -f to overwrite)")
        os.mkdir(self.args.target)
        build_spec = self.builder.get_build_spec(self.args.package)
        self.build_store.prepare_build_dir(self.source_cache, build_spec, self.args.target)
        
        
