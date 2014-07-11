Guidelines for packaging/building
=================================

HashDist can be used to build software in many ways. This document
describes what the HashDist authors recommend and the helper tools
available for post-processing.

Principles
----------

 * Build artifacts should be *fully relocatable*, simply because we
   can, and it is convenient. In particular it means we can avoid
   adding complexity (an extra post-processing phase) for binary
   artifacts.

 * It should be possible to use the software with as few environment
   variable modifications as possible. I.e., one should be able to do
   ``path/to/profile/bin/program`` without any changes to environment
   variables at all, and a typical setup would only modify ``$PATH``.


Relocatable artifacts
----------------------

Relocatability is something that must be dealt with on a case-by-case
basis.

Artifact relative references
''''''''''''''''''''''''''''

For relative artifacts to work (at least without serious patching of all
programs involved...), it is currently necesarry to insist that all build artifacts
involved are in the sub-directory/partition, so that relative paths such
as ``../../../python/34ssdf32/lib/..`` remain valid.

.. note::
    
    *Considering the future:* If multiple artifact dirs are needed,
    a possibility for splitting up build artifact repositories would
    be to symlink between them at the individual artifact level, say::

        /site/hit/zlib/afda/...
        /site/hit/python/fdas/...
    
    And then another artifact directory could contain::

        /home/dagss/.hit/opt/zlib/afda -> /site/hit/zlib/afda
        /home/dagss/.hit/opt/python/fdas -> /site/hit/python/fdas
        /home/dagss/.hit/opt/pymypackage/3dfs/...
    
    Because artifacts should be a DAG this should work well.  This
    could be naturally implemented as whenever a cached build artifact
    is found on a locally available filesystem, symlink to it.

    Of course, now ``/site/hit`` is *not* relocatable, but mere
    rewriting of those symlinks, always at the same level in the
    filesystem, is a lot more transparent than full post-processing of
    artifacts.

Unix: Scripts
'''''''''''''

The shebang lines ``#!/usr/bin/env interpreter`` or
``#!/full/path/to/interpreter`` are limited and preclude
relocatability by themselves. We deal with this by using `multi-line
shebangs <http://rosettacode.org/wiki/Multiline_shebang>`_.

We want to search for interpreters for scripts as follows:

 * In the ``bin``-dir of the profile in use (typically, but not always, along-side
   the script). We define this as: For each symlink in the chain between
   ``$0`` and the real script file, search upwards towards the root for a
   file named ``profile.json``. If found, find the interpreter (by its base name)
   in the ``bin``-subdirectory.

 * Otherwise, fall back to the *relative* path between the real location of the
   script file and the interpreter's build artifact. (E.g., for Python, this could
   work if ``PYTHONPATH`` is also set correctly, as may be the case during
   builds.)

**Example**: The command::

    $ hit build-postprocess --shebang=multiline path-or-script

applies the multiline shebang. Test script::

    #!/tmp/../usr/bin/python

    """simple example"""

    print 'Hello world'

Note that shebangs with ``/usr/bin/*`` is not processed, so we had to
force the tool to kick in using ``/tmp/../usr/bin/`` (because the
intention is really just to patch references to other artifacts). Then
calling the command above yields::

    #!/bin/sh
    # -*- mode: python -*-
    "true" '''\';r="../../../../usr/bin";i="python";o=`pwd`;p="$0";while true; do test -L "$p";il=$?;cd `dirname "$p"`;pdir=`pwd -P`;d="$pdir";while [ "$d" != / ]; do [ -e profile.json ]&&cd "$o"&&exec "$d/bin/$i" "$0" "$@";cd ..;d=`pwd -P`;done;cd "$pdir";if [ "$il" -ne 0 ];then break;fi;p=`readlink $p`;done;cd "$r";p=`pwd -P`;cd "$o";exec "$p/$i" "$0" "$@";exit 127;
    ''' # end multi-line shebang, see hashdist.core.build_tools

    __doc__ = """simple example"""

    print 'Hello world'
    # vi: filetype=python

This file is executable both using Python 2.x or a POSIX shell.  See
the code of :mod:`hashdist.core.build_tools` for the shell script in a
non-compacted form with comments. Note the ``r`` and ``i`` variables;
``../../../../usr/bin`` was simply the relative path between the
example script and ``/usr/bin`` when the command was run.


Unix: Dynamic libraries
'''''''''''''''''''''''

Modern Unix platforms allows binaries to link to dynamic libraries in
relative locations by using an RPATH containing the string
``${ORIGIN}``. See ``man ld.so`` (on Linux at least).

Passing this is almost impossible because whenever one uses the
configure system it tends to add the absolute RPATH anyway. Also,
the contortions one must go through to properly escape the magic
string (``$`` unfortunately being part of it) is build-system specific,
for autoconf with libtool it is ``\$$ORIGIN``, where first Make sees
``$$``, and then Bash sees ``\$``.

Fortunately, for Linux there is `patchelf <http://nixos.org/patchelf.html>`_
and for Mac OS X [another tool].
