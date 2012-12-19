"""
Execution environment for ``build.json`` and ``install.json``.
"""

import os
from os.path import join as pjoin
import subprocess
from glob import glob

from .common import InvalidBuildSpecError

def get_artifact_dependencies_env(build_store, virtuals, dependencies):
    """
    Sets up an environment for a build spec, given the `dependencies`
    property of the document (see :mod:`hashdist.core.build_store`).

    Parameters
    ----------

    build_store : BuildStore object
        Build store to look up artifacts in

    virtuals : dict
        Maps virtual artifact IDs (including "virtual:" prefix) to concrete
        artifact IDs.

    dependencies : list of dict
        The `dependencies` property of the build spec, see above link.

    Returns
    -------

    env : dict
        Environment variables to set containing variables for the dependency
        artifacts
    """
    # just need something that has the right depth relative to the cache_path to
    # use for os.path.relpath
    prototype_lib_dir = pjoin(build_store.artifact_store_dir,
                              '__name', '__version', '__hash', 'lib')

    env = {}
    # Build the environment variables due to dependencies, and complain if
    # any dependency is not built

    PATH = []
    HDIST_CFLAGS = []
    HDIST_ABS_LDFLAGS = []
    HDIST_REL_LDFLAGS = []
    
    for dep in dependencies:
        if dep['before']:
            raise NotImplementedError('todo: implement topological sort')
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

        if dep_ref is not None:
            env[dep_ref] = dep_dir
            env['%s_id' % dep_ref] = dep_id

        if dep['in_path']:
            bin_dir = pjoin(dep_dir, 'bin')
            if os.path.exists(bin_dir):
                PATH.append(bin_dir)

        if dep['in_hdist_compiler_paths']:
            libdirs = glob(pjoin(dep_dir, 'lib*'))
            if len(libdirs) == 1:
                HDIST_ABS_LDFLAGS.append('-L' + libdirs[0])
                HDIST_ABS_LDFLAGS.append('-Wl,-R,' + libdirs[0])

                relpath = os.path.relpath(libdirs[0], prototype_lib_dir)
                HDIST_REL_LDFLAGS.append('-L' + libdirs[0])
                HDIST_REL_LDFLAGS.append('-Wl,-R,$ORIGIN/' + relpath)
            elif len(libdirs) > 1:
                raise InvalidBuildSpecError('in_hdist_compiler_paths set for artifact %s with '
                                            'more than one library dir (%r)' % (dep_id, libdirs))

            incdir = pjoin(dep_dir, 'include')
            if os.path.exists(incdir):
                HDIST_CFLAGS.append('-I' + incdir)

    env['PATH'] = os.path.pathsep.join(PATH)
    env['HDIST_CFLAGS'] = ' '.join(HDIST_CFLAGS)
    env['HDIST_ABS_LDFLAGS'] = ' '.join(HDIST_ABS_LDFLAGS)
    env['HDIST_REL_LDFLAGS'] = ' '.join(HDIST_REL_LDFLAGS)
    return env
    

#def execute_commands(commands, artifact_dependencies, env, cwd, log_to):
    
