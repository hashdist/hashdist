Power users' guide to Hashdist
==============================

What follows is a walkthrough of Hashdist with focus on showing off
how components are strung together and other design decisions,
sorted by order of dependency.

Design principles
-----------------

 - Many small components with one-way dependencies, accessible as Python libraries.

 - Protocols between components are designed so that one can imagine
   turning individual components into server applications dealing with
   high loads. However, implementations of those protocols are
   currently kept as simple as possible.

 - All components are accessible through a common ``hdist`` command-line tool.
   This accesses both power-user low-level features and the higher-level
   "varnish", without implying any deep coupling between them (just like `git`).

 - ``hdist`` reads a configuration file ``~/.hashdistconfig`` (by default, everything
   is overridable).


Source store
------------

The idea of the source store is to help download source code from the net,
or "upload" files from the local disk. Items in the store are identified
with a cryptographic hash.

Items in the source store are only needed for a few hours while the
build takes place, and that may be the default configuration for
"desktop users".  However, an advantage of keeping things around
forever is to always be able to redo an old build without relying on
third parties.  This is an aspect that will be very different for
different userbases.

Example ``~/.hashdistconfig``::

    [sources]
        store = ~/.hashdist/source
        keep-transient = 1 week
        keep-targz = forever
        keep-git = forever

Then one can fetch some sources; the last line output (only one to ``stdout``)
is the resulting key::

    $ hdist fetch http://python.org/ftp/python/2.7.3/Python-2.7.3.tar.bz2
    Downloading... progress indicator ...
    Done
    targz:mheIiqyFVX61qnGc53ZhR-uqVsY

    $ hdist fetch git://github.com/numpy/numpy.git master
    Fetching ...
    Done
    git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3

One can then unpack results later only by using the key::

    $ hdist unpack targz:mheIiqyFVX61qnGc53ZhR-uqVsY src/python
    $ hdist unpack git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3 numpy

While ``targz:`` and ``git:`` is part of the key, this is simply to
indicate (mostly to humans) where the sources originally came from,
and not a requirement of the underlying source store implementation.

Note that git source trees are simply identified by their git commits,
not by an additional "repository name" or similar (the simplest
implementation of this is to pull all git objects into the same
local repository).

Re-fetching sources that are in cache already are not downloaded and
results in the same hash::

    $ hdist fetch http://python.org/ftp/python/2.7.3/Python-2.7.3.tar.bz2
    targz:mheIiqyFVX61qnGc53ZhR-uqVsY

It's assumed that the content under the URL will not change (at least by
default). Downloading the same content from a different URL leads to
de-duplication and the registration of an additional URL for that
source.

Finally it's possible to store files from the local filesystem::

    $ hdist fetch /home/dagss/code/fooproject
    dir:lkQYr_eQ13Sra5EYoXTg3c8msXs
    $ hdist fetch -ttransient /home/dagss/code/buildfoo.sh
    file:tMwPj0cxhQVsA1pncZKcwCMgVbU

This simply copies files from local drive (mainly to make sure a copy
is preserved in pristine condition for inspection if a build fails).

**Tags:** The ``-ttransient`` option was used above to tag the
``buildfoo.sh`` script, meaning it's not likely to be important (or is
archived by other systems on local disk) so just keep it for a few
days. In general we have a system of arbitrary tags which one can then
make use of when configuring the GC.


Builder
--------
Assume in ``~/.hashdistrc``::

    [builder]
        store = ~/.hashdist/artifacts

The builder is responsible for executing builds, under the following
conditions:

 * The builder will *not* recurse to build a dependency. All
   software dependencies are assumed to have been built already
   (or be present on the host system).

 * All sources, scripts etc. has been downloaded/uploaded to the
   source store

Invoking a build::

    $ hdist build < buildspec.json
    Not present in store, need to build. Follow log with
    
        tail -f /home/dagss/.hashdist/artifacts/numpy/2.6/_build0/build.log
    
    Done building, artifact name:
    numpy-2.6-Ymm0C_HRoH0HxNM9snC3lvcIkMo

    $ hdist resolve numpy-2.6-Ymm0C_HRoH0HxNM9snC3lvcIkMo
    /home/dagss/.hashdist/artifacts/numpy/2.6/Ymm0C_HRoH0HxNM9snC3lvcIkMo

The build specification may look like this for a build::

    {
        'name' : 'numpy',
        'version' : '1.6',
        'dependencies' : {
             'blas' : 'ATLAS-3.10.0-gijMQibuq39SCBQfy5XoBeMSQKw',
             'gcc' : 'gcc-4.6.3-A8x1ZV5ryXvVGLUwoeP2C01LtsY',
             'python' : 'python-2.7-io-lizHjC4h8z5e2Q00Ag9xUvus',
             'bash' : 'python-4.2.24.1-Z8GcCVzYOOH97n-ZC6qhfQhciCI',
         },
         'sources' : {
             'numpy' : 'git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3',
             'build.sh' : 'file:gijMQibuq39SCBQfy5XoBeMSQKw',
         }
         'command' : ['$bash/bin/bash', 'build.sh'],
         'envvars' : {
             'NUMPYLAPACKTYPE' : 'ATLAS'
         },
         'parameters' : {
             ['this is free-form json', 'build script can parse this information',
              'and use it as it wants']
         }
    }

What happens:

 1. A hash is computed of the contents of the build
    specification. This is simple since all dependencies are given in
    terms of their hash. Then, look up in the store; if found, we
    are done. (Dictionaries are supposed to be unordered and sorted
    prior to hashing.)

 #. Let's assume the artifact doesn't exist. A temporary directory is
    created for the build using ``mkdtemp`` (this is important so that
    there's no races if two people share the store and attempt the same build
    at the same time; the directory is moved atomically to its final location
    after the build).

 #. ``chdir`` to that directory, redirect all output to ``build.log``,
    and store the build spec as ``build.json``.  Unpack the sources
    listed using the equivalent of ``hdist unpack``. The result in
    this case is a ``numpy`` subdirectory with the git checkout, and a
    ``build.sh`` script.

 #. Set environment variables. The keys in the `dependencies` section
    maps to environment variables, so that ``$blas``
    refers to ``/home/dagss/.hashdist/artifacts/ATLAS/3.10.0/gijMQibuq39SCBQfy5XoBeMSQKw``.
    This is the sole purpose of the keys in the `dependencies` section.
    (Build scripts may also choose to parse ``build.json`` too instead of
    relying on the environment.).

 #. Set up a sandbox environment. The sandboxing should be the topic
    of another section.

 #. Execute the command. The command **must** start with a variable
    substitution of one of the dependencies listed. (The bootstrapping
    problem this creates should be treated in another section.)


::
    

    [stacks]
        location = ~/.hashdist/stacks

    [garbage-collection]
