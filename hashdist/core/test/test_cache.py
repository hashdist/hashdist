import functools
import os
import glob
from os.path import join as pjoin

from .utils import temp_dir, assert_raises
from ..cache import DiskCache

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
    assert DiskCache(tmpdir).get('foo', 'bar') == 1

    assert cache.get('foo', 'baz') == 2
 
    cache.put('foo2', 'bar', 2)
    assert cache.get('foo2', 'bar') == 2
    assert cache.get('foo', 'bar') == 1

    with assert_raises(KeyError):
        cache.get('nonexisting', 'bar')
    assert cache.get('nonexisting', 'bar', 'default') == 'default'

@fixture()
def test_prevent_disk(cache, tempdir):
    cache.put('foo', 'bar', 1, on_disk=False)
    assert DiskCache(tempdir).get('foo', 'bar', None) == None
    assert cache.get('foo', 'bar', None) == 1
    
@fixture()
def test_memory_caching(cache, tempdir):
    # We can retreive even if we remove the backing file, as long as cache is
    # not destructed...
    cache.put('foo', 'bar', 1)
    assert len(cache.memory_cache) == 1
    os.unlink(glob.glob(pjoin(tempdir, '*', '*', '*'))[0])
    assert cache.get('foo', 'bar') == 1
    assert DiskCache(tempdir).get('foo', 'bar', -1) == -1

@fixture()
def test_invalidate(cache, tempdir):
    cache.invalidate('a') # should not raise exception
    cache.put('a', 'foo', 1)
    cache.put('b', 'foo', 2)
    cache.invalidate('a')
    assert cache.get('a', 'foo', None) == None
    assert cache.get('b', 'foo', None) == 2
    
@fixture()
def test_unpickleable(cache, tmpdir):
    class Unpickleable(object):
        def __reduce__(self):
            raise Exception()

    try:
        cache.put('foo', 'bar', Unpickleable())
    except Exception:
        lst = glob.glob(os.path.join(tmpdir, '*', '*'))
        assert len(lst) == 1
        assert len(os.listdir(lst[0])) == 0
    else:
        assert False
