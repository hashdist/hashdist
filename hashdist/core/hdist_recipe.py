"""
A recipe for making the ``hdist`` command reliably available in an
environment.
"""

import os
from os.path import join as pjoin
import sys

from .build_store import BuildSpec

HDIST_CLI_ARTIFACT_NAME = "hdist-cli"
HDIST_CLI_ARTIFACT_VERSION = "r0"

def hdist_cli_build_spec(python=None, package=None):
    """Build-spec to creates a 'bin'-dir containing only a launcher
    for the 'hdist' command.

    The recipe simply emits executable files directly to ``$ARTIFACT``,
    without executing commands.

    It is created with the Python interpreter currently running,
    loading the Hashdist package currently running (i.e.,
    independent of any "python" dependency in the build spec).

    Parameters
    ----------

    python : str
        Path to Python interpreter to use (default: ``sys.executable``)

    package : str
        Path to Hashdist package to use (default: deduced from ``__file__``)

    Returns
    -------

    spec : BuildSpec
    
    """
    if python is None:
        python = os.path.realpath(sys.executable)
    if package is None:
        package = os.path.realpath(pjoin(os.path.dirname(__file__), '..', '..', 'hashdist'))

    spec = {
        "name": HDIST_CLI_ARTIFACT_NAME,
        "version": HDIST_CLI_ARTIFACT_VERSION,
        "files": [
            {
                "target": "$ARTIFACT/bin/hdist",
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
        "parameters": {
            "links": [
                {
                  "action": "symlink",
                  "source": package,
                  "target": "$ARTIFACT/pypkg/hashdist"
                }
            ]
        },
        "commands": [
            ["hdist", "create-links", "--key=parameters/links", "build.json"]
        ]
    }
    return BuildSpec(spec)
    
def ensure_hdist_cli_artifact(build_store, source_cache):
    """
    Builds an artifact which executes the 'hdist' command using the current
    Python interpreter and current Hashdist package.

    Note: The current Hashdist package is merely symlinked to, the
    hash of the artifact doesn't mean much. See this as a way for the
    running process to inject a CLI into the build environment.

    In other words, this artifact should almost always be provided
    as a "virtual:hdist", not as a concrete artifact.
    """
    spec = hdist_cli_build_spec()
    return build_store.ensure_present(spec, source_cache)
