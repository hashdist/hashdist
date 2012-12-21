.. _FAQ:

FAQ
===

Is Hashdist Python-specific?
----------------------------

Hashdist uses Python as its implementation language, and the initial
users will come from that community, but there's nothing
Python-specific about the core layer of Hashdist.


Why not Debian/RedHat/Gentoo?
-----------------------------

Our own motivation for working on Hashdist is HPC clusters. In that
case you never have root access, you cannot change the OS
distribution. Even if you could, the OS distribution is selected by
looking at system stability and performance, not a huge up-to-date
package selection.

Well, why not Gentoo Prefix?
----------------------------

Gentoo Prefix may make sense for very many users. Speaking for
ourselves, we want a more powerful core system, while we don't need
that many available packages.

The main point is to be able to practically manage the combinatorial
explosion of 20 slightly different versions of NumPy with 20 slightly
different versions of Pandas with 5 different LAPACK versions compiled
with 3 different sets of compiler flags, and jump seamlessly between
them.

The goal is to have the flexibility of ``git`` applied to a stack of
built software. Although done in a smarter way than putting ``/usr`` under
git control, the idea is somewhat the same.


Well, why not Nix (or Guix)?
----------------------------

In contrast, Nix (http://nixos.org) *does* support quickly switching
between software stacks. Hashdist is *very* much in debt to the Nix
project and Eelco Dolstra.  Nearly all of the ideas come straight out
of Nix.

The reasons for starting development of Hashdist instead of using the
much more mature Nix is that Nix is very focused on 100% perfect
reproducability. Therefore the default set of packages, *Nixpkgs*,
relies on building its own ``libc``, meaning using Nix software and
host software together in the same process doesn't work.

This directly contradicts our goals with Hashdist. We want to have
a smooth transition between software that is already present on the
host, and software each user builds her-/himself.

The core Nix tool is separate from Nixpkgs, but a) Nix-the-tool is
very much shaped by the philosophy above, and b) we do not want to
maintain a parallel Nix package ecosystem, or in fact create or own
package ecosystem at all. Instead, we hope to create something that
can be used together with one or more of the existing software
distributions. The top priority are the scientific Python
distributions, however it is a goal that it should at least be
possible in theory to do things like build Gentoo Prefix packages
using Hashdist (though that may be prove too much work to happen in
practice).

Also, Nix is GPL, while Hashdist is BSD. And the important thing about
Nix is really the fundamental ideas, rather than the code.
As the Google Summer of Code FAQ states: *"That's fine, a little
duplication is par for the course in open source."*

We're not aware of other hash-based/functional software administration
tools than Nix and Hashdist. Guix uses Nix under the hood.

What's the relationship with non-root software distributions?
-------------------------------------------------------------

Hashdist is not a software distribution in itself, but rather a
"meta-distribution" or distribution framework. It
provides enough features that power-users may use it directly, however
we expect that in typical use it will be rebranded and expanded on
to provide a more user-friendly solution. If all goes (very) well, the current
scientific Python distributions may all live side by side using Hashdist
underneath. The ways in which you download, select and configure
packages in each of these distribution systems will necesarrily be
different, and that is the intention: To allow flexible
experimentation on the front-end side, and cater for the specific
needs of different userbases.



What's the relationship with the Python packaging mess?
-------------------------------------------------------

It's commonly acknowledged that packaging of Python software
has...challenges (to put it very mildly). However, that is a different
problem domain. Hashdist is trying to be "the Debian of choice for
cases where Debian technology doesn't work". Debian needs to package
Python software too.

The two interact to some degree because the weaknesses in the
packaging of Python software must be worked around on the distribution
level. But we are *not* proposing that when writing a Python package
you should care more about Hashdist than Debian or Windows.

The best way for Pythonistas to think about Hashdist may be
a more powerful hybrid of virtualenv and buildout.
