"""
:mod:`hashdist.core.cache` --- General caching
==============================================

Building artifact descriptions can be time-consuming if it involves,
e.g., probing the host system for information and so on. This is
simply a key-value store stored in a central location for HashDist
(typically ``~/.hit/cache``). Anything in the cache can be removed
without further notice.
"""

from os.path import join as pjoin
import os
import tempfile
import cPickle as pickle
import errno
from functools import wraps
import re
import shutil

from .hasher import Hasher
from .fileutils import silent_makedirs

_RAISE = object()

DOMAIN_RE = re.compile(r'^[a-zA-Z0-9-+_.]+$')

class DiskCache(object):
    """
    Key/value cache. The cache has two layers; one in-memory cache for
    this object, and one on disk.

    Each value is cached by (domain, key); all the keys in one
    key domain can be invalidated together. The domain also helps
    making sure there's not key collisions between different uses.

    .. warning::
    
        If two caches access the same path, domain invalidations from
        one cache will not propagate to contents in the memory cache
        of the other. This class is really only meant for very simple
        caching...
    
    """
    def __init__(self, cache_path):
        self.cache_path = cache_path
        self.memory_cache = {}
    
    @staticmethod
    def create_from_config(config, logger):
        """Creates a DiskCache from the settings in the configuration
        """
        return DiskCache(config['global/cache'])

    def _as_domain(self, domain):
        if not isinstance(domain, str):
            domain = '%s.%s' % (domain.__module__, domain.__name__)
        if not DOMAIN_RE.match(domain):
            raise ValueError('invalid domain, does not match %s' % DOMAIN_RE.pattern)
        return domain
    
    def _get_obj_filename(self, domain, key):
        h = Hasher()
        h.update(key)
        digest = h.format_digest()
        return pjoin(self.cache_path, domain, digest[:2], digest[2:])

    def _get_memory_cache(self, domain):
        return self.memory_cache.setdefault(domain, {})

    def invalidate(self, domain):
        """Invalidates all entries in the given domain.
        """
        self._get_memory_cache(domain).clear()
        shutil.rmtree(pjoin(self.cache_path, domain), ignore_errors=True)
            

    def put(self, domain, key, value, on_disk=True):
        """Puts a value to the store

        This should be atomic and race-safe, provided that everybody who
        does a put puts the same value.

        .. warning::

            `value` should be immutable or at least never modified,
            since the same instance can be retreived from the memory
            cache

        Parameters
        ----------

        domain : type or str
            Should be a type or a string that is combined with the key
            to perform the lookup. If a type is passed, then its
            fully qualified name is taken as the domain string.
            The domain must match `DOMAIN_RE`.

        key : object
            Object that is hashable with :cls:`Hasher`.

        value : object
            Pickleable object.

        on_disk : bool
            If `False`, the value will only be stored in the memory cache
            and never pickled/unpickled.
        """
        domain = self._as_domain(domain)
        obj_filename = self._get_obj_filename(domain, key)

        # memory cache
        if obj_filename in self.memory_cache:
            # already stored from this same cache object; don't bother with writing
            # to disk
            return
        self._get_memory_cache(domain)[obj_filename] = value

        if on_disk:
            # dump to temporary file + atomic rename
            obj_dir = os.path.dirname(obj_filename)
            silent_makedirs(obj_dir)
            fd, temp_filename = tempfile.mkstemp(dir=obj_dir)
            try:
                with os.fdopen(fd, 'w') as f:
                    pickle.dump(value, f, protocol=2)
                os.rename(temp_filename, obj_filename)
            except:
                os.unlink(temp_filename)
                raise

    def get(self, domain, key, default=_RAISE):
        """Looks up value from store

        Parameters
        ----------

        domain : type or str
            Should be a type or a string that is combined with the key
            to perform the lookup; this is present to enforce that
            keyspaces don't collide. If a type is passed, then its
            fully qualified name is taken as the domain string.
            The domain must match `DOMAIN_RE`.

        key : object
            Object that is hashable with :cls:`Hasher`.

        default : object (optional)
            Object to return if lookup fails. If not present, a KeyError
            is raised.
        """
        domain = self._as_domain(domain)
        obj_filename = self._get_obj_filename(domain, key)
        try:
            x = self._get_memory_cache(domain)[obj_filename]
        except KeyError:
            try:
                f = file(obj_filename)
            except IOError, e:
                if e.errno != errno.ENOENT:
                    raise
                if default is not _RAISE:
                    return default
                else:
                    raise KeyError('Cannot find object in key-domain "%s" that hashes to %s' %
                                   (domain, obj_filename))
            with f:
                x = self._get_memory_cache(domain)[obj_filename] = pickle.load(f)
        return x

class NullCache(object):
    def put(self, domain, key, value):
        pass

    def get(self, domain, key, default=_RAISE):
        if default is _RAISE:
            raise KeyError('keys are never found in the NullCache')
        else:
            return default

    def invalidate(self, domain):
        pass

null_cache = NullCache()

def cached_method(domain):
    def decorator(func):
        @wraps(func)
        def replacement(self, *args):
            key = (func.__name__,) + tuple(args)
            try:
                x = self.cache.get(domain, key)
            except KeyError:
                x = func(self, *args)
                self.cache.put(domain, key, x)
            return x
        return replacement
    return decorator
