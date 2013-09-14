from textwrap import dedent
from ...core.test.utils import *
from .. import package




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
    
    
@temp_working_dir_fixture
def test_assemble_stages(d):
    spec = dedent("""\
    name: a
    build-stages:
      - {name: install, handler: bash, bash: make install}
      - {name: make, handler: bash, before: install, after: configure, bash: make}
      - {name: configure, hander: bash, bash: ./configure --with-foo=${foo}}
    """)
    parameters = {'foo': 'somevalue'}

def test_topological_stage_sort():
    stages = [dict(name='z'),
              dict(name='a', before=['c', 'b']),
              dict(name='c'),
              dict(name='b'),
              dict(name='aa', before='c', after='b')]
    stages = package.normalize_stages(stages)
    stages = package.topological_stage_sort(stages)
    assert stages == [{'name': 'a'}, {'name': 'b'}, {'name': 'aa'}, {'name': 'c'}, {'name': 'z'}]
