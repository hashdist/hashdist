Specifying a HashDist software profile
======================================

There are specification file types in HashDist.  The *profile spec*
describes *what* to build; what packages should be included in the
profile and the options for each package. A *package spec* contains
the *how* part: A (possibly parametrized) description for building a
single package.

The basic language of the specification files is YAML, see
http://yaml.org.  Style guide: For YAML files within the HashDist
project, we use 2 space indents, and no indent before
vertically-formatted lists (as seen below).

Profile specification
---------------------

The profile spec is what the user points the `hit` tool to to build a profile.
By following references in it, HashDist should be able to find all the information
needed (including the package specification files). An example end-user profile
might look like this::

    extends:
    - name: hashstack
      urls: ['https://github.com/hashdist/hashstack.git']
      key: 'git:5042aeaaee9841575e56ad9f673ef1585c2f5a46'
      file: debian.yaml

    - file: common_settings.yaml

    parameters:
      debug: false

    packages:
      zlib:
      szlib:
      nose:
      python:
        host: true
      mpi:
        use: openmpi
      numpy:
        skip: true

    package_dirs:
    - pkgs
    - base

    hook_import_dirs:
    - base

**extends**:

  Profiles that this profile should extend
  from. Essentially this profile is merged on a parameter-by-parameter
  and package-by-package basis. If anything conflicts there is an
  error. E.g., if two base profiles sets the same parameter, the
  parameter must be specified in the descendant profile, otherwise it
  is an error.

  There are two ways of importing profiles:

  * **Local**: Only provide the **file** key, which can be an absolute
    path, or relative to the directory of the profile spec file.

  * **Remote**: If **urls** (currently this must be a list of length
    one) and **key** are given, the specified sources (usually a git
    commit) will be downloaded, and the given **file** is relative to
    the root of the repo. In this case, providing a **name** for the
    repository is mandatory; the name is used to refer to the
    repository in error messages etc., and must be unique for the
    repository across all imported profile files.


**parameters**:

  Global parameters set for all packages.  Any
  parameters specified in the **packages** section will override these
  on a per-package basis.

  Parameters are typed as is usual for YAML documents; variables will
  take the according Python types in expressions/hooks. E.g., ``false``
  shows up as `False` in expressions, while ``'false'`` is a string
  (evaluating to `True` in a boolean context).

**packages**:

  The packages to build. Each package is given as a key in a dict,
  with a sub-dict containing package-specific parameters.  This is
  potentially empty, which means "build this package with default
  parameters". If a package is not present in this section (and is not
  a dependency of other packages) it will not be built.  The **use**
  parameter makes use of a different package name for the package
  given, e.g., above, package specs for ``openmpi`` will be searched
  and built to satisfy the ``mpi`` package. The **skip** parameter
  says that a package should *not* be built (which is useful in the
  case that the package was included in an ancestor profile).

**package_dirs**:

  Directories to search for package specification files (and hooks,
  see section on Python hook files below). These acts in an "overlay"
  manner. In the example above, if one e.g., if searching for
  ``python_package.yaml`` then first the ``pkgs`` sub-directory
  relative to the profile file will be consulted, then ``base``,
  and finally any directories listed in **package_dirs**
  in the base profiles extended in **extends**.

  This way, one profile can override/replace the package specifications
  of another profile by listing a directory here.

  The common case is that base profiles set **package_dirs**, but that
  overriding user profiles do not have it set.

**hook_import_dirs**:

  Entries for ``sys.path`` in Python hook files. Relative to the
  location of the profile file.


Package specifications
----------------------

Below we assume that the directory ``pkgs`` is a directory listed in
**package_dirs** in the profile spec. We can then use:

 * Single-file spec: ``pkgs/mypkg.yaml``
 * Multi-file spec: ``pkgs/mypkg/mypkg.yaml``, ``pkgs/mypkg/somepatch.diff``,
   ``pkgs/mypkg/mypkg-linux.yaml``

In the latter case, all files matching ``mypkg/mypkg.yaml`` and
``mypkg/mypkg-*.yaml`` are loaded, and the **when** clause evaluated
for each file. An error is given if more than one file matches the
given parameters. One of the files may lack the **when** clause
(conventionally, the one without a dash and a suffix), which
corresponds to a default fallback file.

Also, HashDist searches in the package directories for ``mypkg.py``,
which specifies a Python module with hook functions that can further
influence the build. Documentation for the Python hook system is TBD,
and the API tentative. Examples in ``base/autotools.py`` in the
Hashstack repo.

Examples of package specs are in https://github.com/hashdist/hashstack, and
we will not repeat them here, but simply list documentation on each clause.

In strings; ``{{param_name}}`` will usually expand to the parameter in
question while assembling the specification needed, and are expanded
before artifact hashes are computed. Expansions of the form ``${FOO}``
are expanded at build-time (by the HashDist build system or the shell,
depending on context), and the variable name is what is hashed.


**when**:

  Conditions for using this package spec, see rules above.  It is a
  Python expression, evaluated in a context where all parameters are
  available as variables

**extends**:

  A list of package names. The package specs for these *base packages* will
  be loaded and their contents included, as documented below.

**sources**:

  Sources to download.  This should be a list of ``key`` and ``url``
  pairs.  To generate the ``key`` for a new file, use the ``hit
  fetch`` command.

**dependencies**:

  Lists of names for packages needed during build (**build**
  sub-clause) or in the same profile (**run**
  sub-clause). Dependencies from base packages are automatically
  included in these lists, e.g., if ``python_package`` is listed in
  **extends**, then ``python_package.yaml`` may take care of requiring
  a build dependency on Python.

**build_stages**:

  Stages for the build. See Stage system section below for general
  comments. The build stages are ordered and then executed to produce
  a Bash script to run to do the build; the **handler** attribute (which
  defaults to the value of the **name** attribute) determines the
  format of the rest of the stage.

**when_build_dependency**:

  Environment variable changes to be done when this package is a build
  dependency for *another* package. As a special case variable ``${ARTIFACT}``

**profile_links**:

  A small DSL for setting up links when building the profile. What
  links should be created when assembling a profile. (In general this
  is dark magic and subject to change until documented further, but
  usually only required in base packages.)


Conditionals
------------

The top-level **when** in each package spec has already been mentioned.
In addition, there are two forms of local conditionals withi a file.
The first one can be used within a list-of-dicts, e.g., in **build_stages**
and similar sections::

    - when: platform == 'linux'
      name: configure
      extra: [--with-foo]

    - when: platform == 'windows'
      name: configure
      extra: [--with-bar]

The second form takes the form of a more traditional if-test::

    - name: configure
      when platform == 'linux':
          extra: [--with-foo]
      when platform == 'windows':
          extra: [--with-bar]
      when platform not in ('linux', 'windows'):
          extra: [--with-baz]

The syntax for conditional list-items is a bit awkward, but available
if necesarry::

    dependencies:
      build:
        - numpy
        - when platform == 'linux':  # ! note the dash in front
          - openblas
        - python

This will turn into either ``[numpy, python]`` or ``[numpy, openblas,
python]``.  The "extra" ``-`` is needed to maintain positioning within
the YAML file.


Stage system
------------

The **build_stages**, **when_build_dependency** and **profile_links** clauses
all follow the same format: A list of "stages" that are partially ordered
(using **name**, **before**, and **after** attributes). Thus one can inherit
a set of stages from the base packages, and only override the stages one needs.

There's a special **mode** attribute which determines how the override
happens. E.g.,::

  - name: configure
    mode: override  # !!
    foo: bar

will pass an extra ``foo: bar`` attribute to the configure handler, in
addition to the attributes that were already there in the base
package. This is the default behaviour. On the other hand,::

  - name: configure
    mode: replace  # !!
    handler: bash
    bash: |
        ./configure --prefix=${ARTIFACT}

entirely replaces the configure stage of the base package. 

The ``update`` mode will update dictionaries and lists within a stage,
so it can be helpful for building up a set of actions for a given
stage,::

    - name: configure
       append: {overriden_value: "1", a_key: "a"}
       extra: ['--shared']
    - name: configure
      mode: update
      append: {overriden_value: "2", b_key: "b"}
      extra: ['--without-ensurepip']

is equivalent to,::

    - name: configure
      append: {overriden_value: "2", a_key: "a", b_key: "b"}
      extra: ['--shared', '--without-ensurepip']

Finally,::

  - name: configure
    mode: remove  # !!

removes the stage.
