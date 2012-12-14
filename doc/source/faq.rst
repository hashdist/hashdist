FAQ
===

Is Hashdist Python-specific?
----------------------------

Hashdist uses Python as its implementation language, and the initial
users will come from that community, but there's nothing
Python-specific about the core layer of Hashdist.


What's the relationship with software distributions?
----------------------------------------------------

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
