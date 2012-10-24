.. highlight:: python

Profile specification layer
===========================

Nobody wants to use the core tools directly and copy and paste
artifact IDs (unless they are debugging and developing packages).
This layer is one example of an API that can be used to drive ``hdist
fetch``, ``hdist build`` and ``hdist makeprofile``. Skipping this
layer is encouraged if it makes more sense for your application.

**Included**: The ability to programatically define a desired software profile/"stack",
and automatically download and build the packages with minimum hassle.

**Excluded**: Any use of package metadata or a central package
repository to automatically resolve dependencies.  (Some limited use
of metadata to get software versions and so on may still be included.)

This layer can be used in two modes:

 * As an API to help implementing the final UI

 * Directly by power-users who don't mind manually specifying everything
   to great detail

The API will be demonstrated by an example from the latter usecase

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
    hashdist.command_line(profile, distro_dir='/home/dagss/qsnake')

