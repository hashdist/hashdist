import tempfile
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
def test_script_assembly(d):
    pass
