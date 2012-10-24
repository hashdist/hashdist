Power users' guide to the vapourware soon to be known as Hashdist
=================================================================

What follows is a walkthrough of Hashdist with focus on showing off
how components are strung together.

Terminology
-----------

**Distribution**:
    An end-user software distribution that makes use of Hashdist
    under the hood, e.g., python-hpcmp

**Artifact**:
    The uniquely hashed result of a build process

**Profile**:
    A "prefix" directory structure ready for use through
    ``$PATH``, containing subdirectories ``bin``, ``lib``, and so on
    with all/some of the software one wants to use.

**Package**:
    A program/library, e.g., NumPy, Python etc.; 
    what is **not** meant is a specific package format like ``.spkg``, ``.egg``
    and so on (which is left undefined in this document)

Design principles
-----------------

 - Many small components with one-way dependencies, accessible through
   command line and as Python libraries.

 - Protocols between components are designed so that one can imagine
   turning individual components into server applications dealing with
   high loads. However, implementations of those protocols are
   currently kept as simple as possible.

 - The components are accessible through a common ``hdist`` command-line tool.
   This accesses both power-user low-level features and the higher-level
   "varnish", without implying any deep coupling between them (just like `git`).


The role of Hashdist
--------------------

Hashdist is a "meta-distribution" or distribution framework. It
provides enough features that power-users may use it directly, however
we expect that in typical use it will be rebranded and expanded on
to provide a more user-friendly solution. In time, hopefully PyHPC,
QSnake, Sage, python-hpcmp may all live side by side using Hashdist
underneath. The ways in which you download, select and configure
packages in each of these distribution systems will necesarrily be
different, and that is the intention: To allow flexible
experimentation on the front-end side, and cater for the specific
needs of different userbases.

Hashdist (by which we mean both the library/programs and the source
and build artifact directories on disk) can either be shared between
distributions or isolated; thus one may have build artifacts
in ``~/.hashdist`` which are shared between PyHPC and QSnake, while
Sage has its own Hashdist store in ``~/path/to/sage/store``.

.. note::
    
    The main point of sharing Hashdist is actually to share it
    between different versions of the same distribution; i.e., two
    different QSnake versions may be located in different paths on disk,
    but if they use the global Hashdist they will share the build
    artifacts they have in common.

Details of managing parallel Hashdist installations
'''''''''''''''''''''''''''''''''''''''''''''''''''

By default, Hashdist is exposed through the ``hdist`` command. It is
configured through ``~/.hashdistconfig``::

    [hashdist]
        hdist = ~/.hashdist/bin/hdist
        python2-path = ~/.hashdist/lib/python2

    [sources]
        store = ~/.hashdist/source
        keep-transient = 1 week
        keep-targz = forever
        keep-git = forever

    <...>

If a software distribution bundles its own isolated Hashdist
environment then the ``hdist`` command should be rebranded (e.g.,
``qsnake-hdist``), and it should read a different configuration
file. Similarly, the Python package should be rebranded (e.g.,
``qsnake.hashdist``).

The command ``hdist`` should *always* read ``~/.hashdistconfig`` (or
the configuration file specified on the command line) and launch the
command found there under the `hdist` key. Similarly, ``import
hashdist`` should add the package from the location specified in the
configuration file to ``sys.path`` and then do ``from hashdistlib
import *``.  The reason is simply that the paths mentioned in that
file are managed by a particular version of hashdist, and we want an
upgrade path. Essentially, the ``hdist`` command-line tool and the
``hashdist`` Python package are not part of the software stack the
distribution provides (unless rebranded).  If you put an old, outdated
profile in ``$PATH``, the ``hdist`` command found in it will simply
read ``~/.hashdistconfig`` and then launch a newer version of
``hdist``. (However, ``qsnake-hdist`` is free to behave however it
likes.)

The best way of distributing Hashdist is in fact to get it through the
operating system package manager. In that case, ``~/.hashdistconfig``
will point to ``/usr/bin/hdist``. Alternatively, a
bootstrapping solution is provided and recommended which make sure that each
distribution using a non-rebranded Hashdist use the same one.

Layers
======

Hashdist consists of two (eventually perhaps three) layers. The idea
is to provide something useful for as many as possible. If a
distribution only uses the the *core layer* (or even only some of the
components within it) it can keep on mostly as before, but get a
performance boost from the caching aspect.  If the distribution wants
to buy into the greater Hashdist vision, it can use the *profile
specification layer*.  Finally, for end-users, a final user-interface
layer is needed to make things friendly.  In this latter area Hashdist
will probably remain silent for some times, but some standards and
best practices may emerge. For now, a user interface ideas section is
included below.


.. toctree::
   :maxdepth: 2
   
   core
   profilespec
   uiideas
