User's guide to Hashdist v. 0.2
===============================

Installing and making the `hit` tool available
----------------------------------------------

Hashdist requires Python 2.7 and git.

To start using Hashdist, clone the repo that contains the core tool, and put
the ``bin``-directory in your ``PATH``::

    $ git clone https://github.com/hashdist/hashdist.git /path/to/hashdist
    $ export PATH=/path/to/hashdist/bin:$PATH

The ``hit`` tool should now be available. You should now run the following command to
create the directory ``~/.hashdist``::

    $ hit init-home

By default all built software and downloaded sources will be stored
beneath ``~/.hashdist``.  To change this, edit
``~/.hashdist/config.yaml``.

Setting up your software profile
--------------------------------

Using Hashdist is based on the following steps:

 1) First, *describe* the software profile you want to build in a configuration file ("I want Python, NumPy, SciPy").
 2) Use a dedicated git repository to manage that configuration file
 3) For every git repository, 

Start with cloning a basic user profile template::

    git clone https://github.com/hashdist/profile-template.git /path/to/myprofile

