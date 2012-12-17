"""
Execution environment for ``build.json`` and ``install.json``.
"""

import os
from os.path import join as pjoin
import subprocess

from .common import InvalidBuildSpecError

def get_artifact_dependencies_env(build_store, virtuals, dependencies):
    """
    Given the `dependencies` object (see :mod:`hashdist.core.build_store`),
    set up a shell environment.

    Parameters
    ----------

    build_store : BuildStore object
        Build store to look up artifacts in

    virtuals : dict
        Maps virtual artifact IDs (including "virtual:" prefix) to concrete
        artifact IDs.

    dependencies : list of {"ref":ref, "id":id}
        The dependencies to use in the environment

    Returns
    -------

    env : dict
        Environment variables to set containing variables for the dependency
        artifacts
    """
    env = {}
    # Build the environment variables due to dependencies, and complain if
    # any dependency is not built
    for dep in dependencies:
        dep_ref = dep['ref']
        dep_id = dep['id']

        # Resolutions of virtual dependencies should be provided by the user
        # at the time of build
        if dep_id.startswith('virtual:'):
            try:
                dep_id = virtuals[dep_id]
            except KeyError:
                raise ValueError('build spec contained a virtual dependency "%s" that was not '
                                 'provided' % dep_id)

        dep_dir = build_store.resolve(dep_id)
        if dep_dir is None:
            raise InvalidBuildSpecError('Dependency "%s"="%s" not already built, please build it first' %
                                        (dep_ref, dep_id))
        env[dep_ref] = dep_dir
        env['%s_id' % dep_ref] = dep_id
        bin_dir = pjoin(dep_dir, 'bin')
        if os.path.exists(bin_dir):
            if 'PATH' in env:
                env['PATH'] = bin_dir + os.pathsep + env['PATH']
            else:
                env['PATH'] = bin_dir
    return env
    

#def execute_commands(commands, artifact_dependencies, env, cwd, log_to):
    
