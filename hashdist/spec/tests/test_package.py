from pprint import pprint
from os.path import join as pjoin
from textwrap import dedent
from ...core.test.utils import *
from .. import package
from .. import hook_api
from ...formats.marked_yaml import marked_yaml_load, yaml_dump
from ..exceptions import ProfileError
from nose import SkipTest

def test_topological_stage_sort():
    stages = [dict(name='z', value='z'),
              dict(name='a', value='a', before=['c', 'b', 'nonexisting']),
              dict(name='c', value='c'),
              dict(name='b', value='b'),
              dict(name='aa', value='aa', before='c', after=['b', 'nonexisting'])]
    stages = package.normalize_stages(stages)
    stages = package.topological_stage_sort(stages)
    assert stages == [{'value': 'a'}, {'value': 'b'}, {'value': 'aa'}, {'value': 'c'}, {'value': 'z'}]

#
# Build script assembly
#
def test_assemble_stages():
    doc = marked_yaml_load("""\
        build_stages:
        - {handler: bash, bash: './configure --with-foo={{foo}}'}
        - {handler: bash, bash: make}
        - {handler: bash, bash: make install}
    """)
    ctx = hook_api.PackageBuildContext(None, {}, {})
    ctx.parameters['foo'] = 'somevalue'
    p = package.PackageSpec("mypackage", doc, [], {})
    script = p.assemble_build_script(ctx)
    assert script == dedent("""\
    set -e
    export HDIST_IN_BUILD=yes
    ./configure --with-foo=somevalue
    make
    make install
    """)

def test_create_build_spec():
    package_spec = marked_yaml_load(dedent("""\
        name: mylib
        sources:
          - git: git://foo
            key: git:a3c39a03e7b8e9a3321d69ff877338f99ebb4aa2
        dependencies:
          build: [otherlib]
          run: [foolib] # should be ignored
        build_stages:
          - {name: make, handler: bash, bash: make}
        when_build_dependency:  # ignored below, only used in build spec of dependency
          - prepend_path: FOO
            value: value-of-FOO
    """))
    parameters = {"X": "x", "BASH": "/bin/bash"}
    build_spec = package.create_build_spec("mylib", package_spec,
                                           parameters, {"otherlib": "otherlib/abcdefg"}, {})
    expected = {
        "name": "mylib",
        "build": {
            "import": [{"ref": "OTHERLIB", "id": "otherlib/abcdefg"}],
            "commands": [
                {"set": "BASH", "nohash_value": "/bin/bash"},
                {"cmd": ["$BASH", "_hashdist/build.sh"]},
                {'hit': ['build-postprocess', '--shebang=multiline', '--write-protect', '--remove-pkgconfig',
                         '--relative-rpath', '--check-relocateable']}]},
        "sources": [
            {"key": "git:a3c39a03e7b8e9a3321d69ff877338f99ebb4aa2", "target": "."}
            ]}
    assert expected == build_spec.doc



class MockProfile(object):
    def __init__(self, files):
        self.files = dict((name, marked_yaml_load(body)) for name, body in files.items())

    def load_package_yaml(self, name, parameters):
        return self.files.get('%s.yaml' % name, None)

    def find_package_file(self, name, filename):
        return filename if filename in self.files else None

def test_prevent_diamond():
    files = {
        'a.yaml': 'extends: [b, c]',
        'b.yaml': 'extends: [d]',
        'c.yaml': 'extends: [d]',
        'd.yaml': '{}'}
    with assert_raises(ProfileError):
        package.load_and_inherit_package(MockProfile(files), 'a', {})

def test_inheritance_collision():
    files = {
        'child.yaml': 'extends: [base1, base2]',
        'base1.yaml': 'build_stages: [{name: stage1}]',
        'base2.yaml': 'build_stages: [{name: stage1}]'}
    with assert_raises(ProfileError):
        package.load_and_inherit_package(MockProfile(files), 'child', {})


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
    files['mypackage.py'] = '{}'

    prof = MockProfile(files)

    doc, hook_files, parameters = package.load_and_inherit_package(prof, 'mypackage', {})
    assert hook_files == ['grandparent.py', 'base1.py', 'mypackage.py']

    # the below relies on an unstable ordering as the lists are not sorted, but
    # the parent traversal happens in an (unspecified) stable order
    expected = marked_yaml_load("""\
        build_stages:
        - {handler: foo, name: __3gcv3kvebeam4h3qzok75lxxt5n3rzr7, random: anonymous}
        - {a: 1, b: 3, name: stage1_override}
        - {a: 1, name: stage4_replace}
        - {a: 1, after: stage1_override, b: 3, name: stage3_override}
        - {a: 1, after: stage1_override, before: stage3_override, name: stage_2_inserted}
        dependencies:
          build: [dep1, dep_gp_1]
          run: [dep1, dep_base2_1]
        profile_links:
        - {link: '*/**/*', name: start}
        - {link: foo, name: __ypp7s5jlosieet6v4iyhvbg52ymlcwgk}
        - {after: start, link: '*/**/*', name: end}
        when_build_dependency:
        - {name: start, set: FOO, value: foovalue}
    """)
    assert expected == doc


def test_order_stages():
    doc = marked_yaml_load("""\
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
    profile_links: []
    when_build_dependency: []
    """)
    result = package.order_package_stages(doc)
    assert expected == result


def test_extend_list():
    yield eq_, ['a', 'b'], package._extend_list(['a'], ['b'])
    yield eq_, ['a', 'b'], package._extend_list(['a'], ['b', 'a'])
    yield eq_, [], package._extend_list([], [])
    # check that input is not mutated
    lst = ['a', 'a', 'a', 'a']
    yield eq_, ['a'], package._extend_list(['a'], lst)
    yield eq_, ['a', 'a', 'a', 'a'], lst

def test_name_anonymous_stages():
    stages = [
        {'name': 'foo'},
        {'before': 'foo', 'one': 1},
        {'before': 'bar', 'after': 'foo', 'one': 1}, # should get same name
        {}
        ]
    result = package.name_anonymous_stages(stages)
    assert result == [{'name': 'foo'},
                      {'before': 'foo', 'name': '__vohxh6yicfhfiz6qerugjle42wfmlu2p', 'one': 1},
                      {'after': 'foo',
                       'before': 'bar',
                       'name': '__vohxh6yicfhfiz6qerugjle42wfmlu2p',
                       'one': 1},
                      {'name': '__qvk3jbqy6b3mvv5opou3ae55met2pt6s'}]
    # Note: The fact that identical stages get the same name, which trips up things downstream,
    # could be seen as a feature rather than a bug -- you normally never want this. At any
    # rate, this is better for final ordering stability than having a random ordering.

def test_when_dictionary():
    doc = marked_yaml_load("""\
    dictionary:
        when platform == 'linux':
            when host:
                one: 1
            two: 2
    """)
    r = package.process_conditionals(doc, {'platform': 'linux',
                                           'host': True})
    assert {'dictionary': {'one': 1, 'two': 2}} == r
    r = package.process_conditionals(doc, {'platform': 'linux',
                                           'host': False})
    assert {'dictionary': {'two': 2}} == r
    r = package.process_conditionals(doc, {'platform': 'windows',
                                           'host': False})
    assert {'dictionary': {}} == r

def test_when_list():
    doc = marked_yaml_load("""\
    dictionary:
    - when platform == 'linux':
      - when host:
        - 1
      - 2
    - 3
    - {nested: dict} # dict of length 1
    - am-on: host
      when: host
    """)
    r = package.process_conditionals(doc, {'platform': 'linux',
                                           'host': True})
    assert {'dictionary': [1, 2, 3, {'nested': 'dict'}, {'am-on': 'host'}]} == r
    r = package.process_conditionals(doc, {'platform': 'linux',
                                           'host': False})
    assert {'dictionary': [2, 3, {'nested': 'dict'}]} == r
    r = package.process_conditionals(doc, {'platform': 'windows',
                                           'host': False})
    assert {'dictionary': [3, {'nested': 'dict'}]} == r
