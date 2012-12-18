"""
:mod:`hashdist.core.profile` --- Making profiles
================================================

A (software) profile is a "prefix directory", linking together
many build artifacts and making them available under a common
name. The profile directory contains ``bin``, ``lib``, etc.

Build artifacts describe how they should be installed into
profiles.

.. note::

   We use the term "install" for installing an artifact into a
   profile; this may be a full ``make install``-style install, but it
   is recommended to make it as light as possible, for instance by
   doing the ``make install`` against the artifact directory during
   build and use the install phase to set up a set of symlinks
   instead.

``profile.json`` specification
------------------------------

Example::

    {
        "dependencies" : [],
        "commands": [["hdist", "make-symlinks", "install.json"]],
        "parameters": {
            <...free-form JSON data...>
        }
    }


**dependencies**:
    Sets up the environment for running the commands. See
    :mod:`hashdist.core.build_store`.

    This need *not* be the same complete list as those found in
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
from os.path import join as pjoin
import json

def make_profile(build_store, artifacts, target_dir):
    os.path.makedirs(target_dir) # raises error if it exists
    for a_id in artifacts:
        install_artifact_into_profile(build_store, a_id, target_dir)
    # todo: make profile.json

def install_artifact_into_profile(build_store, artifact_id, target_dir):
    artifact_dir = build_store.resolve(artifact_id)
    if artifact_dir is None:
        raise Exception('artifact %s not built' % artifact_id)
    with file(pjoin(artifact_dir, 'install.json')) as f:
        doc = json.load(f)
