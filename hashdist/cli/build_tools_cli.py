import os
from os.path import join as pjoin
import json

from .main import register_subcommand
from .utils import fetch_parameters_from_json

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
        ap.add_argument('--key', default="",
                        help='read a sub-key from json file')
        ap.add_argument('input', help='json parameter file')

    @staticmethod
    def run(ctx, args):
        from ..core.links import execute_links_dsl
        
        doc = fetch_parameters_from_json(args.input, args.key)
        execute_links_dsl(doc, ctx.env)

register_subcommand(CreateLinks)
