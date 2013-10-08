import os
from os.path import join as pjoin
import sys
import shutil
from pprint import pprint
from .main import register_subcommand, DEFAULT_CONFIG_FILENAME_REPR
import errno

def add_build_args(ap):
    ap.add_argument('-j', metavar='CPUCOUNT', default=1, type=int, help='number of CPU cores to utilize')

def add_profile_args(ap):
    ap.add_argument('-p', '--profile', default='default.yaml', help='yaml file describing profile to build (default: default.yaml)')

class ProfileFrontendBase(object):
    def __init__(self, ctx, args):
        from ..spec import Profile, ProfileBuilder, load_profile, TemporarySourceCheckouts
        from ..core import BuildStore, SourceCache
        self.ctx = ctx
        self.args = args
        self.source_cache = SourceCache.create_from_config(ctx.get_config(), ctx.logger)
        self.build_store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
        self.checkouts = TemporarySourceCheckouts(self.source_cache)
        self.profile = load_profile(self.checkouts, args.profile)
        self.builder = ProfileBuilder(self.ctx.logger, self.source_cache, self.build_store, self.profile)

    @classmethod
    def run(cls, ctx, args):
        self = cls(ctx, args)
        try:
            self.profile_builder_action()
        finally:
            self.checkouts.close()


@register_subcommand
class Build(ProfileFrontendBase):
    """
    Builds a profile in the Hashdist YAML profile spec format, and
    outputs a symlink to the resulting profile at the same location
    as the profile yaml file, but without the .yaml suffix.

    If you provide the package argument to build a single package, the
    profile symlink will NOT be updated.
    """
    command = 'build'

    @classmethod
    def setup(cls, ap):
        add_profile_args(ap)
        add_build_args(ap)
        ap.add_argument('package', nargs='?', help='package to build (default: build all)')

    def profile_builder_action(self):
        from ..core import atomic_symlink

        if not self.args.profile.endswith('.yaml'):
            self.ctx.error('profile filename must end with yaml')

        profile_symlink = self.args.profile[:-len('.yaml')]
        if self.args.package is not None:
            self.builder.build(self.args.package, self.ctx.get_config(), self.args.j)
        else:
            ready = self.builder.get_ready_list()
            was_done = len(ready) == 0
            while len(ready) != 0:
                self.builder.build(ready[0], self.ctx.get_config(), self.args.j)
                ready = self.builder.get_ready_list()
            artifact_id, artifact_dir = self.builder.build_profile(self.ctx.get_config())
            self.build_store.create_symlink_to_artifact(artifact_id, profile_symlink)
            if was_done:
                sys.stdout.write('Up to date, link at: %s\n' % profile_symlink)
            else:
                sys.stdout.write('Profile build successful, link at: %s\n' % profile_symlink)


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
        add_profile_args(ap)

    def profile_builder_action(self):
        report = self.builder.get_status_report()
        report = sorted(report.values())
        for build_spec, is_built in report:
            status = 'OK' if is_built else 'needs build'
            sys.stdout.write('%-50s [%s]\n' % (build_spec.short_artifact_id, status))

@register_subcommand
class Show(ProfileFrontendBase):
    """
    Shows (debug) information for building a profile
    """
    command = 'show'

    @classmethod
    def setup(cls, ap):
        add_profile_args(ap)
        ap.add_argument('subcommand', choices=['buildspec', 'script'])
        ap.add_argument('package', help='package to show information about')

    def profile_builder_action(self):
        if self.args.subcommand == 'buildspec':
            if self.args.package == 'profile':
                spec = self.builder.get_profile_build_spec()
            else:
                spec = self.builder.get_build_spec(self.args.package)
            pprint(spec.doc)
        elif self.args.subcommand == 'script':
            sys.stdout.write(self.builder.get_build_script(self.args.package))
        else:
            raise AssertionError()

@register_subcommand
class BuildDir(ProfileFrontendBase):
    """
    Creates the build directory, ready for build, in a given location, for debugging purposes
    """
    command = 'bdir'

    @classmethod
    def setup(cls, ap):
        add_profile_args(ap)
        ap.add_argument('-f', '--force', action='store_true', help='overwrite output directory')
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

@register_subcommand
class GC(object):
    __doc__ = """
    Perform garbage collection to free up disk space.

    Anything not in use of current profiles will be cleaned out. The list
    of current profiles is kept in a directory of symlinks configured
    in %s.
    """ % DEFAULT_CONFIG_FILENAME_REPR

    @staticmethod
    def setup(ap):
        ap.add_argument('--list', action='store_true', help='Show list of GC roots')

    @staticmethod
    def run(ctx, args):
        from ..core import BuildStore
        if args.list:
            gc_roots_dir = ctx.get_config()['gc_roots']
            # write header to stderr, list to stdout
            sys.stderr.write("List of GC roots:\n")
            for gc_root in os.listdir(gc_roots_dir):
                sys.stdout.write("%s\n" % os.readlink(pjoin(gc_roots_dir, gc_root)))
        else:
            build_store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
            build_store.gc()

class MvCpBase(object):
    @classmethod
    def setup(cls, ap):
        ap.add_argument('source', help='symlink to %s' % cls._action)
        ap.add_argument('target', help='where to %s symlink' % cls._action)

    @classmethod
    def run(cls, ctx, args):
        from ..core import BuildStore
        build_store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
        if os.path.exists(args.target):
            # do this both before and after expanding, because common case is
            # when repeating the same operation, and args.target is a readonly artifact
            sys.stderr.write('Target already exists: %s\n' % args.target)
            return 1
        if os.path.isdir(args.target):
            args.target = pjoin(args.target, os.path.basename(args.source))
        if os.path.exists(args.target):
            sys.stderr.write('Target already exists: %s\n' % args.target)
            return 1

        artifact_id_file = pjoin(args.source, 'id')
        try:
            f = open(artifact_id_file)
        except IOError as e:
            if e.errno == errno.ENOENT:
                sys.stderr.write('Symlink does not point to a Hashdist artifact: %s\n' % args.source)
                return 1
            else:
                raise
        else:
            f = open(artifact_id_file)
            artifact_id = f.read().strip()
        build_store.create_symlink_to_artifact(artifact_id, args.target)
        cls._post_action(ctx, args, build_store)

    @classmethod
    def _post_action(cls, ctx, args, build_store):
        pass


@register_subcommand
class CP(MvCpBase):
    """
    Copies a Hashdist profile symlink while keeping GC references up
    to date.

    You may manually manipulate GC references by modifying the
    gc_roots directory (see configuration file)
    """
    _action = 'copy'

@register_subcommand
class MV(MvCpBase):
    """
    Moves a Hashdist profile symlink while keeping GC references in sync.

    You may manually manipulate GC references by modifying the
    gc_roots directory (see configuration file)
    """
    _action = 'move'

    @classmethod
    def _post_action(cls, ctx, args, build_store):
        build_store.remove_symlink_to_artifact(args.source)

@register_subcommand
class RM(object):
    """
    Removes a Hashdist profile symlink while keeping GC references in sync.

    You may manually manipulate GC references by modifying the
    gc_roots directory (see configuration file).
    """

    @classmethod
    def setup(cls, ap):
        ap.add_argument('what', help='symlink to remove')

    @classmethod
    def run(cls, ctx, args):
        from ..core import BuildStore
        build_store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
        try:
            os.unlink(args.what)
        except:
            raise
        else:
            build_store.remove_symlink_to_artifact(args.what)
