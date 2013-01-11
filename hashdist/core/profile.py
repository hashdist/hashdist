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
from .run_job import pack_virtuals_envvar
from .common import json_formatting_options
from . import run_job

def ensure_empty_existing_dir(d):
    try:
        os.makedirs(d)
    except OSError, e:
        if e.errno == errno.EEXIST:
            if os.listdir(d) != []:
                raise Exception('target directory %s not empty' % target_dir)

def make_profile(logger, build_store, artifacts, target_dir, virtuals):
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
    ensure_empty_existing_dir(target_dir)
    
    # order artifacts
    artifacts = sandbox.stable_topological_sort(artifacts)

    # process artifacts in opposite order; highes prioritized gets to go last
    for artifact in artifacts:
        a_id_desc = shorten_artifact_id(artifact['id'])
        logger.info('Linking %s into %s' % (a_id_desc, target_dir))
        sub_logger = logger.get_sub_logger(a_id_desc)
        install_artifact_into_profile(sub_logger, build_store, artifact['id'], target_dir, virtuals)

    # make profile.json
    doc = {'artifacts': artifacts}
    with file(pjoin(target_dir, 'profile.json'), 'w') as f:
        json.dump(doc, f, **json_formatting_options)
        f.write('\n')

def install_artifact_into_profile(logger, build_store, artifact_id, target_dir, virtuals):
    artifact_dir = build_store.resolve(artifact_id)
    if artifact_dir is None:
        raise Exception('artifact %s not available' % artifact_id)
    doc_filename = pjoin(artifact_dir, 'artifact.json')
    if not os.path.exists(doc_filename):
        logger.warning('No artifact.json present, skipping')
    else:
        with file(doc_filename) as f:
            doc = json.load(f)
        doc = doc.get("install", {})
        script = doc.get('commands', [])
        if script:
            env = dict(doc.get('env', {}))
            env['HDIST_VIRTUALS'] = pack_virtuals_envvar(virtuals)
            env['ARTIFACT'] = artifact_dir
            env['PROFILE'] = os.path.abspath(target_dir)
            dep_env = sandbox.get_artifact_dependencies_env(build_store, virtuals,
                                                            doc.get('dependencies', []))
            env.update(dep_env)
            logger.info('Running command %r' % script)
            sandbox.run_script_in_sandbox(logger, script, env, artifact_dir)
        else:
            logger.info('Nothing to do')
