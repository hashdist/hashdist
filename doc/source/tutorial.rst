Hashdist 0.1 tutorial
========================

The goal of the 0.1 release is to gather input that can steer further
development. Please speak up on the mailing list:
https://groups.google.com/forum/?fromgroups#!forum/hashdist

.. contents::


Getting Hashdist
----------------

::

    git clone git://github.com/hashdist/hashdist.git

There is currently no installer; this tutorial will assume
that the directory is put in ``PYTHONPATH`` and the ``bin``-subdirectory
in ``PATH``. Hashdist is developed using Python 2.7 (Python 2.6 may work).

Once downloaded, execute::

    $ hdist inithome

This will set up ``~/.hdistconfig``, which by default stores everything
under ``~/.hdist`` which is also created::

    $ ls ~/.hdist
    bld  opt  src

In ``bld`` temporary builds are created, ``src`` will cache downloaded
source code, while ``opt`` contains software that has been built.

Core vs. front-end
------------------

The core part of Hashdist, living in ``hashdist.core``,
has a JSON-oriented API and will in time hopefully have many
front-ends, one for each type of userbase.

Because a back-end by itself is boring, Hashdist currently provides
a simple front-end in ``hashdist.recipes``. This is where our tutorial
starts, but please keep in mind that the front-end is only one out of
many possible ways to expose the core functionality.

An analogy may be that ``hashdist.core`` is like the GNU Make program,
while ``hashdist.recipes`` are utility snippets one can use in
Makefiles. In the 0.1 release, the core is 3500 LOC while the recipes
part is less than 400 LOC.

Example: Building HDF5 from sources
-----------------------------------

We want to build HDF5 together with its two dependencies, szip and
zlib.  We fetch one as a tarball and one using git::

    $ hdist fetch http://zlib.net/zlib-1.2.6.tar.gz
    <snip curl output>
    tar.gz:HtaA96RDXGi2QGcJuwiHQrVit67BpE0Llh6UzzCv-q8

    $ hdist fetchgit git://github.com/erdc-cm/szip.git master
    <snip git output>
    git:87863577a4656d5414b0d598c91fed1dd227f74a

The last line in each case is the *key* of the sources. This is used
both to verify the contents on extraction, and as a
globally unique ID for the sources.  Fetched sources are stored under
``~/.hdist/src``, indexed by the key.

In general tarballs are faster to unpack, but if one is tracking a
project in development then it is wasteful to download a full tarball
for every new build, so git is also supported (hopefully more VCSes
in time).

Pre-fetching the sources is not necesarry if one already knows
the key, so we skip the download of HDF5 itself at this point, and move to
the creation of a script ``mystack.py`` containing::

    import hashdist.recipes as hr
    
    unix = hr.NonhashedUnix()
    gcc = hr.NonhashedGCCStack()
    
    zlib = hr.ConfigureMakeInstall('zlib', '1.2.6',
                                   'http://zlib.net/zlib-1.2.6.tar.gz',
                                   'tar.gz:HtaA96RDXGi2QGcJuwiHQrVit67BpE0Llh6UzzCv-q8',
                                   unix=unix, gcc=gcc)
    
    szip = hr.ConfigureMakeInstall('szip', '2.1',
                                   'git://github.com/erdc-cm/szip.git',
                                   'git:87863577a4656d5414b0d598c91fed1dd227f74a',
                                   configure_flags=['--with-pic'],
                                   unix=unix, gcc=gcc)
    
    hdf5 = hr.ConfigureMakeInstall('hdf5', '1.8.10',
                                   'http://www.hdfgroup.org/ftp/HDF5/current/src/hdf5-1.8.10.tar.bz2',
                                   'tar.bz2:+m5rN7eXbtrIYHMrh8UDcOO+ujrnhNBfFvKYwDOkWkQ',
                                   configure_flags=['--with-szlib', '--with-pic'],
                                   zlib=zlib, szip=szip, unix=unix, gcc=gcc)

    profile = hr.Profile([hdf5, szip, zlib])
    
    hr.cli.stack_script_cli(profile)

(Yes, this is a simplistic example. Just take our word for the fact that
Hashdist will easily let you use your own shell scripts to do more
complicated builds. See also discussion below.)

Then run the script to figure out the current status::

    $ python mystack.py -s
    Status:

    profile/n/D3UJ..                                                       [needs build]
      hdf5/1.8.10/im0c..                                                   [needs build]
        virtual:gcc-stack/host (=gcc-stack/host/CT2D..)                    [needs build]
          virtual:hdist-cli/r0 (=hdist-cli/r0/eJbh..)                      [needs build]
        szip/2.1/BT1Q..                                                    [needs build]
          virtual:unix/host (=unix/host/R5KL..)                            [needs build]
            virtual:hdist-cli/r0                                           (see above)
          virtual:gcc-stack/host                                           (see above)
        zlib/1.2.6/TI7T..                                                  [needs build]
          virtual:gcc-stack/host,virtual:unix/host                         (see above)
        virtual:unix/host                                                  (see above)
      szip/2.1/BT1Q..,zlib/1.2.6/TI7T..                                    (see above)
    
    Build needed

Then kick off the build::

    $ python mystack.py target
    ...
    [zlib] Unpacking sources to /home/dagss/.hdist/bld/zlib/1.2.6/osu6
    [zlib] Building zlib/1.2.6/osu6.., follow log with:
    [zlib]   tail -f /home/dagss/.hdist/bld/zlib/1.2.6/osu6/build.log
    [zlib] running ['./configure', '--prefix=/home/dagss/.hdist/opt/zlib/1.2.6/osu6']
    [zlib] success
    ...
    Created "target" -> "/home/dagss/.hdist/opt/profile/n/-3e-"
    

If you want more information there's the ``-v`` flag, in which case you'd
get::

    $ python mystack.py -v local
    ...
    [szip] Unpacking sources to /home/dagss/.hdist/bld/szip/2.1/BT1Q-1
    [szip] Building szip/2.1/BT1Q..
    [szip] running ['./configure', '--prefix=/home/dagss/.hdist/opt/szip/2.1/BT1Q', '--with-pic']
    [szip] environment:
    [szip]   {'ARTIFACT': '/home/dagss/.hdist/opt/szip/2.1/BT1Q',
    [szip]    'BUILD': '/home/dagss/.hdist/bld/szip/2.1/BT1Q-1',
    [szip]    'HDIST_CFLAGS': '',
    [szip]    'HDIST_LDFLAGS': '',
    [szip]    'HDIST_VIRTUALS': 'virtual:gcc-stack/host=gcc-stack/host/CT2DnIT3D7UfuftXhqmbAFjMHhlTztIPq2MyVdiw-kg;virtual:hdist-cli/r0=hdist-cli/r0/eJbh7T9+3ewnn7+Q+XAGTxQAYv9fJKqZbmAi9+ZPDrU;virtual:unix/host=unix/host/R5KLiZOFsP9ApHyQR0kTDPY3Alj0PA7IjU1nXGweU9Y',
    [szip]    'PATH': '/home/dagss/.hdist/opt/gcc-stack/host/CT2D/bin:/home/dagss/.hdist/opt/unix/host/R5KL/bin',
    [szip]    'gcc': '/home/dagss/.hdist/opt/gcc-stack/host/CT2D',
    [szip]    'gcc_id': 'gcc-stack/host/CT2DnIT3D7UfuftXhqmbAFjMHhlTztIPq2MyVdiw-kg',
    [szip]    'unix': '/home/dagss/.hdist/opt/unix/host/R5KL',
    [szip]    'unix_id': 'unix/host/R5KLiZOFsP9ApHyQR0kTDPY3Alj0PA7IjU1nXGweU9Y'}
    [szip] cwd: /home/dagss/.hdist/bld/szip/2.1/BT1Q-1
    [szip] checking for a BSD-compatible install... /home/dagss/.hdist/opt/unix/host/R5KL/bin/install -c
    [szip] checking whether build environment is sane... yes
    [szip] checking for a thread-safe mkdir -p... /home/dagss/.hdist/opt/unix/host/R5KL/bin/mkdir -p
    ...
    Created "target" -> "/home/dagss/.hdist/opt/profile/n/-3e-"

At the end of the build we are left with
``~/.hdist/opt/szip/2.1/BT1Q``, ``~/.hdist/zlib/1.2.6/osu6`` and
``~/.hdist/hdf5/1.8.10/3ysA``, e.g.,::

    $ find ~/.hdist/opt/zlib/1.2.6/osu6
    /home/dagss/.hdist/opt/zlib/1.2.6/osu6
    /home/dagss/.hdist/opt/zlib/1.2.6/osu6/lib
    /home/dagss/.hdist/opt/zlib/1.2.6/osu6/lib/libz.so
    /home/dagss/.hdist/opt/zlib/1.2.6/osu6/lib/libz.so.1.2.6
    /home/dagss/.hdist/opt/zlib/1.2.6/osu6/lib/libz.so.1
    /home/dagss/.hdist/opt/zlib/1.2.6/osu6/lib/libz.a
    /home/dagss/.hdist/opt/zlib/1.2.6/osu6/include
    /home/dagss/.hdist/opt/zlib/1.2.6/osu6/include/zlib.h
    ...

Also, there is ``~/.hdist/opt/profile/n/-3e-``, containing symlinks
to all three packages::

    $ ls -l ~/.hdist/opt/profile/n/-3e-/bin
    lrwxrwxrwx 1 dagss dagss 50 Dec 21 16:19 h5diff -> /home/dagss/.hdist/opt/hdf5/1.8.10/3ysA/bin/h5diff
    lrwxrwxrwx 1 dagss dagss 50 Dec 21 16:19 h5dump -> /home/dagss/.hdist/opt/hdf5/1.8.10/3ysA/bin/h5dump
    lrwxrwxrwx 1 dagss dagss 52 Dec 21 16:19 h5import -> /home/dagss/.hdist/opt/hdf5/1.8.10/3ysA/bin/h5import
    ...
    
    $ ls -l ~/.hdist/opt/profile/n/-3e-/lib
    lrwxrwxrwx 1 dagss dagss   54 Dec 21 16:19 libhdf5.so -> /home/dagss/.hdist/opt/hdf5/1.8.10/3ysA/lib/libhdf5.so
    lrwxrwxrwx 1 dagss dagss   49 Dec 21 16:19 libsz.so -> /home/dagss/.hdist/opt/szip/2.1/BT1Q/lib/libsz.so
    ...

Finally, since we added ``local`` as a script argument, a ``local`` symlink
is emitted in the current directory for our convenience::

    $ ls -l local
    lrwxrwxrwx 1 dagss dagss 37 Dec 21 16:19 local -> /home/dagss/.hdist/opt/profile/n/-3e-

.. note::

   If the hashes don't look exactly like the above, it would be
   because this tutorial is out-dated. The hashes should be the same
   between different systems. The 4-character hashes are abbreviated
   versions of the full ID (and become longer on collisions); there
   are symlinks from the full ID to the abbreviated ones.

   While the "version" string is used in a plain fashion here, it is
   encouraged in more complicated setting to put more information in
   it, such as ``zlib/1.2.6-amd64-icc-avx/CesW``.

Using the software
------------------

To actually use the results, you can simply put ``local/bin`` in your
``$PATH``, and/or point to ``local/lib`` and ``local/include`` when
you build software. The plan is to provide a tool so that you can do
``source  <(hdist env profile-name)`` from a Bash session, but this is
not implemented yet.

More complicated software, such as Python, will be discussed in another
section below.

Note that the binaries and libraries have all been linked with an "RPATH",
meaning that no messing with ``LD_LIBRARY_PATH`` is needed. Note how
paths beneath ``/home/dagss/.hdist`` features below::

    $ ldd local/bin/h5ls
        linux-vdso.so.1 =>  (0x00007fff4bb58000)
        libhdf5.so.7 => /home/dagss/.hdist/opt/hdf5/1.8.10/3ysA/lib/libhdf5.so.7 (0x00007f0347e30000)
        libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f0347a4c000)
        libsz.so.2 => /home/dagss/.hdist/opt/szip/2.1/BT1Q/lib/libsz.so.2 (0x00007f0347838000)
        libz.so.1 => /home/dagss/.hdist/opt/zlib/1.2.6/osu6/lib/libz.so.1 (0x00007f034761b000)
        libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x00007f0347320000)
        /lib64/ld-linux-x86-64.so.2 (0x00007f03482ed000)

    $ ldd local/lib/libhdf5.so
        linux-vdso.so.1 =>  (0x00007fffe44dd000)
        libsz.so.2 => /home/dagss/.hdist/opt/szip/2.1/BT1Q/lib/libsz.so.2 (0x00007fb5bfeec000)
        libz.so.1 => /home/dagss/.hdist/opt/zlib/1.2.6/osu6/lib/libz.so.1 (0x00007fb5bfcce000)
        libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x00007fb5bf9ae000)
        libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007fb5bf5f1000)
        /lib64/ld-linux-x86-64.so.2 (0x00007fb5c05bd000)

Again, this will be further discussed below.

Branching your software stack
-----------------------------

In the example above, we did in fact use an outdated version of *zlib*,
so let's update to a newer one::

    zlib = hr.ConfigureMakeInstall('zlib', '1.2.7',
                                   'http://downloads.sourceforge.net/project/libpng/zlib/1.2.7/zlib-1.2.7.tar.gz',
                                   'tar.gz:+pychjjvuMuO9eTdVFPkVXUeHFMLFZXu1Gbhvpt+JsU',
                                   unix=unix, gcc=gcc)

(I ran ``hdist fetch`` to retrieve the updated hash, but you can just copy it.)
Then rerun (or read the section below on `ccache` to save some time)::

    (master) ~/code/hashdist $ python examples/mystack.py local
    profile/n/4z+N..                                                       [needs build]
      hdf5/1.8.10/W+IA..                                                   [needs build]
        virtual:gcc-stack/host (=gcc-stack/host/CT2D..)                    [ok]
          virtual:hdist-cli/r0 (=hdist-cli/r0/eJbh..)                      [ok]
        szip/2.1/BT1Q..                                                    [ok]
          virtual:unix/host (=unix/host/R5KL..)                            [ok]
            virtual:hdist-cli/r0                                           (see above)
          virtual:gcc-stack/host                                           (see above)
        zlib/1.2.7/whcr..                                                  [needs build]
          virtual:gcc-stack/host,virtual:unix/host                         (see above)
        virtual:unix/host                                                  (see above)
      szip/2.1/BT1Q..,zlib/1.2.7/whcr..                                    (see above)
    
    Build needed
    [zlib] Unpacking sources to /home/dagss/.hdist/bld/zlib/1.2.7/whcr
    [zlib] Building zlib/1.2.7/whcr.., follow log with:
    [zlib]   tail -f /home/dagss/.hdist/bld/zlib/1.2.7/whcr/build.log
    ...

And if and only if the build succeeds, the `target` link is atomically
updated.

The existing build results (a.k.a. *artifacts*) from the previous
build are left in place. The trailing hashes ensures that even if
there is not a version bump, but just a slightly changed ``CFLAGS``,
the artifacts can happily coexist on disk.

**NOW COMES THE MAIN POINT OF HASHDIST**: If you now change
``mystack.py`` back to how it was before, with *zlib* version 1.2.6,
the rebuild will be nearly instant since the artifacts are already
there. So, if you simply put ``mystack.py`` under version
control, you are able to very quickly jump between different software
stacks, go back and forward in time, and so on.

This can also transparently handle some features found in package
management systems. To uninstall HDF5, but keep zlib and szip around,
it is sufficient to change the line::

    profile = hr.Profile([hdf5, szip, zlib])

to::

    profile = hr.Profile([szip, zlib])

Again, a "rebuild" is instant.


The future
----------

That concludes the high-level tour of the current
functionality. Further development will have two facets:

**I) Building the car:** The ``mystack.py`` script is not an adequate
solution. The point is that it shows how the Hashdist API can be used
by something else that parses a higher-level, more user-friendly
description of the desired software stack.

For instance, to build (yet another) scientific Python source
distribution, one could continue the script for a couple of hundred
lines to get something very similar to Sage, but with faster
upgrades. Then add a configuration file that is parsed and affects the
build flags, automatic fetching of metadata from PyPI, and so on.

Note that Hashdist does not provide anything in the direction of a
**package management system**: A system that looks at package metadata
and automatically resolve dependencies etc. (with a package system you
would only need to explicitly mention HDF5 above, not zlib and szip).
However, we believe that one or more decent systems for installing
packages can be built on top of Hashdist.

**II) Improving the engine:** Additional features will also be
needed in the core engine. The most important ones are
garbage collection (remove unused build results after some time)
and improved sandboxing (the current sandboxing is discussed below).
Distribution of resulting builds as binary packages is also
worthy of consideration, though probably out of scope for current
funding.


Advanced topics
---------------

ccache
''''''

A nice feature of "functional software building" is how easy it
can be to change how the software is built. To use *ccache*, and
significantly speed up similar rebuilds, it is currently sufficient
with::

    ccache = hr.CCache(gcc=gcc, unix=unix)
    
    zlib = hr.ConfigureMakeInstall('zlib', '1.2.7',
                                   ...,
                                   ccache=ccache, unix=unix, gcc=gcc)

Then `ccache` will know to insert itself in front of the real `gcc`
in the path, and will bind to exactly the `gcc` that is provided
(if there are more than one, see below).

Using software from host system
'''''''''''''''''''''''''''''''

Using ``gcc = hr.NonhashedGCCStack()`` as the compiler is highly
questionable; which GCC is used does not enter
the hash and so there is no way to trigger a rebuild with
a newer version of GCC. 

One solution is to set up a full build of gcc, including download of
sources etc. However, this is often not what one wants; what one wants
is to use software from the host while making that software enter the
hash. There are two ways of attacking this. First, it is in fact
very easy to integrate with existing software distributions, so in
version 0.2 one will be able to do::

    gcc = hr.DebianPackage('gcc', 'deb:oCaEGwBOSSqxE6HaLpL9nIMCjxmFHh0itPoPa18bWX0')

or::

    icc = hr.EnvironmentModules('intel', 'modules:GfOiMlTioNUZXElKQKJDqcyvPSAoewy0qBplPBCFhbI')

and then proceed to pass these as arguments to packages built by
Hashdist.  In the former case, a Debian package provides checksums
that can be used to fetch the digest very quickly. In the latter case
some hashing of files would be needed.  We expect this to be the
preferred method since it is so explicit and in fact easy to
implement.

However, if this doesn't work for some users,
one can always do something to the effect of
::

    gcc = hr.HostSoftware(['/usr/bin/gcc', '/usr/bin/as', ...],
                          'host:qatIOWcGNM7Aw+3QM32YqB7X35W-SJyl4f1Tyu+9U20')

where the listed files are hashed (by contents or name+date).

But wait, I don't want all those rebuilds!
''''''''''''''''''''''''''''''''''''''''''

Having to rebuild the entire software stack every time GCC is updated in
response to a ``sudo apt-get upgrade`` is of course a major pain!
However, it is not necesarry. The following cannot be tried today, but
facilitating it is a core feature of the design so far::

    gcc_4_6_2 = hr.DebianPackage('gcc', 'deb:oCaEGwBOSSqxE6HaLpL9nIMCjxmFHh0itPoPa18bWX0')
    hdf = hr.ConfigureMakeInstall('hdf', ..., gcc=gcc_4_6_2)
    python = hr.ConfigureMakeInstall('python', ..., gcc=gcc_4_6_2)

    gcc_4_6_3 = hr.DebianPackage('gcc', 'deb:qwvHTcGiksl+Wu3BALaBvjuXXXLO45ftmjqU3Uhlhww')
    pytables = hr.ConfigureMakeInstall('pytables', ..., gcc=gcc_4_6_3, hdf=hdf, python=python)

The key point to realize here is that it *does not have to be possible
to build a package* if it is already built; one just needs to know its
hash.

Thus one creates a "paper trail" ("hash trail"?) of exactly what has
happened: First HDF5 and Python was compiled, then the system GCC was
upgraded, then PyTables was compiled.  Of course, if one tries to pass
``gcc=gcc_4_6_2`` instead to PyTables one will get an error (unless
PyTables was in fact built at a time when the older GCC was installed).

User-facing frontends to Hashdist can simply take "metadata
snapshots" of the host system every time a new package is installed, so
that the correct paper trail of host dependencies is present.

Note how easy it now would be to request that Python *should* in fact
be rebuilt with the newest GCC. This also creates the foundation for
binary redistributable artifacts, since it is not a requirement that
the used compiler has ever been present on the current host system.
In fact, something to this effect is possible::

    pkg = hr.JustUseTheArtifactDontThinkAboutIt("python/2.7.0-compiled-in-oslo/EXBjBU87Z9GuIGFaeCnvwR4Xrlasn-7+IaAgsrox8dc")

In short: Keep in mind that in the build dependency DAG, a sub-tree
can be left out if the root is already built.

Python and details of profile construction
''''''''''''''''''''''''''''''''''''''''''

To explain how Hashdist software profiles can work with Python, it's worth
describing exactly how *virtualenv* works: It makes a sub-directory
where most of the Python files (``lib`` contents etc.) are symlinked,
but the ``python`` binary itself is *copied*.
The key is that when Python starts, it will use the real path of its
binary to try to resolve where its libraries can be found, before
checking ``/usr/lib``.

The profile creation in Hashdist is *not* hard-coded to a set of symlinks;
in fact each artifact can specify
arbitrary actions that should happen on install. Here is
``~/.hdist/opt/hdf5/1.8.10/W+IA/artifact.json`` from my system::

    {
      "install" : {
        "commands" : [
          ["hdist", "create-links",  "--key=install/parameters/links", "artifact.json"]
        ], 
        "parameters" : {
          "links" : [
            {
              "action" : "symlink", 
              "prefix" : "$ARTIFACT", 
              "select" : "$ARTIFACT/*/**/*", 
              "target" : "$PROFILE"
            }
          ]
        }
      }
    }

So it is already the case that you can make a Python build which, when
its artifact is linked up to a profile, uses virtualenv to do the job
instead of (only) creating symlinks. Thus one can get a dedicated ``lib/python2.7``
in each profile, and avoids needing to drag along a ``$PYTHONPATH`` etc.

For the purposes of Hashdist we may change this scheme a bit,
because keeping hundreds of copies of Python around, ~8 MB each,
can be prohibitive (and if profile creation is not dirt cheap then
much of the point disappears). What we can do instead is to compile a 10-line C
program which hard-codes the path to the real Python
and passes it to ``exec``, thus fooling the Python binary into thinking
its real location is the 1KB launcher program.

The build sandbox
'''''''''''''''''

TODO

Further reading
---------------

To get the whole picture it is recommended to also read
through :mod:`hashdist.core.build_store` and look at some of the
``build.json`` files (which can be found in the root of each
produced artifact).
