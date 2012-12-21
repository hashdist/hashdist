Profile specification layer
===========================

Nobody wants to use the core tools directly and copy and paste
artifact IDs (unless they are debugging and developing packages).
This layer is one example of an API that can be used to drive ``hdist
fetch``, ``hdist build`` and ``hdist makeprofile``. Skipping this
layer is encouraged if it makes more sense for your application.

**Included**: The ability to programatically define a desired software
profile/"stack", and automatically download and build the packages
with minimum hassle. Patterns for using the lower-level ``hdist``
command (e.g., standardize on symlink-based artifact profiles).

**Excluded**: Any use of package metadata or a central package
repository to automatically resolve dependencies.  (Some limited use
of metadata to get software versions and so on may still be included.)

This layer can be used in two modes:

 * As an API to help implementing the final UI

 * Directly by power-users who don't mind manually specifying everything
   to great detail

The API will be demonstrated by an example from the latter usecase.

Package class
-------------

At the basic level, we provide utilites that knows how to build packages
and inject dependencies. Under the hood this happens by generating the
necesarry JSON files (including the build setup, which is the hard
part) and calling ``hdist build`` and ``hdist makeprofile``.

.. note::

    This has some overlap with Buildout. We should investigate using the Buildout
    API for the various package builders.

.. warning::

   A lot in the below block is overly simplified in terms of what's required
   for each package to build. Consider it a sketch.


Assume one creates the following "profile-script" where pretty much everything
is done manually:

.. code-block:: python
    
    import hashdist
    from hashdist import package as pkg

    from_host = pkg.UseFromHostPackage(['gcc', 'python', 'bash'])

    ATLAS = pkg.ConfigureMakeInstallPackage('http://downloads.sourceforge.net/project/math-atlas/Stable/3.10.0/atlas3.10.0.tar.bz2',
                                            build_deps=dict(gcc=from_host, bash=from_host))
    numpy = pkg.DistutilsPackage('git://github.com/numpy/numpy.git',
                                 build_deps=dict(python=from_host, gcc=from_host, blas=ATLAS),
                                 run_deps=dict(python=from_host, blas=ATLAS),
                                 ATLAS=ATLAS.path('lib'),
                                 CFLAGS=['-O0', '-g'])
    profile = hashdist.Profile([numpy])
    hashdist.command_line(profile)

Everything here is *lazy* (one instantiates *descriptors* of packages
only); each package object is immutable and just stores information
about what it is and describes the dependency DAG. E.g.,
``ATLAS.path('lib')`` doesn't actually resolve any paths, it just
returns a symbolic object which during the build will be able to
resolve the path.

Running the script produces a command-line with several options, a typical run
would be::

    python theprofilescript.py update ~/mystack

This:

 #. Walks the dependency DAG and for each component generates a ``build.json``
    and calls ``hdist build``, often hitting the cache
 #. Builds a profile and does ``ln -sf`` to atomically update ``~/mystack`` (which
    is a symlink).

Package repositories
--------------------

Given the above it makes sense to then make APIs which are essentially
package object factories, and which are aware of various package
sources. Like before, everything should be lazy/descriptive. Sketch:

.. code-block:: python
    
    import hashdist
    
    # the package environment has a list of sources to consider for packages;
    # which will be searched in the order provided
    env = hashdist.PackageEnvironment(sources=[
        hashdist.SystemPackageProvider('system'),
        hashdist.SpkgPackageProvider('qsnake', '/home/dagss/qsnake/spkgs'),
        hashdist.PyPIPackageProvider('pypi', 'http://pypi.python.org')
    ])

    # The environment also stores default arguments. env is immutable, so we
    # modify by making a copy
    env = env.copy_with(CFLAGS=['-O0', '-g'])

    # Set up some compilers; insist that they are found on the 'system' source
    # (do not build them)
    intel = env.pkgs.intel_compilers(from='system')
    gcc = env.pkgs.gnu_compilers(from='system')

    # env.pkgs.__getattr__ "instantiates" software. The result is simply a symbolic
    # node in a build dependency graph; nothing is resolved until an actual build
    # is invoked
    blas = env.pkgs.reference_blas(compiler=intel)
    # or: blas = env.pkgs.ATLAS(version='3.8.4', compiler=intel)
    # or: blas = env.pkgs.ATLAS(version='3.8.4', from='system',
    #                           libpath='/sysadmins/stupid/path/for/ATLAS')

    python = env.pkgs.python()
    petsc = env.pkgs.petsc(from='qsnake', blas=blas, compiler=intel)
    petsc4py = env.pkgs.petsc4py(from='qsnake', petsc=petsc, compiler=gcc, python=python)
    numpy = env.pkgs.numpy(python=python, blas=blas, compiler=intel, CFLAGS='-O2')
    jinja2 = env.pkgs.jinja2(python=python)
    
    profile = hashdist.profile([python, petsc, numpy, jinja2])
    hashdist.command_line(profile)

