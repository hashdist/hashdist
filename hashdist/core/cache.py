"""
:mod:`hashdist.core.cache` --- General caching
==============================================

Building artifact descriptions can be time-consuming if it involves,
e.g., probing the host system for information and so on. This is
simply a key-value store stored in a central location for Hashdist
(typically ``~/.hdist/cache``). Anything in the cache can be removed
without further notice.
"""

from os.path import join as pjoin
import os
import tempfile
import cPickle as pickle
import errno

from .hasher import Hasher
from .fileutils import silent_makedirs

_RAISE = object()

class DiskCache(object):
    """
    Key/value store to cache th
    """
    def __init__(self, cache_path):
        self.cache_path = cache_path
        self.memory_cache = {}
    
    @staticmethod
    def create_from_config(config, logger):
        """Creates a Cache from the settings in the configuration
        """
        return Cache(config.get_path('general', 'cache'))

    def _as_domain(self, domain):
        if not isinstance(domain, str):
            domain = '%s.%s' % (domain.__module__, domain.__name__)
        return domain
    
    def _get_obj_filename(self, domain, key):
        h = Hasher()
        h.update((domain, key))
        digest = h.format_digest()
        return pjoin(self.cache_path, digest[:2], digest[2:])

    def put(self, domain, key, value):
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
            to perform the lookup; this is present to enforce that
            keyspaces don't collide. If a type is passed, then its
            fully qualified name is taken as the domain string.

        key : object
            Object that is hashable with :cls:`Hasher`.

        value : object
            Pickleable object.
        """
        domain = self._as_domain(domain)
        obj_filename = self._get_obj_filename(domain, key)

        # memory cache
        if obj_filename in self.memory_cache:
            # already stored from this same cache object; don't bother with writing
            # to disk
            return
        self.memory_cache[obj_filename] = value
        
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

        key : object
            Object that is hashable with :cls:`Hasher`.

        default : object (optional)
            Object to return if lookup fails. If not present, a KeyError
            is raised.
        """
        domain = self._as_domain(domain)
        obj_filename = self._get_obj_filename(domain, key)
        try:
            x = self.memory_cache[obj_filename]
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
                x = self.memory_cache[obj_filename] = pickle.load(f)
        return x

class NullCache(object):
    def put(self, domain, key, value):
        pass

    def get(self, domain, key, default=_RAISE):
        if default is _RAISE:
            raise KeyError('keys are never found in the NullCache')
        else:
            return default
