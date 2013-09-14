from textwrap import dedent
from ...core.test.utils import *
from .. import package
from ..marked_yaml import marked_yaml_load


def test_topological_stage_sort():
    stages = [dict(name='z'),
              dict(name='a', before=['c', 'b']),
              dict(name='c'),
              dict(name='b'),
              dict(name='aa', before='c', after='b')]
    stages = package.normalize_stages(stages)
    stages = package.topological_stage_sort(stages)
    assert stages == [{'name': 'a'}, {'name': 'b'}, {'name': 'aa'}, {'name': 'c'}, {'name': 'z'}]

@temp_working_dir_fixture
def test_package_loading(d):
    dump("pkgs/b/b.yaml", """\
    name: b
    sources:
      - http://foo
    dependencies:
      build: [a]
      run: [a]
    """)

    dump("pkgs/a/a.yaml", """\
    name: a
    """)

    resolver = package.PackageSpecResolver("pkgs")
    b = resolver.parse_package("b")
    assert ['a'] == b.run_deps.keys()
    assert ['a'] == b.build_deps.keys()
    assert 'a' == b.run_deps['a'].doc['name']

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
    parameters = {'X': 'x', 'BASH': '/bin/bash'}
    build_spec = package.create_build_spec(package_spec, parameters, {'otherlib': 'otherlib/abcdefg'})
    expected = {
        'name': 'mylib',
        'version': 'na',
        'on_import': [{'prepend_path': 'PYTHONPATH', 'value': 'foox ${X}'}],
        'build': {
            'import': [{'in_env': True, 'ref': 'OTHERLIB', 'id': 'otherlib/abcdefg'}],
            'commands': [
                {'set': 'BASH', 'nohash_value': '/bin/bash'},
                {'chdir': 'src'},
                {'cmd': ['$BASH', '../build.sh']}],
            'nohash_params': {}}}
    assert expected == build_spec.doc


## @temp_working_dir_fixture
## def test_assemble_with_handler(d):
##     dump('base/toimport.py', """\
##     from hashdist.spec
##     """)
##     dump('base/foobase.py', """\
##     from hashdist.spec import handler

##     @handler

    
##     """)
