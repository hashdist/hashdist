User's guide to Hashdist
========================

Installing and making the `hit` tool available
----------------------------------------------

Hashdist requires Python 2.7 and git.

To start using Hashdist, clone the repo that contains the core tool, and put
the ``bin``-directory in your ``PATH``::

    $ git clone https://github.com/hashdist/hashdist.git 
    $ cd hashdist
    $ export PATH=$PWD/bin:$PATH

The ``hit`` tool should now be available. You should now run the following command to
create the directory ``~/.hashdist``::

    $ hit init-home

By default all built software and downloaded sources will be stored
beneath ``~/.hashdist``.  To change this, edit
``~/.hashdist/config.yaml``.

Setting up your software profile
--------------------------------

Using Hashdist is based on the following steps:

 1) First, describe the software profile you want to build in a configuration file ("I want Python, NumPy, SciPy").

 2) Use a dedicated git repository to manage that configuration file

 3) For every git commit, Hashdist will be able to build the specified
    profile, and *cache* the results, so that you can jump around in
    the history of your software profile.

Start with cloning a basic user profile template::

    git clone https://github.com/hashdist/profile-template.git /path/to/myprofile

The contents of the repo is a single file ``default.yaml`` which a)
selects a *base profile* to extend, and b) lists which packages to
include.  It is also possible to override build parameters from this
file, or link to extra package descriptions within the repository
(docs not written yet).  The idea is to modify this repository to make
changes to the software profile that only applies to you. You are
encouraged to submit pull requests against the base profile for
changes that may be useful to more users.

To build the stack, simply do::

    cd /path/to/myprofile
    hit build

This will take a while, including downloading the source code needed.
In the end, a symlink ``default`` is created which contains the exact
software described by ``default.yaml``.

Now, try to remove the ``jinja2`` package from ``default.yaml`` and do
``hit build`` again. This time, the build should only take a second,
which is the time used to assemble a new profile.

Then, add the ``jinja2`` package again and run ``hit build``. This
exact software profile was already built, and so the operation is very
fast.

When coupled with managing the profile specification with git, this
becomes very powerful, as you can use git to navigate the history of
or branches of your software profile repository, and then instantly switch to
pre-built versions. [TODO: ``hit commit``, ``hit checkout`` commands.]

If you want to have, e.g., release and debug profiles,
you can create ``release.yaml`` and ``debug.yaml``, and use the
``-p`` flag to ``hit`` to select another profile than ``default.yaml``
to build.

Garbage collection
------------------

Hashdist does not have the concepts of "upgrade" or "uninstall", but
simply keeps everything it has downloaded or built around forever. To
free up disk space, you may invoke the garbage collector to remove
unused builds.

Currently the garbage collection strategy is very simple: When you
invoke garbage collection manually, Hashdist removes anything that
isn't currently in use. To figure out what that means, you may invoke
``hit gc --list``; continueing on the example from above, we
would find::

    $ hit gc --list
    List of GC roots:
    /path/to/myprofile/default

This indicates that if you run a plain ``hit gc``, software accessible
through ``/path/to/myprofile/default`` will be kept, but all other builds
will be removed from the Hashdist store. To try it, you may comment out
the ``zlib`` line from ``default.yaml``, then run ``hit build``, and
then ``hit gc`` -- the zlib software is removed at the last step.

If you want to manipulate profile symlinks, you should use the ``hit
cp``, ``hit mv``, and ``hit rm`` commands, so that Hashdist can
correctly track the profile links. This is useful to keep multiple
profiles around. E.g., if you first execute::

    hit cp default old_profile

and then modify ``default.yaml``, and then run ``hit build``,
then after the build ``default`` and ``old_profile`` will point
to different revisions of the software stacks, both usable at the
same time. Garbage collection will keep software for either around.

The database of GC roots is kept (by default) in
``~/.hashdist/gcroots``.  You are free to put your own symlinks there
(you may give them an arbitrary name, as long as they do not contain
an underscore in front), or manually remove symlinks.

.. warning::

   As a corollary to the description above, if you do a plain
   ``mv`` of a symlink to a profile, and then execute ``hit gc``,
   then the software profile may be deleted by Hashdist.


Debug features
--------------

A couple of commands allow you to see what happens when building.

* Show the script used to build Jinja2::

    hit show script jinja2

* Show the "build spec" (low-level magic)::

    hit show buildspec jinja2

* Get a copy of the build directory that would be used::

    hit bdir jinja2 bld

This extracts Jinja2 sources to ``bld``, puts a Bash build-script in
``bld/_hashdist/build.sh``. However, if you go ahead and try to run it
the environment will not be the same as when Hashdist builds, so this
is a bit limited so far. [TODO: ``hit debug`` which also sets the right
environment and sets the ``$ARTIFACT`` directory.]


Developing the base profile
---------------------------

If you want to develop the ``hashstack2`` repository yourself, using a
dedicated local-machine profile repo becomes tedious. Instead, copy
the ``default.example.yaml`` to ``default.yaml``. Then simply run
``hit build`` directly in the base profile (in which case the personal
profile is not needed at all).

``default.yaml`` is present in ``.gitignore`` and changes should not
be checked in; you freely change it to experiment with whatever
package you are adding. Note the orthogonality between the two
repositories: The base profile repo has commits like "Added build
commands for NumPy 1.7.2 to share to the world".  The personal profile
repo has commits like "Installed the NumPy package on my computer".

Further details
---------------

:doc:`specs`
