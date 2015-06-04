import mock
import logging
from pprint import pprint
from os.path import join as pjoin
from textwrap import dedent
from ...core.test.utils import *
from ...core.test.test_build_store import fixture as build_store_fixture
from .. import profile
from .. import package
from .. import package_loader
from .. import hook_api
from ..package import PackageYAML
from ...formats.marked_yaml import marked_yaml_load, yaml_dump
from ..exceptions import ProfileError, PackageError
from nose import SkipTest


null_logger = logging.getLogger('null_logger')


def test_topological_stage_sort():
    stages = [dict(name='z', value='z'),
              dict(name='a', value='a', before=['c', 'b']),
              dict(name='c', value='c'),
              dict(name='b', value='b'),
              dict(name='aa', value='aa', before='c', after='b')]
    stages = package_loader.normalize_stages(stages)
    stages = package_loader.topological_stage_sort(stages)
    assert stages == [{'value': 'a'}, {'value': 'b'}, {'value': 'aa'}, {'value': 'c'}, {'value': 'z'}]

#
# Build script assembly
#
def test_assemble_stages():
    doc = marked_yaml_load("""\
        build_stages:
        - {handler: bash, bash: './configure --with-foo={{foo}} --with-bar={{bar}}'}
        - {handler: bash, bash: make}
        - {handler: bash, bash: make install}
    """)
    ctx = hook_api.PackageBuildContext('mypackage', {}, {'bar': 'othervalue', 'foo': 'somevalue'})
    script = package.assemble_build_script(doc, ctx)
    eq_(script, dedent("""\
        set -e
        export HDIST_IN_BUILD=yes
        ./configure --with-foo=somevalue --with-bar=othervalue
        make
        make install
    """))

def test_create_build_spec():
    doc = marked_yaml_load(dedent("""\
        name: mylib
        sources:
          - git: git://foo
            key: git:a3c39a03e7b8e9a3321d69ff877338f99ebb4aa2
        dependencies:
          build: [otherlib]
          run: [foolib] # should be ignored
        build_stages:
          - {name: make, handler: bash, bash: make}
        post_process:
          - hit: [shebang=multiline, write-protect, remove-pkgconfig]
        when_build_dependency:  # ignored below, only used in build spec of dependency
          - prepend_path: FOO
            value: value-of-FOO
    """))
    parameters = {"X": "x", "BASH": "/bin/bash"}
    imports = [{"ref": "OTHERLIB", "id": "otherlib/abcdefg"}]
    build_spec = package.create_build_spec('mylib', doc, parameters, imports, [])
    expected = {
        "name": "mylib",
        "build": {
            "import": [{"ref": "OTHERLIB", "id": "otherlib/abcdefg"}],
            "commands": [
                {"set": "BASH", "nohash_value": "/bin/bash"},
                {"cmd": ["$BASH", "_hashdist/build.sh"]},
                {'hit': ['build-postprocess', '--shebang=multiline', '--write-protect',
                         '--remove-pkgconfig']}]},
        "sources": [
            {"key": "git:a3c39a03e7b8e9a3321d69ff877338f99ebb4aa2", "target": "."}
            ]}
    eq_(expected, build_spec.doc)



class MockPackageYAML(PackageYAML):

    def __init__(self, filename, doc, hook_filename):
        self.profile = profile
        self.doc = doc
        self.filename = filename
        self.in_directory = False
        self.hook_filename = hook_filename
        self.used_name = filename.replace('.yaml', '')
        self.primary = True

    def copy_with_doc(self, doc):
        return MockPackageYAML(self.filename, doc, self.hook_filename)


class MockProfile(object):

    def __init__(self, files):
        self.parameters = {}
        self.packages = {}
        self.files = dict((name, marked_yaml_load(body)) for name, body in files.items())

    def load_package_yaml(self, name, parameters):
        try:
            filename = name + '.yaml'
            doc = self.files[filename]
        except KeyError:
            return None
        hook = name + '.py'
        if hook not in self.files:
            hook = None
        return MockPackageYAML(filename, doc, hook)

    def load_package(self, name):
        assert isinstance(name, basestring)
        yaml = self.load_package_yaml(name, {})
        return package.Package.create_from_yaml_files(self, [yaml])

    def find_package_file(self, name, filename):
        return filename if filename in self.files else None


@temp_working_dir_fixture
def test_prevent_diamond(d):
    dump('pkgs/a.yaml', 'extends: [b, c]')
    dump('pkgs/b.yaml', 'extends: [d]')
    dump('pkgs/c.yaml', 'extends: [d]')
    dump('pkgs/d.yaml', '{}')
    dump('profile.yaml', """
        package_dirs:
        - pkgs
        packages:
          a:
    """)
    with profile.TemporarySourceCheckouts(None) as checkouts:
        prof = profile.load_profile(null_logger, checkouts, "profile.yaml")
        with assert_raises(PackageError) as e:
            prof.load_package('a')
        assert 'diamond' in str(e.exc_val)

def test_inheritance_collision():
    files = {
        'child.yaml': 'extends: [base1, base2]',
        'base1.yaml': 'build_stages: [{name: stage1}]',
        'base2.yaml': 'build_stages: [{name: stage1}]'}
    prof = MockProfile(files)
    pkg = prof.load_package('child')
    with assert_raises(PackageError) as e:
        pkg.instantiate({})
    assert '"stage1" used as the name for a stage in two separate package ancestors' in str(e.exc_val)


def test_load_and_inherit_package():
    files = {}
    files['mypackage.yaml'] = """\
        extends: [base1, base2]
        dependencies:
          build: [dep1]
          run: [dep1]
        build_stages:

        - name: stage1_override
          # mode defaults to override
          a: 1

        - name: stage3_override
          mode: override
          a: 1

        - name: stage_to_remove
          mode: remove

        - name: stage4_replace
          mode: replace
          a: 1

        - name: stage_2_inserted
          after: stage1_override
          before: stage3_override
          a: 1

        profile_links:
        - name: start
          link: '*/**/*'
        when_build_dependency:
        - name: start
          set: FOO
          value: foovalue
    """

    files['base1.yaml'] = """\
        extends: [grandparent]
        build_stages:
        - random: anonymous
          handler: foo
        post_process:
        - name: post1
          hit: relative-rpath
    """

    files['base2.yaml'] = """\
        dependencies:
          run: [dep_base2_1]
        profile_links:
        - name: end
          after: start
          link: '*/**/*'
        - link: foo  # anonymous stage
        build_stages:
        - {name: stage3_override, after: stage1_override, a: 2, b: 3}
        - {name: stage4_replace, after: stage3_override, a: 2, b: 3}
    """

    files['grandparent.yaml'] = """\
        dependencies:
          build: [dep_gp_1]
        build_stages:
        - {name: stage1_override, a: 2, b: 3}
        - {name: stage_to_remove, after: stage1_override, a: 2, b: 3}
    """

    files['grandparent.py'] = '{}'
    files['base1.py'] = '{}'
    files['mypackage.py'] = '{}'

    prof = MockProfile(files)

    pkg = prof.load_package('mypackage')
    with mock.patch('hashdist.spec.package_loader.PackageLoader.topo_order_stages', lambda self: None):
        loader = package_loader.PackageLoader(pkg, {'param1':'from profile'})

    eq_(set(p.spec.name for p in loader.all_parents), set(['base1', 'base2', 'grandparent']))
    eq_(set(p.spec.name for p in loader.direct_parents), set(['base1', 'base2']))
    eq_(loader.get_hook_files(),
        ['grandparent.py', 'base1.py', 'mypackage.py'])

    # the below relies on an unstable ordering as the lists are not sorted, but
    # the parent traversal happens in an (unspecified) stable order
    expected = marked_yaml_load("""\
        build_stages:
        - {handler: foo, name: __3gcv3kvebeam4h3qzok75lxxt5n3rzr7, random: anonymous}
        - {a: 1, b: 3, name: stage1_override}
        - {a: 1, name: stage4_replace}
        - {a: 1, after: stage1_override, b: 3, name: stage3_override}
        - {a: 1, after: stage1_override, before: stage3_override, name: stage_2_inserted}
        post_process:
        - {hit: relative-rpath, name: post1}
        profile_links:
        - {link: '*/**/*', name: start}
        - {link: foo, name: __ypp7s5jlosieet6v4iyhvbg52ymlcwgk}
        - {after: start, link: '*/**/*', name: end}
        when_build_dependency:
        - {name: start, set: FOO, value: foovalue}
    """)
    eq_(expected, loader.doc)

def test_update_mode():
    files = {}
    files['python.yaml'] = """
    build_stages:
    - name: configure
    - name: configure
      mode: update
      append: {LDFLAGS: "--overridden-flag"}
      extra: ['--without-ensurepip']
    - name: configure
      mode: update
      append: {LDFLAGS: "-Wl,-rpath,${ARTIFACT}/lib"}
      extra: ['--enable-shared']
    - name: configure
      mode: update
      extra: ['--enable-framework=${ARTIFACT}']
    """
    prof = MockProfile(files)
    pkg = prof.load_package('python')
    loader = package_loader.PackageLoader(pkg, {})
    expected = [{'handler': 'configure',
                 'append': {'LDFLAGS': '-Wl,-rpath,${ARTIFACT}/lib'},
                 'extra': ['--without-ensurepip', '--enable-shared', '--enable-framework=${ARTIFACT}']}]
    eq_(expected, loader.doc['build_stages'])

def test_order_stages():
    loader = package_loader.PackageLoader.__new__(package_loader.PackageLoader)
    loader.doc = marked_yaml_load("""\
    build_stages:
    - {a: 1, after: stage1_override, before: stage3_override, name: stage_2_inserted}
    - {a: 1, name: stage4_replace}
    - {a: 1, b: 3, name: stage1_override}
    - {a: 1, after: stage1_override, b: 3, name: stage3_override}
    """)

    expected = marked_yaml_load("""\
    build_stages:
    - {a: 1, b: 3, handler: stage1_override}
    - {a: 1, handler: stage_2_inserted}
    - {a: 1, b: 3, handler: stage3_override}
    - {a: 1, handler: stage4_replace}
    post_process: []
    profile_links: []
    when_build_dependency: []
    """)
    loader.topo_order_stages()
    eq_(expected, loader.doc)

def test_extend_list():

    def _extend_list(to_insert, lst):
        """Removes items from `lst` that can be found in `to_insert`, and then
        returns a list with `to_insert` at the front and `lst` at the end.
        """
        lst = [x for x in lst if x not in to_insert]
        return to_insert + lst

    yield eq_, ['a', 'b'], _extend_list(['a'], ['b'])
    yield eq_, ['a', 'b'], _extend_list(['a'], ['b', 'a'])
    yield eq_, [], _extend_list([], [])
    # check that input is not mutated
    lst = ['a', 'a', 'a', 'a']
    yield eq_, ['a'], _extend_list(['a'], lst)
    yield eq_, ['a', 'a', 'a', 'a'], lst

def test_name_anonymous_stages():
    loader = package_loader.PackageLoader.__new__(package_loader.PackageLoader)
    loader.name = 'theloader'
    stages_ok = [
        {'name': 'foo'},
        {'before': 'foo', 'one': 1},
        {'before': 'bar', 'after': 'foo', 'two': 2},
        {}
        ]
    stages_identical = [
        {'before': 'foo', 'one': 1},
        {'before': 'bar', 'after': 'foo', 'one': 1},
        ]
    loader.doc = dict(ok=stages_ok, bad=stages_identical)
    result = loader.get_stages_with_names('ok')
    assert result == [{'name': 'foo'},
                      {'before': 'foo', 'name': '__vohxh6yicfhfiz6qerugjle42wfmlu2p', 'one': 1},
                      {'after': 'foo',
                       'before': 'bar',
                       'name': '__tdurutje3wctzqnu24mzy5gqza5yxt6b',
                       'two': 2},
                      {'name': '__qvk3jbqy6b3mvv5opou3ae55met2pt6s'}]
    with assert_raises(PackageError):
        loader.get_stages_with_names('bad')

@temp_working_dir_fixture
def test_files_glob(d):
    dump('pkgs/bar/bar.yaml', """
        dependencies:
          run: []
        profile_links:
        - name: link_with_glob
          link: '*/**/*'
        - name: link_without_glob
          link: bar
        build_stages:
        - name: build_without_glob
          files: [bar.c]
        - name: build_with_glob
          files: [glob_*]
    """)
    dump('pkgs/bar/bar.c', '/*****/')
    dump('pkgs/bar/glob_first', 'Frist!')
    dump('pkgs/bar/glob_second', 'Second')
    dump('profile.yaml', """
        package_dirs:
        - pkgs
    """)
    with profile.TemporarySourceCheckouts(None) as checkouts:
        doc = profile.load_and_inherit_profile(checkouts, "profile.yaml")
        prof = profile.Profile(null_logger, doc, checkouts)
        pkg = prof.load_package('bar')
        instance = pkg.instantiate({})
    eq_(instance._impl.doc, marked_yaml_load("""
        post_process: []
        profile_links:
        - {link: '*/**/*'}
        - {link: bar}
        build_stages:
        - files: [glob_first, glob_second]
          handler: build_with_glob
        - files: [bar.c]
          handler: build_without_glob
        when_build_dependency: []
    """))

@temp_working_dir_fixture
def test_package_spec(d):
    # Test parsing and construction of PackageSpec, i.e. YAML files loaded
    # and the interface to other packages parsed.

    # The 'when' clause on parameters is mostly useless, but allows testing,
    # and must be implemented anyway due to when clauses on package builds.
    # So since we don't expect these used independently, we require anything
    # going into them to be 'globally present' parameters

    # First create two alternatives for "middlebase" (default and -alt), with a parameter choosing
    # between them in "base". middlebase-alt declares the y parameter, middlebase declares
    # the x parameter. To add to the fun, only bar-positive-int-parameter extends from
    # middlebase, the default bar doesn't extend anything.
    dump('pkgs/base.yaml', """
        parameters:
        - name: use_middlebase_alt
          type: bool
          default: true
        - name: param_with_def_val
          default: in_base
    """)
    dump('pkgs/middlebase/middlebase.yaml', """
        extends: [base]
        parameters: [{name: y, type: int}]
    """)
    dump('pkgs/middlebase/middlebase-alt.yaml', """
        extends: [base]
        when: use_middlebase_alt
        parameters: [{name: x, type: int}]
    """)

    dump('pkgs/bar/bar-positive-int-parameter.yaml', """
        when bool_parameter:
          extends: [middlebase]  # extend conditional on a parameter..
        when: int_parameter > 0
        dependencies:
          build: [adep, {'when bool_parameter': [bdep]}]
          run: [adep, rdep]
        parameters:
        - name: str_parameter
          type: str
          when: bool_parameter == True and int_parameter == 3
          default: foovalue

        - name: bool_parameter
          type: bool

        - name: int_parameter
          type: int
    """)
    dump('pkgs/bar/bar.yaml', """
        dependencies:
          build: [bdep, cdep]
        parameters:
        - name: bool_parameter
          type: bool

        - name: other_parameter
          type: int

        - when not bool_parameter:
            - name: str_parameter
              type: str
              default: foovalue

        - name: param_with_def_val
          default: in_bar
    """)
    dump('profile.yaml', """
        package_dirs:
        - pkgs
        packages:
          bar:
    """)
    with profile.TemporarySourceCheckouts(None) as checkouts:
        prof = profile.load_profile(null_logger, checkouts, "profile.yaml")
        pkg = prof.load_package('bar')

    eq_(pkg.parameters['param_with_def_val'].default, 'in_bar')

    mock_package = object()

    eq_(set(pkg.parameters.keys()),
        set(['BASH', '_run_adep', '_run_rdep',
             'adep', 'bdep', 'bool_parameter', 'cdep',
             'int_parameter', 'other_parameter', 'package', 'str_parameter',
             'y', 'x', 'use_middlebase_alt',
             'param_with_def_val']))

    # Check resulting declared_when and constraints
    eq_(pkg.parameters['str_parameter'].declared_when,
        '((int_parameter > 0) and (bool_parameter == True and int_parameter == 3)) or '
        '((not (int_parameter > 0)) and (not bool_parameter))')

    eq_(pkg.parameters['bdep'].declared_when,
        '((int_parameter > 0) and (bool_parameter)) or (not (int_parameter > 0))')

    # x and y depedns on use_middlebase_alt..
    eq_(pkg.parameters['x'].declared_when, '((int_parameter > 0) and (bool_parameter)) and (use_middlebase_alt)')
    eq_(pkg.parameters['y'].declared_when, '((int_parameter > 0) and (bool_parameter)) and (not (use_middlebase_alt))')

    ##pprint(sorted(pkg.constraints))
    eq_(set(pkg.constraints), set([
        'not ((int_parameter > 0) and (bool_parameter)) or (bdep is not None)',
        'not ((int_parameter > 0) and (bool_parameter)) or (not (use_middlebase_alt) or (x is not None))',
        'not ((int_parameter > 0) and (bool_parameter)) or (not (not (use_middlebase_alt)) or (y is not None))',
        'not (int_parameter > 0) or (adep is not None)',
        'not (int_parameter > 0) or (bool_parameter is not None)',
        'not (int_parameter > 0) or (int_parameter is not None)',
        'not (int_parameter > 0) or (_run_adep is not None)',
        'not (int_parameter > 0) or (_run_rdep is not None)',
        'not (not (int_parameter > 0)) or (bdep is not None)',
        'not (not (int_parameter > 0)) or (bool_parameter is not None)',
        'not (not (int_parameter > 0)) or (cdep is not None)',
        'not (not (int_parameter > 0)) or (other_parameter is not None)',
        ]))

    # get_failing_constraints method
    eq_(pkg.get_failing_constraints({'int_parameter': 3, 'adep': None, 'bool_parameter': True,
                                     'bdep': mock_package, '_run_rdep': mock_package, '_run_adep': mock_package,
                                     'use_middlebase_alt': False, 'y': 3}),
        ['not (int_parameter > 0) or (adep is not None)'])

    with assert_raises(ProfileError) as e:
        # other_parameter not present
        pkg.get_failing_constraints({'int_parameter': -13, 'adep': None, 'bool_parameter': True,
                                     'bdep': mock_package, '_run_rdep': mock_package,
                                     '_run_adep': mock_package})
    assert "'other_parameter' is not defined" in str(e.exc_val)

    params = {'int_parameter': -13, 'cdep': mock_package, 'bool_parameter': True,
              'bdep': mock_package, '_run_rdep': mock_package, '_run_adep': mock_package,
              'other_parameter': 4, 'use_middlebase_alt': True}
    eq_([], pkg.get_failing_constraints(params))

    # typecheck_parameter_set method
    def check_package(self, value):
        eq_(value, mock_package)
        return True

    with mock.patch('hashdist.spec.package.Parameter._check_package_value', check_package):
        with assert_raises(ProfileError) as e:
            pkg.typecheck_parameter_set({'int_parameter': 3})
        assert "'bool_parameter' is not defined" in str(e.exc_val)

        pkg.typecheck_parameter_set(params)
        params['int_parameter'] = 'a'
        with assert_raises(PackageError) as e:
            pkg.typecheck_parameter_set(params)
        eq_(str(e.exc_val), "<unknown location>: Parameter int_parameter has value 'a' which is not of type <type 'int'>")


def test_parse_deps_repeated():
    from .test_spec_ast import load_when_doc_from_str as loads
    with assert_raises(PackageError) as e:
        package.parse_deps(loads("{'dependencies': {'build': ['a', '+a']}}"))
    assert 'dependency a repeated' in str(e.exc_val)
    with assert_raises(PackageError):
        package.parse_deps(loads("{'dependencies': {'run': ['a', '+a']}}"))
    assert 'dependency a repeated' in str(e.exc_val)
    # But this is OK:
    package.parse_deps(loads("{'dependencies': {'run': ['a'], 'build': ['a']}}"))


def test_parse_deps():
    from .test_spec_ast import load_when_doc_from_str as loads
    params, constraints = package.parse_deps(loads(
        "{dependencies: {build: [a, b], run: [x, +b, +c]}}"))
    eq_(set(params.keys()), set(['a', 'b', '_run_x', '_run_b', '_run_c']))
    eq_(set(constraints), set(['_run_x is not None', 'a is not None', 'b is not None']))
