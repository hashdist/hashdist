===============================================
The Cloud Sphinx Theme
===============================================

This is release |release| of a small Python package named
:mod:`!cloud_sptheme`. It contains a `Sphinx <http://sphinx.pocoo.org/>`_ theme
named "Cloud", and some related Sphinx extensions. Cloud and its extensions
are primarily oriented towards generating html documentation for Python libraries.
It provides numerous small enhancements to make the html documentation html more interactive,
improve the layout on mobile devices, and other enhancements.

Contents
========

Themes
------
:doc:`Cloud Sphinx Theme <cloud_theme>`
    the main Sphinx theme provided by this package,
    and used by this documentation.

Extensions
----------
The following Sphinx extensions provide features used by the Cloud theme,
and should be enabled for most documentation that uses it:

    :mod:`cloud_sptheme.ext.index_styling`
        Adds additional css styling classes to the index page.

    :mod:`cloud_sptheme.ext.relbar_toc`
        Adds a TOC link to the top navigation controls.

Generic Extensions
------------------
This package also provides a few extra Sphinx extensions which may be useful
when documenting Python projects; and should be theme-agnostic:

    :mod:`cloud_sptheme.ext.autodoc_sections`
        Patches the :mod:`sphinx.ext.autodoc` to handle RST section headers
        inside docstrings.

    :mod:`cloud_sptheme.ext.issue_tracker`
        Adds a special ``:issue:`` role for quickly linking to
        your project's issue tracker.

    :mod:`cloud_sptheme.ext.escaped_samp_literals`
        Patches Sphinx to permit escaped ``{}`` characters within a ``:samp:`` role.

Reference
---------
:doc:`install`
    requirements and installations instructions

:doc:`history`
    history of current and past releases

Online Resources
================

    .. rst-class:: html-plain-table

    ====================== ===================================================
    Homepage:              `<https://bitbucket.org/ecollins/cloud_sptheme>`_
    Online Docs:           `<http://packages.python.org/cloud_sptheme>`_
    Download & PyPI:       `<http://pypi.python.org/pypi/cloud_sptheme>`_
    ====================== ===================================================
