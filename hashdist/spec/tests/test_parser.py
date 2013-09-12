from ...core.test.utils import *
from .. import parser

@temp_working_dir_fixture
def test_package_loading(d):
    dump("pkgs/b/b.yaml", """\
    name: b
    deps: [a]
    """)

    dump("pkgs/a/a.yaml", """\
    name: a
    """)

    resolver = parser.PackageSpecResolver("pkgs")
    print resolver.parse_package("a")
    1/0
    
    
