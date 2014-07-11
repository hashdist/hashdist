import sys
import os
from os.path import join as pjoin
import json
from functools import partial

from .main import register_subcommand
from .utils import fetch_parameters_from_json

from ..core import SourceCache, BuildStore

@register_subcommand
class CreateLinks(object):
    """
    Sets up a set of symlinks to the host system. Works by specifying
    rules in a JSON document, potentially part of another document.
    The following symlinks from ``$ARTIFACT/bin`` to everything in
    ``/bin`` except ``cp``::

        {
          ...
          "commands": [{"hit": ["create-links", "--key=parameters/links", "build.json"]}],
          "parameters" : {
            "links" : [
              {
                "action": "exclude",
                "select": "/bin/cp",
              },
              {
                "action": "symlink",
                "select": "/bin/*",
                "prefix": "/",
                "target": "$ARTIFACT"
              }
            ]
          }
        }

    See :mod:`hashdist.core.links` for more information on the rules
    one can use.

    If the 'launcher' action is used, then the 'LAUNCHER' environment
    variable should be set to the launcher binary.
    """

    command = 'create-links'

    @staticmethod
    def setup(ap):
        ap.add_argument('--key', default="/", help='read a sub-key from json file')
        ap.add_argument('input', help='json parameter file')

    @staticmethod
    def run(ctx, args):
        from ..core.links import execute_links_dsl

        launcher = ctx.env.get('LAUNCHER', None)
        doc = fetch_parameters_from_json(args.input, args.key)
        execute_links_dsl(doc, ctx.env, launcher, logger=ctx.logger)

@register_subcommand
class BuildUnpackSources(object):
    """
    Extract a set of sources as described in a ``build.json`` spec.

    Extraction is to  the current directory. Example specification::

        {
            ...
           "sources" : [
               {"key": "git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3"},
               {"key": "tar.bz2:kthlsesw5amq4r2ku5jknydfbiw7lorx",
                "target": "sources", "strip": 1},
               {"key": "files:see4qwsfw4b7q7yucosakve2ftvjvnkw"}
         ],

    The optional ``target`` parameter gives a directory they should be
    extracted to (default: ``"."``). The ``strip``
    parameter (only applies to tarballs) acts like the
    `tar` ``--strip-components`` flag.

    If there are any conflicting files then an error is reported and
    unpacking stops.

    .. warning::

        In the event of a corrupted tarball, unpacking will stop, but
        already extracted contents will not be removed, so one should
        always extract into a temporary directory, and recursively
        remove it if there was a failure.

    """

    command = 'build-unpack-sources'

    @staticmethod
    def setup(ap):
        ap.add_argument('--key', default="sources", help='key to read from json (default: "sources")')
        ap.add_argument('--input', default="build.json", help='json parameter file (default: "build.json")')

    @staticmethod
    def run(ctx, args):
        from ..core.build_store import unpack_sources
        source_cache = SourceCache.create_from_config(ctx.get_config(), ctx.logger)
        doc = fetch_parameters_from_json(args.input, args.key)
        unpack_sources(ctx.logger, source_cache, doc, '.')

@register_subcommand
class BuildWriteFiles(object):
    """
    Writes a set of files inlined in a ``build.json`` spec.

    Example ``build.json``::

        {
            ...
            "files" : [
                {
                    "target": "build.sh",
                    "text": [
                       "set -e",
                       "./configure --prefix=\\"${ARTIFACT}\\"",
                       "make",
                       "make install"
                    ]
                }
            ]
        }

    Embed small text files in-line in the build spec, potentially expanding
    variables within them. This is suitable for configuration files, small
    scripts and so on. For anything more than a hundred lines or so
    you should upload to the source cache and put a ``files:...`` key
    in *sources* instead. Note that a JSON-like object can be provided
    instead of text.

    * **target**: Target filename. Variable substitution is performed,
      so it is possible to put ``$ARTIFACT/filename`` here.

    * **text**: Contents as a list of lines which will be joined with "\\n".

    * **object**: As an alternative to *text*, one can provide an object
      which will be serialized to the file as JSON.

    * **executable**: Whether to set the executable permission bit

    * **expandvars**: Whether to expand variables in the text itself
      (defaults to False)

    Order does not affect hashing. Files will always be encoded in UTF-8.

    """

    command = 'build-write-files'

    @staticmethod
    def setup(ap):
        ap.add_argument('--key', default="/", help='read a sub-key from json')
        ap.add_argument('input', help='json parameter file')

    @staticmethod
    def run(ctx, args):
        from ..core.build_tools import execute_files_dsl
        doc = fetch_parameters_from_json(args.input, args.key)
        execute_files_dsl(doc, ctx.env)

@register_subcommand
class BuildWhitelist(object):
    """
    Prints a whitelist based on artifacts listed in the HDIST_IMPORTS environment
    variable to standard output.
    """
    command = 'build-whitelist'

    @staticmethod
    def setup(ap):
        pass

    @staticmethod
    def run(ctx, args):
        from ..core.build_tools import build_whitelist, get_import_envvar
        artifacts = get_import_envvar(ctx.env)
        build_store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
        sys.stdout.write('%s\n' % pjoin(build_store.get_build_dir(), '**'))
        sys.stdout.write('/tmp/**\n')
        sys.stdout.write('/etc/**\n')
        build_whitelist(build_store, artifacts, sys.stdout)

@register_subcommand
class BuildPostprocess(object):
    """
    Walk through directories to perform the actions given by flags.

    To be used after the build process. Default path is the one
    given by ``$ARTIFACT``.

    --shebang=$technique:

        All scripts (executables starting with #!) are re-wired to
        a) if within a profile, launch the interpreter of the profile,
        b) if not in a profile, launch the interpreter using a relative
        path instead of absolute one to make the artifact relocatable.

        The technique used depends on the value; multiline will use a
        polyglot script fragment to insert a 'multi-line shebang',
        while 'launcher' will use the HashDist 'launcher' tool. The
        latter looks for the path to the 'launcher' artifact in the
        LAUNCHER environment variable.

    --write-protect:

        Remove all 'w' mode bits.

    --relative-rpath:

        Patches the RPATH of all executables to turn them from
        absolute RPATHS to relative RPATHS. The details vary across
        platforms, but the goal is to make the artifact
        relocatable. If relocatability is not supported for the
        platform, the command exists silently.

    --relative-symlinks:

        Rewrites absolute symlinks pointing within the $ARTIFACT
        as relative symlinks, and gives an error on symlinks pointing
        out of the artifact.

    --remove-pkgconfig:

        Remove pkgconfig files as they are not relocatable (at least
        yet)

    --relative-pkgconfig:

       Replace the (absolute) artifact directory in the pc files with
       a ``PACKAGE_DIR`` variable. This variable must then be defined
       using ``pkg-config --define-variable=FOO_DIR=artifact_dir``
       when calling pkg-config later on. Hashstack contains a
       pkg-config wrapper script to do this.

    --relative-sh-script=pattern

        Files that matches 'pattern' will be modified so that
        references to $ARTIFACT will be replaced with a path relative
        from the script location. For instance, use the pattern
        `bin/.*-config` to match config-scripts. Code will be inserted
        at top introducing a hashdist_artifact variable in the script,
        and then references to $ARTIFACT will be

    --check-relocatable

        Complain loudly if the full path ${ARTIFACT} string is found
        anywhere within the artifact.

    --check-ignore=REGEX

        Ignore filenames matching REGEX for the relocatability check
    """
    command = 'build-postprocess'

    @staticmethod
    def setup(ap):
        ap.add_argument('--shebang', choices=['multiline', 'launcher', 'none'], default='none')
        ap.add_argument('--write-protect', action='store_true')
        ap.add_argument('--relative-rpath', action='store_true')
        ap.add_argument('--remove-pkgconfig', action='store_true')
        ap.add_argument('--relative-pkgconfig', action='store_true')
        ap.add_argument('--relative-sh-script', action='append')
        ap.add_argument('--relative-symlinks', action='store_true')
        ap.add_argument('--check-relocatable', action='store_true')
        ap.add_argument('--check-ignore', action='append')
        ap.add_argument('--pyc', action='store_true')
        ap.add_argument('path', nargs='?', help='dir/file to post-process (dirs are handled '
                        'recursively)')

    @staticmethod
    def run(ctx, args):
        from ..core import build_tools
        from ..core import BuildStore
        handlers = []

        if args.shebang == 'launcher':
            try:
                launcher = ctx.env['LAUNCHER']
            except KeyError:
                ctx.logger.error('LAUNCHER environment variable not set')
                raise
            if not os.path.exists(launcher):
                ctx.logger.error('%s does not exist' % launcher)
                raise Exception("%s does not exist" % launcher)
            handlers.append(partial(build_tools.postprocess_launcher_shebangs,
                                    launcher_program=launcher))
        elif args.shebang == 'multiline':
            build_store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
            handlers.append(partial(build_tools.postprocess_multiline_shebang,
                                    build_store))

        if (args.relative_sh_script or args.check_relocatable or
            args.relative_symlinks or args.relative_pkgconfig):
            if 'ARTIFACT' not in ctx.env:
                ctx.logger.error('ARTIFACT environment variable not set')
            artifact_dir = ctx.env['ARTIFACT']

        if args.relative_rpath:
            build_store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
            handlers.append(lambda filename: build_tools.postprocess_rpath(ctx.logger, build_store.artifact_root,
                                                                           ctx.env, filename))

        if args.relative_sh_script:
            handlers.append(lambda filename: build_tools.postprocess_sh_script(ctx.logger,
                                                                               args.relative_sh_script,
                                                                               artifact_dir,
                                                                               filename))

        if args.relative_symlinks:
            handlers.append(lambda filename: build_tools.postprocess_relative_symlinks(ctx.logger, artifact_dir,
                                                                                       filename))

        if args.remove_pkgconfig:
            handlers.append(lambda filename: build_tools.postprocess_remove_pkgconfig(
                ctx.logger, filename))

        if args.relative_pkgconfig:
            handlers.append(lambda filename: build_tools.postprocess_relative_pkgconfig(
                ctx.logger, artifact_dir, filename))

        if args.check_relocatable:
            handlers.append(lambda filename: build_tools.check_relocatable(ctx.logger, args.check_ignore,
                                                                            artifact_dir, filename))

        if args.write_protect:
            handlers.append(build_tools.write_protect)

        if args.path is None:
            try:
                args.path = ctx.env['ARTIFACT']
            except KeyError:
                ctx.logger.error('path not given and ARTIFACT environment variable not set')
                raise

        def apply_handlers(path):
            for handler in handlers:
                handler(path)
                if not os.path.exists(path):
                    return   # handler deleted file

        # we traverse post-order so that write-protection of
        # directories happens very last
        if os.path.isfile(args.path):
            apply_handlers(args.path)
        else:
            for dirpath, dirnames, filenames in os.walk(args.path, topdown=False):
                for filename in filenames:
                    apply_handlers(pjoin(dirpath, filename))
                apply_handlers(dirpath)
