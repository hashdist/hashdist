import os
from os.path import join as pjoin
import sys

from .test_build_store import fixture

from ..hdist_recipe import ensure_hdist_cli_artifact

@fixture()
def test_hdist_cli_artifact(tempdir, sc, bldr, config):
    hdist_id, hdist_path = ensure_hdist_cli_artifact(bldr, config)
    assert sorted(os.listdir(hdist_path)) == ['bin', 'build.json', 'build.log.gz', 'pypkg']
    with file(pjoin(hdist_path, 'bin', 'hdist')) as f:
        hdist_bin = f.read()
    assert hdist_bin.startswith('#!' + sys.executable)

    # Try to use it
    spec = {
             "name": "foo", "version": "na",
             "dependencies": [{"ref": "hdist", "id": "virtual:hdist"}],
             "build": {
                "script": [{"hdist": ["create-links", "--key=parameters/links", "build.json"]}]
             },
             "parameters": {
               "links": [
                  {"action": "symlink", "target": "$ARTIFACT", "select": "/bin/cp", "prefix": "/"},
                ]
             }
           }
    virtuals = {'virtual:hdist': hdist_id}
    artifact_id, path = bldr.ensure_present(spec, config, virtuals)
    assert os.path.realpath(pjoin(path, 'bin', 'cp')) == '/bin/cp'

    
