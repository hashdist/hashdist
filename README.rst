Hashdist
========

Note: ``master`` is the development branch.

The ``stable`` branch contains the latest release (currently 0.1).

**Docs**:
    http://hashdist.readthedocs.org/

**Tutorial:**
    http://hashdist.readthedocs.org/en/latest/tutorial.html

**Code:**
    https://github.com/hashdist/hashdist

**Mailing list:**
    https://groups.google.com/forum/?fromgroups#!forum/hashdist

**Authors:**
    Dag Sverre Seljebotn,
    Ondrej Certik,
    Chris Kees

**Funding:**
    Hashdist is partially funded by the International Research Office,
    US Army Engineer Research and Development Center, BAA contract
    W911NF-12-1-0604



Copyright and license
---------------------

Copyright (c) 2012, Dag Sverre Seljebotn and Ondrej Certik. All rights
reserved.

Hashdist is licensed under the BSD 3-clause license. See LICENSE.txt
for full details.

Since Hashdist is used as the installation tool, some very small
dependencies are simply ripped out of the original projects and
bundled under ``hashdist/deps``. The copyright of these belong to the
respective authors; the licenses are included in LICENSE.txt.

 * sh
     * location: hashdist/deps/sh:
     * version: commit abb0ba6
     * main author: Andrew Moffat
     * license: MIT
     * homepage: https://github.com/amoffat/sh

 * PyYAML
     * location: hashdist/deps/yaml
     * version: 3.10
     * main author: Kirill Simonov
     * license: MIT
     * homepage:  https://bitbucket.org/xi/pyyaml/
     * additional patches: (see git log on hashdist/deps/yaml):
        * http://pyyaml.org/ticket/128
