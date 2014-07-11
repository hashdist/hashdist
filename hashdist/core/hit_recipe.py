"""
A recipe for making the ``hit`` command reliably available in an
environment.
"""

import os
from os.path import join as pjoin
import sys

from .build_store import BuildSpec

HIT_CLI_ARTIFACT_NAME = "hit-cli"
HIT_CLI_ARTIFACT_VERSION = "r0"

def hit_cli_build_spec(python=None, package=None):
    """Build-spec to creates a 'bin'-dir containing only a launcher
    for the 'hit' command.

    The recipe simply emits executable files directly to ``$ARTIFACT``,
    without executing commands.

    It is created with the Python interpreter currently running,
    loading the HashDist package currently running (i.e.,
    independent of any "python" dependency in the build spec).

    Parameters
    ----------

    python : str
        Path to Python interpreter to use (default: ``sys.executable``)

    package : str
        Path to HashDist package to use (default: deduced from ``__file__``)

    Returns
    -------

    spec : BuildSpec
    
    """
    if python is None:
        python = os.path.realpath(sys.executable)
    if package is None:
        package = os.path.realpath(pjoin(os.path.dirname(__file__), '..', '..', 'hashdist'))

    spec = {
        "name": HIT_CLI_ARTIFACT_NAME,
        "version": HIT_CLI_ARTIFACT_VERSION,
        "files": [
            {
                "target": "$ARTIFACT/bin/hit",
                "executable": True,
                "expandvars": True,
                "text": [
                    "#!%s" % python,
                    "import sys",
                    "import os",
                    "sys.path.insert(0, os.path.join('$ARTIFACT', 'pypkg'))",
                    "from hashdist.cli.main import main",
                    "sys.exit(main(sys.argv))",
                    ""
                ]
            }
        ],
        "build": {
            "commands": [
                {"hit": ["build-write-files", "--key=files", "build.json"]},
                {"hit": ["create-links", "$in0"],
                 "inputs": [
                     {"json": [{
                         "action": "symlink",
                         "source": package,
                         "target": "$ARTIFACT/pypkg/hashdist"
                         }
                               ]
                    }
                     ]
                 }
                ]
            }
        }
    return BuildSpec(spec)
    
def ensure_hit_cli_artifact(build_store, config):
    """
    Builds an artifact which executes the 'hit' command using the current
    Python interpreter and current HashDist package.

    Note: The current HashDist package is merely symlinked to, the
    hash of the artifact doesn't mean much. See this as a way for the
    running process to inject a CLI into the build environment.

    In other words, this artifact should almost always be provided
    as a "virtual:hit", not as a concrete artifact.
    """
    spec = hit_cli_build_spec()
    return build_store.ensure_present(spec, config)
