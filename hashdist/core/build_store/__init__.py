"""
:mod:`hashdist.core.build_store` --- Build artifact store
=========================================================

Principles
----------

The build store is the very core of Hashdist: Producing build artifacts
identified by hash-IDs. It's important to have a clear picture of just
what the build store is responsible for and not.

Nix takes a pure approach where an artifact hash is guaranteed to
identify the resulting binaries (up to anything inherently random in
the build process, like garbage left by compilers). In contrast,
Hashdist takes a much more lenient approach where the strictness is
configurable. The primary goal of Hashdist is to make life simpler
by reliably triggering rebuilds when software components are updated,
not total control of the environment (in which case Nix is likely
the better option).

The *only* concern of the build store is managing the result of a
build.  So the declared dependencies in the build-spec are not the
same as "package dependencies" found in higher-level distributions;
for instance, if a pure Python package has a NumPy dependency, this
should not be declared in the build-spec because NumPy is not needed
during the build; indeed, the installation can happen in
parallel. Assembing artifacts together in a usable run-time system is
the job of :mod:`hashdist.core.profile`.


Artifact IDs
------------

A Hashdist artifact ID has the form ``name/version/hash``, e.g.,
``zlib/1.2.7/fXHu+8dcqmREfXaz+ixMkh2LQbvIKlHf+rtl5HEfgmU``.

 * `name` is a descriptive name for the package
 * `version` describes the specific build in human-friendly terms;
   this may be a simple version number (``1.2``) or something
   more descriptive (``1.2-beta-intel-openblas-avx``). For simplicity
   we require this to always be present; by convention set it to ``n`` for
   "does not apply" or ``dev`` for "not released yet".
 * `hash` is a secure sha-256 hash of the build specification (43 characters)

All explicit references to build artifacts happens by using the full
three-part ID.

For the artifact paths on disk, a shortened form (4-char hash) is used
to make things more friendly to the human user. If there is a
collision, the length is simply increased for the one that comes
later. Thus, the example above could be stored on disk as
``~/.hdist/opt/zlib/1.2.7/fXHu``, or ``~/.hdist/opt/zlib/1.2.7/fXHu+``
in the (rather unlikely) case of a collision. There is a symlink
from the full ID to the shortened form. See also Discussion below.

Build specifications and inferring artifact IDs
-----------------------------------------------

The fundamental object of the build store is the JSON build
specification.  If you know the build spec, you know the artifact ID,
since the former is the hash of the latter. The key is that both
`dependencies` and `sources` are specified in terms of their hashes.

An example build spec:

.. code-block:: python
    
    {
        "name" : "<name of piece of software>",
        "version" : "<human-readable description what makes this build special>",
        "dependencies" : [
            {"ref": "bash", "id": "virtual:bash"},
            {"ref": "make", "id": "virtual:gnu-make/3+"},
            {"ref": "gcc", "id": "zlib/1.2.7/fXHu+8dcqmREfXaz+ixMkh2LQbvIKlHf+rtl5HEfgmU"},
            {"ref": "unix", "id": "virtual:unix"},
            {"ref": "zlib", "id": "gcc/host-4.6.3/q0VSL7JmzH1P17meqITYc4kMbnIjIexrWPdlAlqPn3s"},
         ],
         "sources" : [
             {"key": "git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3"},
             {"key": "tar.bz2:RB1JbykVljxdvL07mN60y9V9BVCruWRky2FpK2QCCow", "target": "sources", "strip": 1},
             {"key": "files:5fcANXHsmjPpukSffBZF913JEnMwzcCoysn-RZEX7cM"}
         ],
         "files" : [
             { "target": "build.sh",
               "contents": [
                 "set -e",
                 "./configure --prefix=\\"${TARGET}\\"",
                 "make",
                 "make install"
               ]
             }
         ],
         "commands" : [["bash", "build.sh"]],
    }

The build environment
---------------------

The build environment is totally clean except for what is documented here.
``$PATH`` is reset as discussed in the next section.

The build starts in a temporary directory ``$BUILD`` with *sources*
and *files* unpacked into it, and should result in something being
copied/installed to ``$TARGET``. The build specification is available
under ``$BUILD/build.json``, and output redirected to
``$BUILD/build.log``; these two files will also be present in
``$TARGET`` after the build.


Build specification fields
--------------------------

**name**:
    See previous section

**version**:
    See previous section

**dependencies**:
    The dependencies needed for the *build* (after the
    artifact is built these have no effect).

    * **ref**: A name to use to inject information of this dependency
      into the build environment. Above, 
      ``$zlib`` will be the absolute path to the ``zlib`` artifact,
      ``$zlib_id`` will be the full artifact ID, while
      ``$zlib_relpath`` will be the relative path from ``$PREFIX`` to the
      zlib artifact.

    * **id**: The artifact ID. If the value is prepended with
      ``"virtual:"``, the ID is a virtual ID, used so that the real
      one does not contribute to the hash. See section on virtual
      dependencies below.

    Each dependency that has a ``bin`` sub-directory will have this inserted
    in ``$PATH`` in the order the dependencies are listed (and these
    are the *only* entries in ``$PATH``, ``/bin`` etc. are not present).

    **Note**: The order affects the hash (since it affects ``$PATH``).
    Whenever ordering does not matter, the list should be sorted prior
    to input by the ``ref`` argument to maintain hash stability.

**sources**:
    Unpacked into the temporary build directory. The optional ``target`` parameter
    gives a directory they should be extracted to (default: ``"."``). The ``strip``
    parameter (only applies to tarballs) acts like the
    `tar` ``--strip-components`` flag.

    Order does not affect the hashing. The build will fail if any of
    the archives contain conflicting files.

**files**:
    Embed small text files in-line in the build spec. This is really equivalent
    to uploading the file to the source store, but can provide more immediate
    documentation. **target** gives the target filename and **contents** is
    a list of lines (which will be joined by the platform newline character).

    For anything more than a hundred lines or so (small scripts and configuration
    files), you should upload to the source cache and put a ``files:...`` key
    in *sources* instead.

    Order does not affect hashing. Files will always be encoded in UTF-8.

**commands**:
    Executed to perform the build. If any command fails, the build fails.

    Note that while more than one command is allowed, and they will be
    executed in order, this is not a shell script: Each command is
    spawned from the builder process with a pristine environment. For anything
    that is not completely trivial one should use a scripting language.


Virtual dependencies
--------------------

Some times one do not wish some dependencies to become part of the
hash.  For instance, if the ``cp`` tool is used during the build, one
is normally ready to trust that the build wouldn't have been different
if a newer version of the ``cp`` tool was used instead.

Virtual dependencies, such as ``virtual:unix`` in the example above,
are present in order. If a bug in ``cp`` is indeed discovered,

Embedding version information in the virtual artifact names provide
the possibility of recovering from mis-builds caused by bugs in the
tools provided. If a serious bug is indeed discovered in ``cp``, one
can start to use the name ``virtual:unix/r2`` instead, thus triggering
rebuilds of artifacts built with the old version.

This feature should not be over-used. For instance, GCC should almost
certainly not be a virtual dependency.

.. note::
   One should think about virtual dependencies merely as a tool that gives
   the user control (and responsibility) over when the hash should change.
   They are *not* the primary mechanism for providing software
   from the host; though software from the host will sometimes be
   specified as virtual dependencies.


Discussion
----------

Safety of the shortened IDs
'''''''''''''''''''''''''''

Hashdist will never use these to resolve build artifacts, so collision
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

Reference
---------

"""

# package exports
from .builder import BuildFailedError
from .build_spec import (BuildSpec, as_build_spec, get_artifact_id,
                         InvalidBuildSpecError)
from .build_store import BuildStore
