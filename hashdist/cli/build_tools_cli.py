import os
from os.path import join as pjoin
import json

from .main import register_subcommand
from .utils import fetch_parameters_from_json

from ..core import SourceCache

@register_subcommand
class CreateLinks(object):
    """
    Sets up a set of symlinks to the host system. Works by specifying
    rules in a JSON document, potentially part of another document.
    The following symlinks from ``$ARTIFACT/bin`` to everything in
    ``/bin`` except ``cp``::

        {
          ...
          "commands": [["hdist", "create-links", "--key=parameters/links", "build.json"]],
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
    """

    command = 'create-links'

    @staticmethod
    def setup(ap):
        ap.add_argument('--key', default="/", help='read a sub-key from json file')
        ap.add_argument('input', help='json parameter file')

    @staticmethod
    def run(ctx, args):
        from ..core.links import execute_links_dsl
        
        doc = fetch_parameters_from_json(args.input, args.key)
        execute_links_dsl(doc, ctx.env, logger=ctx.logger)

@register_subcommand
class BuildUnpackSources(object):
    """
    Extracts a set of sources as described in a ``build.json`` spec

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
        from ..core.links import execute_links_dsl
        source_cache = SourceCache.create_from_config(ctx.config, ctx.logger)
        doc = fetch_parameters_from_json(args.input, args.key)
        for source_item in doc:
            key = source_item['key']
            target = source_item.get('target', '.')
            strip = source_item.get('strip', 0)
            source_cache.unpack(key, target, unsafe_mode=True, strip=strip)

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
        ap.add_argument('--key', default="files", help='key to read from json (default: "files")')
        ap.add_argument('--input', default="build.json", help='json parameter file (default: "build.json")')

    @staticmethod
    def run(ctx, args):
        from ..core.build_tools import execute_files_dsl
        doc = fetch_parameters_from_json(args.input, args.key)
        execute_files_dsl(doc, ctx.env)
