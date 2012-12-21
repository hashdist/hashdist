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
do a rebuild, no explicit code is needed to implement the “uninstall”
feature. (Also, the "build" step could potentially mean downloading a
binary package over the net, though that’s out of scope currently.)

.. note::

   With respect to the plethora of scientific Python distributions,
   Hashdist does not hope to replace these, but rather to provide
   core technology that all of them can use.

   See the FAQ for more details on ambitions and relations with
   existing projects.


User's guide
------------

.. toctree::
   :maxdepth: 1

   tutorial
   faq

Power-users' reference
----------------------

Important concepts
''''''''''''''''''

.. toctree::
   :maxdepth: 1

   core/source_cache
   core/build_store
   core/profile

Support code
''''''''''''

.. toctree::
   :maxdepth: 1

   core/hasher
   core/links
   core/ant_glob

Other
'''''

.. toctree::
   :maxdepth: 1

   installing
   mess



Terminology
-----------

**Distribution**:
    An end-user software distribution that makes use of Hashdist
    under the hood, e.g., python-hpcmp

**Artifact**:
    The result of a build process, identified by a hash of the
    inputs to the build

**Profile**:
    A "prefix" directory structure ready for use through
    ``$PATH``, containing subdirectories ``bin``, ``lib``, and so on
    with all/some of the software one wants to use.

**Package**:
    Used in the loose sense; a program/library, e.g., NumPy, Python etc.; 
    what is **not** meant is a specific package format like ``.spkg``, ``.egg``
    and so on (which is left undefined in the bottom two Hashdist layers)

Design principles
-----------------

 * Many small components with one-way dependencies, accessible through
   command line and as libraries (initially for Python, but in principle
   for more languages too).

 * Protocols between components are designed so that one can imagine
   turning individual components into server applications dealing with
   high loads.

 * However, implementations of those protocols are currently kept as
   simple as possible.

 * Hashdist is a language-neutral solution; Python is the
   implementation language chosen but the core tools can (in theory)
   be rewritten in C or Ruby without the users noticing any difference

 * The components are accessible through a common ``hdist`` command-line tool.
   This accesses both power-user low-level features and the higher-level
   "varnish", without implying any deep coupling between them (just like `git`).



Powerusers' guide, layer by layer
---------------------------------

Hashdist consists of two (eventually perhaps three) layers. The idea
is to provide something useful for as many as possible. If a
distribution only uses the the *core layer* (or even only some of the
components within it) it can keep on mostly as before, but get a
performance boost from the caching aspect.  If the distribution wants
to buy into the greater Hashdist vision, it can use the *profile
specification layer*.  Finally, for end-users, a final user-interface
layer is needed to make things friendly.  Here Hashdist
will probably remain silent for some time, but some standards,
best practices and utilities may emerge. For now, a user interface ideas section is
included below.


.. toctree::
   :maxdepth: 2
   
   core
   profilespec
   uiideas


