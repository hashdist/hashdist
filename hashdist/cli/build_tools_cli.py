import os
from os.path import join as pjoin
import json

from ..fileutils import silent_makedirs

from .main import register_subcommand

def fetch_parameters_from_json(filename, key):
    with file(filename) as f:
        doc = json.load(f)
    for step in key.split('/'):
        doc = doc[step]
    return doc

class CreateLinks(object):
    """
    Sets up a set of symlinks to the host system. The following
    ``build.json`` would set up links to "ls" and "cp" from the host system::

        {
          ...
          "commands": [["hdist", "create-links"]],
          "parameters" : {
            "links" : [
              {
                "action": "symlink",
                "select": "/bin/cp",
                "prefix": "/",
                "target": "$ARTIFACT"
              }
            ]
          }
        }

    Variables are expanded from the OS environment.
    
    Note: It is a good idea to sort the link target list to make the
    hash more stable.
    """

    command = 'create-links'

    @staticmethod
    def setup(ap):
        ap.add_argument('--key', default="parameters/links",
                        help='key in json file to read (default: "parameters/links")')
        ap.add_argument('input', help='parameter json file')

    @staticmethod
    def run(ctx, args):
        from ..core.links import execute_links_dsl
        
        doc = fetch_parameters_from_json(args.input, args.key)
        execute_links_dsl(doc, os.environ)

register_subcommand(CreateLinks)
