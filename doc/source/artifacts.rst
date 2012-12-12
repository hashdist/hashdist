Build artifacts
===============


Artifact IDs
------------

A Hashdist artifact ID has the form ``name/version/hash``, where

 * `name` is a descriptive name for the package ("numpy")
 * `version` describes the specific build in human-friendly terms;
   this may be a simple version number (``1.2-beta``) or something
   more descriptive (``1.2-beta-intel-openblas-avx``). For simplicity
   we require this to always be present; by convention set it to ``n`` for
   "does not apply" or ``dev`` for "not released yet".
 * `hash` is a cryptographic hash of the build specification



Short form
''''''''''

For the artifact paths on disk, a shortened form (4-char hash) is used
to make things more friendly to the human user. If there is a
collision, the length is simply increased for the one that comes
later. Hashdist will never use these to resolve build artifacts, so
collision problems come in two forms:

 * Automatically finding the list of run-time dependencies from the
   build dependencies. In this case one scans the artifact directory
   only for the build dependencies (less than hundred). It then makes
   sense to consider the chance of finding one exact string
   ``aaa/0.0/ZXa3`` in a random stream of 8-bit bytes, which helps
   collision strength a lot, with chance "per byte" in the artifact of a
   collision on the order :math:`2^{-(8 \cdot 12)}=2^{-96}` for this minimal
   example.

   If this is deemed a problem (the above is too optimistice), one can
   also scan for "duplicates" (other artifacts where longer hashes
   were chosen, since we know these).


 * Binary distributions where you get pre-built artifacts which have
   links to other artifacts embedded, and artifacts from multiple
   sources may collide. In this case it makes sense to increase the
   hash lengths a bit (though one could still track and explicitly warn
   on error, assuming the pre-built artifacts declare the full length
   hashes).



