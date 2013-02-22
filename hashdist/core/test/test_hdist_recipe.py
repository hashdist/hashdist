import os
from os.path import join as pjoin
import sys

from .test_build_store import fixture

from ..hdist_recipe import ensure_hdist_cli_artifact

@fixture()
def test_hdist_cli_artifact(tempdir, sc, bldr, config):
    hit_id, hit_path = ensure_hdist_cli_artifact(bldr, config)
    assert sorted(os.listdir(hit_path)) == ['bin', 'build.json', 'build.log.gz', 'pypkg']
    with file(pjoin(hit_path, 'bin', 'hit')) as f:
        hdist_bin = f.read()
    assert hdist_bin.startswith('#!' + sys.executable)

    # Try to use it
    spec = {
             "name": "foo", "version": "na",
             "dependencies": [{"ref": "hit", "id": "virtual:hit"}],
             "build": {
                "script": [{"hit": ["create-links", "--key=parameters/links", "build.json"]}]
             },
             "parameters": {
               "links": [
                  {"action": "symlink", "target": "$ARTIFACT", "select": "/bin/cp", "prefix": "/"},
                ]
             }
           }
    virtuals = {'virtual:hit': hit_id}
    artifact_id, path = bldr.ensure_present(spec, config, virtuals)
    assert os.path.realpath(pjoin(path, 'bin', 'cp')) == '/bin/cp'

    
