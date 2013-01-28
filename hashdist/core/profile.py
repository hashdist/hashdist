"""
:mod:`hashdist.core.profile` --- Making profiles
================================================

A (software) profile is a "prefix directory", linking together
many build artifacts and making them available under a common
name. The profile directory contains ``bin``, ``lib``, etc.

Build artifacts describe how they should be "installed" into
profiles; often this will consist of making a set of symlinks
into the artifact, but it need not be.

``profile.json`` specification
------------------------------

Example::

    {
      "install": {
        "dependencies": [],
        "env": {}
        "commands": [["hdist", "make-symlinks", "profile.json"]],
        "parameters": {
            <...free-form JSON data...>
        }
      }
    }


**dependencies**, **env**:
    Sets up the environment for running the commands. See
    :mod:`hashdist.core.build_store`.

    The *dependencies* need *not* be the same complete list as those found in
    ``build.json``; only the ones needed to actually do the
    installation into the profile. In the example above where only the
    ``hdist`` tool is used, no dependencies need to be specificed.

**commands**:
    Commands to execute during profile installation.

**parameters**:
    Data that can be parsed by the commands (by opening ``install.json``
    and parsing it).


"""


import os
import errno
from os.path import join as pjoin
import json

from .build_store import shorten_artifact_id
from .common import json_formatting_options
from . import run_job

def make_profile(logger, build_store, artifacts, target_dir, virtuals, cfg):
    """

    Parameters
    ----------
    logger : Logger

    build_store : BuildStore

    artifacts : list of dict(id=..., before=...)
        Lists the artifacts to include together with constraints

    target_dir : str
        Target directory, must be non-existing or entirely empty
    """
    # order artifacts
    artifacts = run_job.stable_topological_sort(artifacts)

    # process artifacts in opposite order; highes prioritized gets to go last
    for artifact in artifacts:
        a_id_desc = shorten_artifact_id(artifact['id'])
        logger.info('Linking %s into %s' % (a_id_desc, target_dir))
        sub_logger = logger.get_sub_logger(a_id_desc)
        install_artifact_into_profile(sub_logger, build_store, artifact['id'], target_dir,
                                      virtuals, cfg)

    # make profile.json
    doc = {'artifacts': artifacts}
    with file(pjoin(target_dir, 'profile.json'), 'w') as f:
        json.dump(doc, f, **json_formatting_options)
        f.write('\n')

def install_artifact_into_profile(logger, build_store, artifact_id, target_dir, virtuals, cfg):
    target_dir = os.path.abspath(target_dir)
    artifact_dir = build_store.resolve(artifact_id)
    if artifact_dir is None:
        raise Exception('artifact %s not available' % artifact_id)
    doc_filename = pjoin(artifact_dir, 'artifact.json')
    if not os.path.exists(doc_filename):
        logger.warning('No artifact.json present, skipping')
    else:
        with file(doc_filename) as f:
            doc = json.load(f)
        job_spec = doc.get("install", None)
        if job_spec:
            env = {}
            env['ARTIFACT'] = artifact_dir
            env['PROFILE'] = os.path.abspath(target_dir)
            run_job.run_job(logger, build_store, job_spec, env, virtuals, artifact_dir, cfg)
        else:
            logger.info('Nothing to do')
