import fnmatch
import os
from os.path import join as pjoin
import sys
import shutil
from pprint import pprint
from .main import register_subcommand, DEFAULT_CONFIG_FILENAME_REPR
import errno

def add_build_args(ap):
    ap.add_argument('-j', metavar='CPUCOUNT', default=1, type=int, help='number of CPU cores to utilize')
    ap.add_argument('-k', metavar='KEEP_BUILD', default="error", type=str,
            help='keep build directory: always, never, error (default: error)')
    ap.add_argument('--debug', action='store_true', help='enter interactive debug mode')

def add_profile_args(ap):
    ap.add_argument('profile', nargs='?', default='default.yaml', help='yaml file describing profile to build (default: default.yaml)')

def add_develop_args(ap):
    ap.add_argument('-l', '--link', default='absolute', help='Link action: one of [absolute, relative, copy] (default: absolute)')

def add_target_args(ap):
    ap.add_argument('target', nargs='?', default='', help='directory to use for build dir (default: profile/package name)')
    ap.add_argument('-f', '--force', action='store_true', help='overwrite output directory')

class ProfileFrontendBase(object):
    def __init__(self, ctx, args):
        from ..spec import Profile, ProfileBuilder, load_profile, TemporarySourceCheckouts
        from ..core import BuildStore, SourceCache
        self.ctx = ctx
        self.args = args
        self.source_cache = SourceCache.create_from_config(ctx.get_config(), ctx.logger)
        self.build_store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
        self.checkouts = TemporarySourceCheckouts(self.source_cache)
        self.profile = load_profile(self.ctx.logger, self.checkouts, args.profile)
        self.builder = ProfileBuilder(self.ctx.logger, self.source_cache, self.build_store, self.profile)

    @classmethod
    def run(cls, ctx, args):
        self = cls(ctx, args)
        try:
            self.profile_builder_action()
        finally:
            self.checkouts.close()

    def build_profile_deps(self):
        ready = self.builder.get_ready_list()
        if len(ready) == 0:
            sys.stdout.write('[Profile dependencies are up to date]\n')
        else:
            while len(ready) != 0:
                self.builder.build(ready[0], self.ctx.get_config(),
                        self.args.j, self.args.k)
                ready = self.builder.get_ready_list()
            sys.stdout.write('[Profile dependency build successful]\n')

    def ensure_target(self, target):
        if os.path.exists(target):
            if self.args.force:
                shutil.rmtree(target)
            else:
                self.ctx.error("%s already exists (use -f to overwrite)" % target)
        os.mkdir(target)

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

        profile_symlink = os.path.basename(self.args.profile)[:-len('.yaml')]
        if self.args.package is not None:
            self.builder.build(self.args.package, self.ctx.get_config(), self.args.j,
                               self.args.k, self.args.debug)
        else:
            ready = self.builder.get_ready_list()
            was_done = len(ready) == 0
            while len(ready) != 0:
                self.builder.build(ready[0], self.ctx.get_config(), self.args.j,
                                   self.args.k, self.args.debug)
                ready = self.builder.get_ready_list()
            artifact_id, artifact_dir = self.builder.build_profile(self.ctx.get_config())
            self.build_store.create_symlink_to_artifact(artifact_id, profile_symlink)
            if was_done:
                sys.stdout.write('Up to date, link at: %s\n' % profile_symlink)
            else:
                while len(ready) != 0:
                    self.builder.build(ready[0], self.ctx.get_config(),
                            self.args.j, self.args.k)
                    ready = self.builder.get_ready_list()
                sys.stdout.write('Profile build successful, link at: %s\n' % profile_symlink)

@register_subcommand
class Develop(ProfileFrontendBase):
    """
    Builds a development profile in the Hashdist YAML profile spec
    format, at the same location as the profile yaml file, but without
    the .yaml suffix.

    Note that Develop uses absolute symlinks by default, but supports
    relative symlinks and copying as well.
    """
    command = 'develop'

    @classmethod
    def setup(cls, ap):
        add_profile_args(ap)
        add_build_args(ap)
        add_target_args(ap)
        add_develop_args(ap)

    def profile_builder_action(self):
        if not self.args.profile.endswith('.yaml'):
            self.ctx.error('profile filename must end with yaml')
        develop_profile = self.args.profile[:-len('.yaml')]
        if self.args.target:
            target = os.path.abspath(self.args.target)
        else:
            target = os.path.abspath(develop_profile)

        self.ensure_target(target)
        self.build_profile_deps()
        self.builder.build_profile_out(target, self.ctx.get_config(), self.args.link, self.args.debug)
        sys.stdout.write('Development profile build %s successful\n' % target)


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
        ap.add_argument('package', help='package to show information about')
        add_target_args(ap)

    def profile_builder_action(self):
        self.ensure_target(self.args.target)
        build_spec = self.builder.get_build_spec(self.args.package)
        self.build_store.prepare_build_dir(self.ctx.get_config(), self.ctx.logger, build_spec, self.args.target)

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

            
class PrintLibs(object):
    """
    Print all dynamic libraries from the given profile.

    Example::

        $ hit print-libs default                # print all .so libraries
        $ hit print-libs default --suffix so    # print all .so libraries
        $ hit print-libs default --suffix dylib # print all .dylib libraries
        $ hit print-libs default --suffix dll   # print all .dll libraries

    """

    command = 'print-libs'

    @staticmethod
    def setup(ap):
        ap.add_argument('profile', help='profile to check')
        ap.add_argument('--suffix', default='so',
                help="library suffix (default 'so')")

    @staticmethod
    def run(ctx, args):
        libs = [os.path.join(dirpath, f)
                for dirpath, dirnames, files in os.walk(args.profile)
                for f in fnmatch.filter(files, "*.%s*" % args.suffix)]
        for lib in libs:
            sys.stdout.write(lib + '\n')
