Hashdist 0.1 tutorial
========================

The goal of the 0.1 release is to gather input that can steer further
development. Please speak up on the mailing list:
https://groups.google.com/forum/?fromgroups#!forum/hashdist



Getting Hashdist
----------------

::

    git clone git://github.com/hashdist/hashdist.git

There is currently no installer; this tutorial will assume
that the directory is put in ``PYTHONPATH`` and the ``bin``-subdirectory
in ``PATH``. Hashdist is developed using Python 2.7 (Python 2.6 may work).

Once downloaded, execute::

    $ hdist inithome

This will set up ``~/.hdist`` for storing code/software as well as ``~/.hdistconfig``.

Core vs. front-end
------------------

The core part of Hashdist, living in ``hashdist.core``,
has a JSON-oriented API and will in time hopefully have many
front-ends, one for each type of userbase.

Because a back-end by itself is boring, Hashdist currently provides
a simple front-end in ``hashdist.recipes``. This is where our tutorial
starts, but please keep in mind that the front-end is only one out of
many possible ways to expose the core functionality.
In time there will hopefully be many front-ends for different
userbases.

Hashdist recipes: Building HDF5 from sources
--------------------------------------------

We want to build HDF5 together with two of its dependencies, szip and
zlib.  We fetch one as a tarball and one using git::

    $ hdist fetch http://zlib.net/zlib-1.2.7.tar.gz
    <snip curl output>
    tar.gz:qBbZXVZi6CeWJavb6n0OYhV9fR8CgCCxB1UAv0g+1e8

    $ hdist fetchgit git://github.com/erdc-cm/hdf5.git master
    <snip git output>
    git:802ff8c4ccd931b104a95c3f30ff385008d95f31

The last line in each case is the `key` of the sources. This is used
both to verify the contents on extraction, and as a
globally unique ID for the sources.  Fetched sources are stored under
``~/.hdist/src``, indexed by the key.

In general tarballs are faster to unpack, but if one is tracking a
project in development then it is wasteful to download a full tarball
for every new build, so git is also supported (hopefully more VCSes
in time).

We don't have to pre-fetch the sources, that was only done to get hold
of the keys. So let's delay getting the sources of HDF5 itself, and
focus on the build. We create a script, say, ``mystack.py``,
containing::

    import hashdist.recipes as hr

    unix = hr.UnhashedUnix()
    make = hr.UnhashedMake()
    gcc = hr.UnhashedGCCStack()
    zlib = hr.ConfigureMakeInstall('zlib', '1.2.7',
                                   'http://zlib.net/zlib-1.2.7.tar.gz',
                                   'tar.gz:+pychjjvuMuO9eTdVFPkVXUeHFMLFZXu1Gbhvpt+JsU',
                                   unix=unix, make=make, gcc=gcc)
    hr.cli.stack_script_cli(zlib)

.. note::
   The URL is at this point unecesarry on your own system since an object
   with the given key is already stored in the source cache; it is present
   so that when you ship the script to somebody else the sources can be
   automatically downloaded.

Then run it::

    $ python mystack.py
    zlib/1.2.7/7uGpgC..                                                    [NEEDS BUILD]
      virtual:gcc-stack (=gcc-stack/host/YC9yQn..)                         [NEEDS BUILD]
        virtual:hdist-cli (=hdist-cli/n/MOjRiz..)                          [NEEDS BUILD]
      virtual:unix (=unix/host/TBEGJ1..)                                   [NEEDS BUILD]
        virtual:hdist-cli (see above)                                      [NEEDS BUILD]
      virtual:make (=make/host/7lK-MB..)                                   [NEEDS BUILD]
        virtual:hdist-cli (see above)                                      [NEEDS BUILD]

.. note::
   If the hashes don't look exactly like the above, it would be because
   this tutorial is out-dated. The hashes should be the same between
   different systems.

Nothing happened; the objects created are a set of rules and take
no action. To take action, run it with the "build" command::

    $ python mystack.py build
    <...snip build output...>
    $ python mystack.py
    Status:
    
    Status:
    
    hdf5/1.8.10/IyikMi..                                                   [NEEDS BUILD]
      virtual:unix (=unix/host/TBEGJ1..)                                   [NEEDS BUILD]
        virtual:hdist-cli (=hdist-cli/n/mkJy9Z..)                          [NEEDS BUILD]
      zlib/1.2.7/rJ0NkA..                                                  [NEEDS BUILD]
        virtual:gcc-stack (=gcc-stack/host/YC9yQn..)                       [NEEDS BUILD]
          virtual:hdist-cli (see above)                                    [NEEDS BUILD]
        virtual:unix (see above)                                           [NEEDS BUILD]
          virtual:hdist-cli (see above)                                    [NEEDS BUILD]
        virtual:make (=make/host/7lK-MB..)                                 [NEEDS BUILD]
          virtual:hdist-cli (see above)                                    [NEEDS BUILD]
      szip/2.1/Et3JNr..                                                    [NEEDS BUILD]
        virtual:gcc-stack (see above)                                      [NEEDS BUILD]
          virtual:hdist-cli (see above)                                    [NEEDS BUILD]
        virtual:unix (see above)                                           [NEEDS BUILD]
          virtual:hdist-cli (see above)                                    [NEEDS BUILD]
        virtual:make (see above)                                           [NEEDS BUILD]
          virtual:hdist-cli (see above)                                    [NEEDS BUILD]
      virtual:gcc-stack (see above)                                        [NEEDS BUILD]
        virtual:hdist-cli (see above)                                      [NEEDS BUILD]
      virtual:make (see above)                                             [NEEDS BUILD]
        virtual:hdist-cli (see above)                                      [NEEDS BUILD]

Build needed
    
    Everything up to date!
    Root artifact: /home/dagss/.hdist/opt/zlib/1.2.7/7uGp

::
    ~/.hdist/opt/hdf5/1.8.7/Fhra/lib $ ldd libhdf5.so
        linux-vdso.so.1 =>  (0x00007fff07bff000)
        libsz.so.2 => /home/dagss/.hdist/opt/szip/2.1/Et3J/lib/libsz.so.2 (0x00007f48774ef000)
        libz.so.1 => /lib/x86_64-linux-gnu/libz.so.1 (0x00007f48772b1000)
        libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x00007f4876fb7000)
        libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f4876bfa000)
        /lib64/ld-linux-x86-64.so.2 (0x00007f4877bb5000)

Notice that not everything is perfect, only ``libsz`` and not ``libz``
is picked up from the Hashdist store. The reason is ``RPATH``::

    ~/.hdist/opt/hdf5/1.8.7/Fhra/lib $ scanelf -r libhdf5.so
     TYPE   RPATH FILE 
    ET_DYN /home/dagss/.hdist/opt/szip/2.1/Et3J/lib libhdf5.so 

Luckily there's a ``patchelf`` tool we can use, so this problem will
(hopefully) be fixed in the next Hashdist release.


::

    $ find /home/dagss/.hdist/opt/zlib/1.2.7/7uGp
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/lib
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/lib/libz.so.1.2.7
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/lib/libz.so
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/lib/libz.so.1
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/lib/pkgconfig
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/lib/pkgconfig/zlib.pc
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/lib/libz.a
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/share
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/share/man
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/share/man/man3
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/share/man/man3/zlib.3
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/build.log
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/include
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/include/zlib.h
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/include/zconf.h
    /home/dagss/.hdist/opt/zlib/1.2.7/7uGp/build.json

Note that the 4-character hash is a shortened version (on conflicts they grow longer)::

    $ ls -lA ~/.hdist/opt/zlib/1.2.7/
    total 12
    drwxrwxr-x 5 dagss dagss 4096 Dec 18 14:25 7uGp
    lrwxrwxrwx 1 dagss dagss    4 Dec 18 14:24 7uGpgCesW-3S4R9lmzGPbMs7Xawp2C+XQmowyRZtrKE -> 7uGp

.. note::
   While the "version" string is used in a plain fashion here, it is
   encouraged in more complicated setting to put more information in it, such as
   ``zlib/1.2.7-amd64-icc-avx/CesW``. It is the version of the *build*, not the
   *software*. (Better name than "version" welcome.) Either way, the hash
   is sufficient to avoid collisions and the name and version are present
   only to aid the human reader.

Building from git sources
-------------------------

Tarballs are good for slowly-moving sources, but for tracking the development head
of a project it is suboptimal to always re-download everything. It is therefore
possible to use git instead::

    $ bin/hdist fetchgit git://github.com/erdc-cm/zlib.git master
    <... snip git output ...>
    git:f7d921d70f092380e224502bf92e256936ddce8a

If you now fetched from a fork of this repository
somewhere else, it would be smart about it and only download the
differences, independent of the repository URI.

The only changes needed to ``mystack.py`` are in the two strings identifying
the sources::

    zlib = hr.ConfigureMakeInstall('zlib', '1.2.7',
                                   'git://github.com/erdc-cm/zlib.git',
                                   'git:f7d921d70f092380e224502bf92e256936ddce8a',
                                   unix=unix, make=make, gcc=gcc)

At this point, the hash changes, triggering a rebuild::

    zlib/1.2.7/HJ6q65..                                                    [NEEDS BUILD]
      virtual:gcc-stack (=gcc-stack/host/YC9yQn..)                         [OK]
        virtual:hdist-cli (=hdist-cli/n/MOjRiz..)                          [OK]
    <...snip>

After the build this version co-exists on disk together with the
version built from the tarball::

    $ ls -lA ~/.hdist/opt/zlib/1.2.7
    total 8
    drwxrwxr-x 5 dagss dagss 4096 Dec 18 16:12 7uGp
    lrwxrwxrwx 1 dagss dagss    4 Dec 18 16:12 7uGpgCesW-3S4R9lmzGPbMs7Xawp2C+XQmowyRZtrKE -> 7uGp
    drwxrwxr-x 5 dagss dagss 4096 Dec 18 16:12 rJ0N
    lrwxrwxrwx 1 dagss dagss    4 Dec 18 16:12 rJ0NkAflxanVYyiwFMwz5oqcUcG2VhcX0S-7Sqi76l0 -> rJ0N

Consequences
------------

Note that at this point one can change the script back, and the "rebuild"
is instant, merely as a side-effect of the hashes being the same
as in a previous build. This is a very powerful feature, because it
means that simply by putting ``mystack.py`` under git control,
one can jump around between different software stacks using git.

Peeking under the hood
''''''''''''''''''''''

It is instructive to have a look at that ``build.json`` file (up to pretty-formatting)::

    {
        "name" : "zlib", 
        "version" : "1.2.7"
        "sources" : [
            {
                "key" : "tar.gz:+pychjjvuMuO9eTdVFPkVXUeHFMLFZXu1Gbhvpt+JsU", 
                "strip" : 1, 
                "target" : "."
            }
        ]
        "dependencies" : [
            {"ref": "gcc", "id": "virtual:gcc-stack"},
            {"ref": "make", "id": "virtual:make"},
            {"ref": "unix", "id": "virtual:unix"}
        ],
        "env" : {},
        "files" : [], 
        "parameters" : {}, 
        "commands" : [
            ["./configure", "--prefix=${TARGET}"], 
            ["make"],
            ["make install"]
        ],
    }

``build.json`` is essentially a domain-specific language to launch a reproducible
build process. The 
