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

class BuildSymlinks(object):
    """
    Sets up a set of symlinks to the host system. The following
    ``build.json`` would set up links to "ls" and "cp" from the host system::

        {
          ...
          "commands": [["hdist", "build-symlinks"]],
          "parameters" : {
            "symlinks" : [
              {
                "target": "bin",
                "link-to" : ["/bin/ls", "/bin/cp"]
              },
              <...more target directories here...>
          }
        }

    Note: It is a good idea to sort the link target list to make the
    hash more stable.
    """

    command = 'build-symlinks'

    @staticmethod
    def setup(ap):
        ap.add_argument('--key', default="parameters/symlinks",
                        help='key in json file to read (default: "parameters/symlinks")')
        ap.add_argument('input', nargs='?', help='parameter json file (default: "build.json")')

    @staticmethod
    def run(ctx, args):
        if args.input is None:
            args.input = "build.json"
        doc = fetch_parameters_from_json(args.input, args.key)
        for section in doc:
            target_dir = section['target']
            silent_makedirs(target_dir)
            for link in section['link-to']:
                basename = os.path.basename(link)
                os.symlink(link, pjoin(target_dir, basename))

register_subcommand(BuildSymlinks)
