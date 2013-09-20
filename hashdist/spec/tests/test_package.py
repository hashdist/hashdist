from pprint import pprint
from textwrap import dedent
from ...core.test.utils import *
from .. import package
from ..marked_yaml import marked_yaml_load

from nose import SkipTest

def test_topological_stage_sort():
    stages = [dict(name='z'),
              dict(name='a', before=['c', 'b']),
              dict(name='c'),
              dict(name='b'),
              dict(name='aa', before='c', after='b')]
    stages = package.normalize_stages(stages)
    stages = package.topological_stage_sort(stages)
    assert stages == [{'name': 'a'}, {'name': 'b'}, {'name': 'aa'}, {'name': 'c'}, {'name': 'z'}]

#
# Build script assembly
#
def test_assemble_stages():
    spec = marked_yaml_load("""\
        build_stages:
          - {name: install, handler: bash, bash: make install}
          - {name: make, handler: bash, before: install, after: configure, bash: make}
          - {name: configure, handler: bash, bash: './configure --with-foo=${{foo}}'}
    """)
    parameters = {'foo': 'somevalue'}
    p = package.PackageSpec("mypackage", spec, {})
    script = p.assemble_build_script(parameters)
    assert script == dedent("""\
    set -e
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
        on_import:  # ignored below, only used in build spec of dependency
          - prepend_path: PYTHONPATH
            value: foo${{X}} ${X}
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
                {"chdir": "src"},
                {"cmd": ["$BASH", "../build.sh"]}]},
        "sources": [
            {"key": "git:a3c39a03e7b8e9a3321d69ff877338f99ebb4aa2", "target": "src"}
            ]}
    assert expected == build_spec.doc


class MockProfile(object):
    def __init__(self, dir):
        self.dir = dir

def test_inheritance_happy_day():
    child_doc = marked_yaml_load("""\
    extends: [base1, base2]
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
    """)

    base1_doc = marked_yaml_load("""\
    build_stages:
      - {name: stage1_override, a: 2, b: 3}
      - {name: stage_to_remove, after: stage1_override, a: 2, b: 3}
    """)

    base2_doc = marked_yaml_load("""\
    build_stages:
      - {name: stage3_override, after: stage1_override, a: 2, b: 3}
      - {name: stage4_replace, after: stage3_override, a: 2, b: 3}
    """)

    p = package.PackageSpec('mypackage', child_doc, {'base1': base1_doc, 'base2': base2_doc})
    assert p.build_stages == [
        {'name': 'stage1_override', 'a': 1, 'b': 3},
        {'name': 'stage_2_inserted', 'a': 1},
        {'name': 'stage3_override', 'a': 1, 'b': 3},
        {'name': 'stage4_replace', 'a': 1}]

def test_inheritance_collision():
    child_doc = marked_yaml_load("extends: [base1, base2]")
    base1_doc = marked_yaml_load("build_stages: [{name: stage1}]")
    base2_doc = marked_yaml_load("build_stages: [{name: stage1}]")
    with assert_raises(package.IllegalPackageSpecError):
        package.PackageSpec('mypackage', child_doc, {'base1': base1_doc, 'base2': base2_doc})
    
