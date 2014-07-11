Installing HashDist for use in software distributions
=====================================================

Dependencies
------------

HashDist depends on Python 2.6+.

A bootstrap script should be made to facilitate installation everywhere...

Bundling vs. sharing
--------------------

HashDist (by which we mean both the library/programs and the source
and build artifact directories on disk) can either be shared between
distributions or isolated; thus one may have build artifacts
in ``~/.hashdist`` which are shared between PyHPC and QSnake, while
Sage has its own HashDist store in ``~/path/to/sage/store``.

.. note::
    
    The main point of sharing HashDist is actually to share it
    between different versions of the same distribution; i.e., two
    different QSnake versions may be located in different paths on disk,
    but if they use the global HashDist they will share the build
    artifacts they have in common.

    Another advantage is simply sharing the source store among
    distributions which build many of the same source tarballs
    and git repos.


Managing conflicting HashDist installations
-------------------------------------------

By default, HashDist core tools are exposed through the ``hit``
command and the ``hashdist`` Python package. It is configured through
``~/.hitconfig``::

    [hashdist]
        hit = ~/.hashdist/bin/hit
        python2-path = ~/.hashdist/lib/python2

    [sources]
        store = ~/.hashdist/source
        keep-transient = 1 week
        keep-targz = forever
        keep-git = forever

    <...>

If a software distribution bundles its own isolated HashDist
environment then the ``hit`` command should be rebranded (e.g.,
``qsnake-hit``), and it should read a different configuration
file. Similarly, the Python package should be rebranded (e.g.,
``qsnake.hashdist``).

The command ``hit`` should *always* read ``~/.hitconfig`` (or
the configuration file specified on the command line) and launch the
command found there under the `hit` key. Similarly, ``import
hashdist`` should add the package from the location specified in the
configuration file to ``sys.path`` and then do ``from hashdistlib
import *``.  The reason is simply that the paths mentioned in that
file are managed by a particular version of hashdist, and we want an
upgrade path. Essentially, the ``hit`` command-line tool and the
``hashdist`` Python package are not part of the software stack the
distribution provides (unless rebranded).  If you put an old, outdated
profile in ``$PATH``, the ``hit`` command found in it will simply
read ``~/.hitconfig`` and then launch a newer version of
``hit``. (However, ``qsnake-hit`` is free to behave however it
likes.)

The best way of distributing HashDist is in fact to get it through the
operating system package manager. In that case, the `hit` key in ``~/.hitconfig``
will point to ``/usr/bin/hit``. Alternatively, a
bootstrapping solution is provided and recommended which make sure that each
distribution using a non-rebranded HashDist use the same one.



Bootstrap script
----------------

TODO
