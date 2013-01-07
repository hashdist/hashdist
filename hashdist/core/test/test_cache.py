import functools
import os
import glob

from .utils import temp_dir
from ..cache import DiskCache, NOT_PRESENT

def fixture():
    def decorator(func):
        @functools.wraps(func)
        def decorated():
            with temp_dir() as d:
                func(DiskCache(d), d)
        return decorated
    return decorator

@fixture()
def test_basic(cache, tmpdir):
    cache.put('foo', 'bar', 1)
    cache.put('foo', 'baz', 2)
    assert cache.get('foo', 'bar') == 1
    assert cache.get('foo', 'baz') == 2
 
    cache.put('foo2', 'bar', 2)
    assert cache.get('foo2', 'bar') == 2
    assert cache.get('foo', 'bar') == 1

    assert cache.get('nonexisting', 'bar') is NOT_PRESENT
    assert cache.get('nonexisting', 'bar', 'default') == 'default'
    
@fixture()
def test_unpickleable(cache, tmpdir):
    class Unpickleable(object):
        def __reduce__(self):
            raise Exception()

    try:
        cache.put('foo', 'bar', Unpickleable())
    except Exception:
        lst = glob.glob(os.path.join(tmpdir, '*'))
        assert len(lst) == 1
        assert len(os.listdir(lst[0])) == 0
    else:
        assert False
