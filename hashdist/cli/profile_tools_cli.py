from .main import register_subcommand
from .utils import fetch_parameters_from_json

@register_subcommand
class CreateProfile(object):
    '''
    Creates a profile (a "prefix directory") from the artifacts given.
    The resulting directory contains ``bin``, ``lib``, etc., and can
    be used in a shell environment by calling ``source < (hdist env
    /path/to/profile)``.

    Profile building happens by reading ``profile.json`` in each of
    the artifacts and following the instructions found there; it can,
    e.g., consist of making a set of symlinks to the artifact in the
    profile. See :mod:`hashdist.core.profile` for more details.

    The arguments to this command comes from a parameter JSON file.
    The following use is typical, a build spec which creates a
    profile::


        {
          ...
          "commands": [["hdist", "create-profile", "--key=parameters/profile", "build.json", "$ARTIFACT"]],
          "parameters" : {
            "profile" : [
              {"id": "zlib/1.2.7/fXHu+8dcqmREfXaz+ixMkh2LQbvIKlHf+rtl5HEfgmU"},
              {"id": "hdf/1.8.10/2ae+FVZnpvbvDYpCkSz4wz3nvp-CNxyD5VGi+e5nKQY",
               "before": ["zlib/1.2.7/fXHu+8dcqmREfXaz+ixMkh2LQbvIKlHf+rtl5HEfgmU"]}
            ]
          }
        }
    

    Note that if artifact A comes "before" artifact B, then B will be installed
    first, and then A, so that A can overwrite the files set up by B (and
    so have the same behaviour as if A was *before* B in PATH).

    Virtual artifacts may be needed in the sub-commands of each
    artifact installation; these are read from the HDIST_VIRTUALS
    environment variable.
    '''
    command = 'create-profile'

    @staticmethod
    def setup(ap):
        ap.add_argument('--key', default="/",
                        help='read a sub-key from json file')
        ap.add_argument('input', help='json parameter file')
        ap.add_argument('target', help='location of resulting profile directory')

    @staticmethod
    def run(ctx, args):
        from ..core import make_profile, BuildStore
        from ..core.run_job import unpack_virtuals_envvar
        virtuals = unpack_virtuals_envvar(ctx.env.get('HDIST_VIRTUALS', ''))
        build_store = BuildStore.create_from_config(ctx.config, ctx.logger)
        doc = fetch_parameters_from_json(args.input, args.key)
        make_profile(ctx.logger, build_store, doc, args.target, virtuals, ctx.config)
