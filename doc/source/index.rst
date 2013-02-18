Welcome to the Hashdist documentation
=====================================


Core idea of Hashdist
---------------------

Current solutions for software distribution fall short for some
user-bases.  One such example is scientific software, in particular on
HPC clusters.  Another example is Python packaging for developers who
need to live on bleeding edge across multiple platforms.

The idea of Hashdist is to solve the problem of software distribution
through a declarative approach: You always specify a full distribution
that you want in a set of configuration files, then do a full rebuild
(from source) in order for changes to be reflected. However, builds
are cached under an associated hash reflecting the entire build
environment, so that a "full rebuild" is often very fast. Thus,
"uninstall" is simply removing the package from the configuration and
do a rebuild, no explicit code is needed to implement the "uninstall"
feature. (Also, the "build" step could potentially mean downloading a
binary package over the net, though that’s out of scope currently.)

With respect to the plethora of scientific Python distributions,
Hashdist does not hope to replace these, but rather to provide core
technology that one or more of them can use.  See the :ref:`FAQ` for more
details.

Status
------

The goal of Hashdist v0.1 is to gather input that can steer further
development.

Hashdist is only tested on Linux and Python 2.7. Python 2.6 may work.
Mac OS X status is unknown, Windows will definitely not work.

User's guide
------------

.. toctree::
   :maxdepth: 1

   tutorial
   faq
   building

Hashdist API reference
----------------------


Important concepts
''''''''''''''''''

.. toctree::
   :maxdepth: 1

   core/source_cache
   core/build_store
   core/sandbox
   core/profile

Support code
''''''''''''

.. toctree::
   :maxdepth: 1

   core/hasher
   core/links
   core/ant_glob

