Build specifications and artifacts
==================================

The build spec (``build.json``)
-------------------------------

The heart of HashDist are *build specs*, JSON documents that describes
everything that goes into a build: the source code to use, the build
environment, the build commands.

A *build artifact* is the result of executing the instruction in the
build spec. The *build store* is the collection of locally available
build artifacts.

The way the build store is queried is by using build specs as
keys to look up software. E.g., take the
following ``build.json``::

    {
        "name": "zlib",
        "sources": [
            {"key": "tar.gz:7kojzbry564mxdxv4toviu7ekv2r4hct", "target": ".", "strip": 1}
        ],
        "build": {
            "import": [
                {"ref": "UNIX", "id": "virtual:unix"},
                {"ref": "GCC", "id": gcc/gxuzlqihu4ok5obtxm5xt6pvi6a3gp5b"},
            ],
            "commands": [
                {"cmd": ["./configure", "--prefix=$ARTIFACT"]},
                {"cmd": ["make", "install"]}
            ]
        }
    }

The *artifact ID* derived from this build specification is::

    $ hit hash build.json
    zlib/d4jwf2sb2g6glprsdqfdpcracwpzujwq

Let us check if it is already in the build store::

    $ hit resolve build.json
    (not built)

::

    $ hit resolve -h zlib/d4jwf2sb2g6glprsdqfdpcracwpzujwq
    (not built)

In the future, we hope to make it possible to automatically download
build artifacts that are not already built. For now, building from
source is the only option, so let's do that::

    $ hit build -v build.json
    ...<output>...
    /home/dagss/.hdist/opt/zlib/d4jw

The last line is the location of the corresponding *build artifact*,
which can from this point of be looked up by the either the build spec
or the hash::

    $ hit resolve build.json
    /home/dagss/.hdist/opt/zlib/d4jw
    
::

    $ hit resolve -h zlib/d4jwf2sb2g6glprsdqfdpcracwpzujwq
    /home/dagss/.hdist/opt/zlib/d4jw


.. note::

    Note that the intention is not that end-users write ``build.json``
    files themselves; they are simply the *API for the build artifact
    store*. It is the responsibility of distributions such as
    *python-hpcmp* to properly generate build specifications for
    HashDist in a user-friendly manner.


Build artifacts
---------------

A build artifact contains the result of a build; usually as a
prefix-style directory containing one library/program only, i.e.,
typical subdirectories are ``bin``, ``include``, ``lib`` and so on.
The build artifact should ideally be in a relocatable form that can
be moved around or packed and distributed to another computer (see
:doc:`building`), although HashDist does not enforce this.

A HashDist artifact ID has the form ``name/hash``, e.g.,
``zlib/4niostz3iktlg67najtxuwwgss5vl6k4``. For the artifact paths on
disk, a shortened form (4-char hash) is used to make things more
friendly to the human user. If there is a collision, the length is
simply increased for the one that comes later (see also :ref:`build-spec-discussion`).

Some information is present in every build artifact:

``build.log.gz``:
    The log from performing the build.


``build.json``:
    The input build spec.

``artifact.json``:
    Metadata about the build artifact itself. Some of this is simply
    copied over from ``build.json``; however, this is a separate file
    because parts of it could be generated as part of the build
    process. This is important during **Profile generation** (docs TBD).



Build spec spec
---------------

The build spec document has the following top-level fields:

**name**:
    Used as the prefix in the artifact ID. Should match ``[a-zA-Z0-9-_+]+``.

**version**:
    (Currently not used, but will become important for
    virtual build artifacts). Should match ``[a-zA-Z0-9-_+]*``.

**build**:
    A *job* to run to perform the build. See :mod:`hashdist.core.run_job`
    for the documentation of this sub-document.

**sources**:
    Sources listed are unpacked to build directory;
    documentation for now in 'hit unpack-sources'

**profile_install**:
    Copied to `$ARTIFACT/artifact.json` before the build.

**import_modify_env**:
    Copied to `$ARTIFACT/artifact.json` before the build.


The build environment
---------------------

See :mod:`hashdist.core.execute_job` for information about how the
build job is executed. In addition, the following environment variables
are set:

**BUILD**:
    Set to the build directory. This is also the starting `cwd` of
    each build command. This directory may be removed after the build.

**ARTIFACT**:
    The location of the final artifact. Usually this is the "install location"
    and should, e.g., be passed as the ``--prefix`` to ``./configure``-style
    scripts.

The build specification is available under ``$BUILD/build.json``, and
stdout and stderr are redirected to ``$BUILD/build.log``. These two
files will also be present in ``$ARTIFACT`` after the build.


.. _build-spec-discussion:

Discussion
----------

Safety of the shortened IDs
'''''''''''''''''''''''''''

HashDist will never use these to resolve build artifacts, so collision
problems come in two forms:

First, automatically finding the list of run-time dependencies from
the build dependencies. In this case one scans the artifact directory
only for the build dependencies (less than hundred). It then makes
sense to consider the chance of finding one exact string
``aaa/0.0/ZXa3`` in a random stream of 8-bit bytes, which helps
collision strength a lot, with chance "per byte" of
collision on the order :math:`2^{-(8 \cdot 12)}=2^{-96}`
for this minimal example.

If this is deemed a problem (the above is too optimistice), one can
also scan for "duplicates" (other artifacts where longer hashes
were chosen, since we know these).

The other problem can be future support for binary distribution of
build artifacts, where you get pre-built artifacts which have links to
other artifacts embedded, and artifacts from multiple sources may
collide. In this case it makes sense to increase the hash lengths a
bit since the birthday effect comes into play and since one only has 6
bits per byte. However, the downloaded builds presumably will contain
the full IDs, and so on can check if there is a conflict and give an
explicit error.

