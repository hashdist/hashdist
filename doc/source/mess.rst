Messy details of package building
=================================

Relocateable artifacts
----------------------

$ORIGIN in RPATH
''''''''''''''''

In the end, this is almost impossible because whenever one uses the
configure system, e.g., ``--with-szlib`` on HDF, it tends to add the
absolute RPATH anyway, and any relative paths one manage to put in
ends up after. The only viable solution seems to be after-the-fact
patching from absolute to relocateable.

Below some notes if one actually wants to do it:

Passing through the string "$ORIGIN" to the linker can be a real pain
because of the ``$`` character. This worked on HDF5: ``\$$ORIGIN``.
The reason:

 * LDFLAGS is emitted straight from environment to Makefile; ``make``
   interprets ``$$`` as the escape sequence for ``$``

 * When linking, ``src/Makefile`` uses ``$(LINK)``, which uses ``$(LIBTOOL)``,
   which is defined as ``$(SHELL) path/to/libtool``. This means that commands
   with ``$(LINK)`` in them will be interpreted by ``$(SHELL)``, that is ``/bin/bash``,
   and so we need the extra backslash.

