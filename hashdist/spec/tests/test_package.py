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
    spec = dedent("""\
      - {name: install, handler: bash, bash: make install}
      - {name: make, handler: bash, before: install, after: configure, bash: make}
      - {name: configure, handler: bash, bash: './configure --with-foo=${{foo}}'}
    """)
    parameters = {'foo': 'somevalue'}
    script = package.assemble_build_script(marked_yaml_load(spec), parameters)
    assert script == dedent("""\
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
        on_import:
          - prepend_path: PYTHONPATH
            value: foo${{X}} ${X}
    """))
    parameters = {"X": "x", "BASH": "/bin/bash"}
    build_spec = package.create_build_spec(package_spec, parameters, {"otherlib": "otherlib/abcdefg"})
    expected = {
        "name": "mylib",
        "version": "na",
        "on_import": [{"prepend_path": "PYTHONPATH", "value": "foox ${X}"}],
        "build": {
            "import": [{"in_env": True, "ref": "OTHERLIB", "id": "otherlib/abcdefg"}],
            "commands": [
                {"set": "BASH", "nohash_value": "/bin/bash"},
                {"chdir": "src"},
                {"cmd": ["$BASH", "../build.sh"]}],
            "nohash_params": {}},
        "sources": [
            {"key": "git:a3c39a03e7b8e9a3321d69ff877338f99ebb4aa2", "target": "src"}
            ]}
    assert expected == build_spec.doc

@temp_working_dir_fixture
def test_assemble_stages_python_handlers(d):
    raise SkipTest("only test case written for this one")

    dump('base/numberechoing.py', """\
    from hashdist.spec import handler
    from myutils import get_echo_string

    @handler()
    def echo_number(pkg, parameters, stage_args):
        return ['%s %s %d' % (get_echo_string(), parameters['caption'], stage_args['number'])]

    """)
    dump('base/myutils.py', """\
    def get_echo_string(): return 'echo'
    """)
    dump('base/numberechoing.yaml', """\
    build_stages:
        - {name: configure, before: echo_number, handler: bash, bash: echo Echo coming up}
    """)
    
    spec = dedent("""\
    extends: [numberechoing]
      - {name: echo_number, number: 4}
    """)
    parameters = {'caption': 'numero'}
    script = package.assemble_build_script(marked_yaml_load(spec), parameters)
    assert script == dedent("""\
    ./configure --with-foo=somevalue
    make
    make install
    """)
