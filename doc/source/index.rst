Welcome to the Hashdist documentation
=====================================

.. warning::

   Hashdist is still vapour-ware! This documentation just reflects
   how we want things to be.

.. warning::

   This documentation is currently meant for power-users and developers.


Core idea of Hashdist
---------------------

Current solutions for software distribution fall short for some
user-bases.  One such example is scientific software, in particular on
HPC clusters.  Another example is Python packaging for developers who
need to live on bleeding edge across multiple platforms.

The idea is to solve the problem of software distribution through a
declarative approach: You always specify a full distribution that you
want in a set of configuration files, then do a full rebuild (from
source) in order for changes to be reflected. However, builds are
cached under an associated hash reflecting the entire build
environment, so that a "full rebuild" is often very fast. Thus,
"uninstall" is simply removing the package from the configuration and
do a rebuild, no explicit code is needed to implement the “uninstall”
feature. (Also, the "build" step could potentially mean downloading a
binary package over the net, though that’s out of scope currently.)

**Note**: Hashdist chooses Python as its implementation language, and
the initial users will come from that community, but there's nothing
Python-specific about the core layer of Hashdist.

Relationship with software distributions
----------------------------------------

Hashdist is not a software distribution in itself, but rather a
"meta-distribution" or distribution framework. It
provides enough features that power-users may use it directly, however
we expect that in typical use it will be **rebranded** and expanded on
to provide a more user-friendly solution. If all goes well, the current
scientific Python distribution may all live side by side using Hashdist
underneath. The ways in which you download, select and configure
packages in each of these distribution systems will necesarrily be
different, and that is the intention: To allow flexible
experimentation on the front-end side, and cater for the specific
needs of different userbases.

Relationship with the Python packaging mess
-------------------------------------------

It's commonly acknowledged that packaging of Python software
has...challenges (to put it very mildly). However, that is a different
problem domain. Hashdist is trying to be "the Debian of choice for
cases where Debian technology doesn't work". Debian needs to package
Python software too.

The two interact to some degree because the weaknesses in the
packaging of Python software must be worked around on the distribution
level. But we are *not* proposing that when writing a Python package
you should care more about Hashdist than Debian or Windows.


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

Reference
---------

.. toctree::
   :maxdepth: 1

   core/source_cache
   core/build_store
   core/hasher


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

Reference manual
----------------

.. toctree::
   :maxdepth: 2

   installing


