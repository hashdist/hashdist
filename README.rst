HashDist
========

**Home Page**:
    https://hashdist.github.io/

**Docs**:
    http://hashdist.readthedocs.org/

**Tutorial:**
    http://hashdist.readthedocs.org/en/latest/tutorial.html

**Code:**
    https://github.com/hashdist/hashdist

**Mailing list:**
    https://groups.google.com/forum/?fromgroups#!forum/hashdist

**HashStack (Packages and Profiles for HashDist):**
    https://github.com/hashdist/hashstack/

**Wiki:**
    https://github.com/hashdist/hashdist/wiki

**Command-line Help:**
    ``hit help`` or ``hit help <command>``

**Authors:**
    Aron Ahmadia,
    Volker Braun,
    Ondrej Certik,
    Chris Kees,
    Fernando Perez,
    Dag Sverre Seljebotn,
    Andy Terrel

**Funding:**
    HashDist is partially funded by the International Research Office,
    US Army Engineer Research and Development Center, BAA contract
    W911NF-12-1-0604

Note: ``master`` is the development branch.

Copyright and license
---------------------

Copyright (c) 2012-2015, HashDist Developers. All rights
reserved.

HashDist is licensed under the BSD 3-clause license. See LICENSE.txt
for full details.

Since HashDist is used as a standalone installation tool, some very small
dependencies are bundled under ``hashdist/deps``. The copyright of these belong to the
respective authors; the licenses are included in LICENSE.txt.

 * argparse
     * version: 1.2.1

 * jsonschema
     * version: 2.1.0
     * author: Julian Berman
     * license: MIT
     * github: https://github.com/Julian/jsonschema

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
 * distlib
     * location: hashdist/deps/distlib
     * version: commit 5e64fd139851
     * authors: see distlib-CONTRIBUTORS.txt
     * homepage: https://bitbucket.org/vinay.sajip/distlib
