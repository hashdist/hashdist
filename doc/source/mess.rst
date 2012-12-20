Messy details of package building
=================================

Relative RPATH -- $ORIGIN
-------------------------

Passing through the string "$ORIGIN" to the linker can be a real pain
because of the ``$`` character. This worked on HDF5: ``\$$ORIGIN``.
The reason:

 * LDFLAGS is emitted straight from environment to Makefile; ``make``
   interprets ``$$`` as the escape sequence for ``$``

 * When linking, ``src/Makefile`` uses ``$(LINK)``, which uses ``$(LIBTOOL)``,
   which is defined as ``$(SHELL) path/to/libtool``. This means that commands
   with ``$(LINK)`` in them will be interpreted by ``$(SHELL)``, that is ``/bin/bash``,
   and so we need the extra backslash.

