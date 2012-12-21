Installing Hashdist for use in software distributions
=====================================================

Dependencies
------------

Hashdist depends on Python 2.6+.

A bootstrap script should be made to facilitate installation everywhere...

Bundling vs. sharing
--------------------

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

    Another advantage is simply sharing the source store among
    distributions which build many of the same source tarballs
    and git repos.


Managing conflicting Hashdist installations
-------------------------------------------

By default, Hashdist core tools are exposed through the ``hdist``
command and the ``hashdist`` Python package. It is configured through
``~/.hashdistconfig``::

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
operating system package manager. In that case, the `hdist` key in ``~/.hashdistconfig``
will point to ``/usr/bin/hdist``. Alternatively, a
bootstrapping solution is provided and recommended which make sure that each
distribution using a non-rebranded Hashdist use the same one.



Bootstrap script
----------------

TODO
