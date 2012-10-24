.. index:: cloud; installation

=========================
Installation Instructions
=========================

Requirements
============
* Python >= 2.5 or Python 3
* `Sphinx <http://sphinx.pocoo.org/>`_ 1.1 or newer.

Installing
==========
* To install from pypi using pip::

   pip install cloud_sptheme

* To install from pypi using easy_install::

   easy_install cloud_sptheme

* To install from source using ``setup.py``::

    python setup.py build
    sudo python setup.py install

.. index:: readthedocs.org; installation on

ReadTheDocs
===========
To use this theme on `<http://readthedocs.org>`_:

1. If it doesn't already exist, add a ``requirments.txt`` to your documentation (e.g. alongside ``conf.py``).

2. Make sure the file contains the line ``cloud_sptheme`` (along with any other
   build requirements your documentation has, if applicable).

3. When setting up your project on ReadTheDocs, enter the path to ``requirements.txt``
   in the *requirements file* field.

4. ReadTheDocs will automatically download the latest version of this theme
   when building your documentation.

Documentation
=============
The latest copy of this documentation should always be available at:
    `<http://packages.python.org/cloud_sptheme>`_

If you wish to generate your own copy of the documentation,
you will need to:

1. install `Sphinx <http://sphinx.pocoo.org/>`_ (1.1 or better)
2. download the :mod:`!cloud_sptheme` source.
3. install :mod:`!cloud_sptheme` itself.
4. from the source directory, run ``python docs/make.py clean html``.
5. Once Sphinx is finished, point a web browser to the file :samp:`{SOURCE}/docs/_build/html/index.html`.
