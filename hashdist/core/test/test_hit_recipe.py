import os
from os.path import join as pjoin
import sys
from nose.tools import eq_

from .test_build_store import fixture

from ..hit_recipe import ensure_hit_cli_artifact


@fixture()
def test_hit_cli_artifact(tempdir, sc, bldr, config):
    hit_id, hit_path = ensure_hit_cli_artifact(bldr, config)

    eq_(sorted(os.listdir(hit_path)),
        ['artifact.json', 'bin', 'build.json', 'build.log.gz', 'id', 'pypkg'])
    with file(pjoin(hit_path, 'bin', 'hit')) as f:
        hit_bin = f.read()
    assert hit_bin.startswith('#!' + os.path.realpath(sys.executable))

    # Try to use it
    spec = {
             "name": "foo", "version": "na",
             "dependencies": [{"ref": "hit", "id": "virtual:hit"}],
             "build": {
                "commands": [
                    {"hit": ["create-links", "$in0"],
                     "inputs": [
                         {"json": [
                             {"action": "symlink", "target": "$ARTIFACT", "select": "/bin/cp", "prefix": "/"},
                             ]
                          }
                         ]
                     }
                ]
            },
        }
    virtuals = {'virtual:hit': hit_id}
    artifact_id, path = bldr.ensure_present(spec, config, virtuals)
    assert os.path.realpath(pjoin(path, 'bin', 'cp')) == os.path.realpath('/bin/cp')


