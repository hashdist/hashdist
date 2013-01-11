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

A Hashdist artifact ID has the form ``name/hash``, e.g.,
``zlib/4niostz3iktlg67najtxuwwgss5vl6k4``.

For the artifact paths on disk, a shortened form (4-char hash) is used
to make things more friendly to the human user. If there is a
collision, the length is simply increased for the one that comes
later. Thus, the example above could be stored on disk as
``~/.hdist/opt/zlib/4nio``, or ``~/.hdist/opt/zlib/1.2.7/4nios``
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
        "version" : "<version>",
        "description": "<what makes this build special>",
        "build": {
            "import" : [
                 {"ref": "bash", "id": "virtual:bash"},
                 {"ref": "make", "id": "virtual:gnu-make/3+"},
                 {"ref": "zlib", "id": "zlib/1.2.7/fXHu+8dcqmREfXaz+ixMkh2LQbvIKlHf+rtl5HEfgmU"},
                 {"ref": "unix", "id": "virtual:unix"},
                 {"ref": "gcc", "id": "gcc/host-4.6.3/q0VSL7JmzH1P17meqITYc4kMbnIjIexrWPdlAlqPn3s", "before": ["virtual:unix"]},
             ],
             "script" : [
                 ["hdist", "build-unpack-sources"],
                 ["hdist", "build-write-files"],
                 ["bash", "build.sh"]
             ],
         },
         "sources" : [
             {"key": "git:c5ccca92c5f136833ad85614feb2aa4f5bd8b7c3"},
             {"key": "tar.bz2:RB1JbykVljxdvL07mN60y9V9BVCruWRky2FpK2QCCow", "target": "sources", "strip": 1},
             {"key": "files:5fcANXHsmjPpukSffBZF913JEnMwzcCoysn-RZEX7cM"}
         ],
         "files" : [
             { "target": "build.sh",
               "text": [
                 "set -e",
                 "./configure --prefix=\\"${ARTIFACT}\\"",
                 "make",
                 "make install"
               ]
             }
         ],
    }


**name**:
    Should match ``[a-zA-Z0-9-_+]+``.

**version**:
    Should match ``[a-zA-Z0-9-_+]*``.

..
    **description**:
    What makes this build special in some human-readable form, e.g.,
    ``icc-avx-gotoblas`` (this may be part of the pathname on some
    platforms). Should match ``[a-zA-Z0-9-_+]*``.

**build**:
    A job to run to perform the build. See :mod:`hashdist.core.run_job`
    for the documentation of this sub-document.

In addition, extra keys can be added at will to use for input to
commands executed in the build. In the example above, the `sources`
key is read by the ``hdist build-unpack-sources`` command.

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

.. automodule:: hashdist.core.build_store.build_store
    :members:

.. automodule:: hashdist.core.build_store.build_spec
    :members:

.. automodule:: hashdist.core.build_store.builder
    :members:


"""

# package exports
from .build_spec import BuildSpec, as_build_spec, shorten_artifact_id
from .build_store import BuildStore
