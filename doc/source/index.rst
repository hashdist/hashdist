Welcome to the Hashdist documentation
=====================================

Hashdist is an in-progress **library for building non-root software
distributions**.


We want to make maintaining software stacks more like using git, with
the ability to jump to another stack of software in seconds.

To do this, we focus on a declarative approach: You always specify a
full distribution that you want in a set of configuration files, then
do a full rebuild (from source) in order for changes to be
reflected. However, builds are cached under an associated hash
reflecting the entire build environment, so that a "full rebuild" is
often very fast.

See the :ref:`FAQ` for more details on Hashdist compared to other projects.

.. note::
    If you consider yourself an end-user of software
    distributions, you have come to the wrong place. This
    documentation is mainly useful for developers of software
    distributions, such as *python-hpcmp*.

Guide
------------

.. toctree::
   :maxdepth: 1

   build_spec
   
   building

.. faq

Hashdist API reference
----------------------


Important concepts
''''''''''''''''''

.. toctree::
   :maxdepth: 1

   core/source_cache
   core/build_store
   core/run_job
   core/profile

Support code
''''''''''''

.. toctree::
   :maxdepth: 1

   core/hasher
   core/links
   core/ant_glob

