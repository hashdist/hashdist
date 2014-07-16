import functools
import logging
from nose import SkipTest

from ..host import WrongHostTypeError
from ..debian import DebianHostPackages
from ...core import null_cache

def setup():
    global deb
    null_logger = logging.getLogger('null_logger')
    try:
        deb = DebianHostPackages(null_logger, null_cache)
    except WrongHostTypeError, e:
        raise SkipTest("not on Debian")
        
def test_deps():
    all_deps = deb.get_all_dependencies('gcc')
    assert 'libc6' in all_deps

    imm_deps = deb.get_immediate_dependencies('gcc')
    assert len(imm_deps) < len(all_deps)
    assert len(imm_deps.difference(all_deps)) == 0

def test_key():
    key = deb.get_package_key('gcc')
    assert key.startswith('deb:')
    assert deb.check_package('gcc', key) == True
    assert deb.check_package('gcc', 'deb:' + '3' * 40) == False
    assert deb.check_package('nonexisting-foo', key) == False
    assert deb.is_package_installed('nonexisting-foo') == False

def test_files_installed():
    assert '/usr/bin/gcc' in deb.get_files_of('gcc')
