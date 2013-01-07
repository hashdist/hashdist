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

NOT_PRESENT = object()

class DiskCache(object):
    def __init__(self, cache_path):
        self.cache_path = cache_path
    
    @staticmethod
    def create_from_config(config, logger):
        """Creates a Cache from the settings in the configuration
        """
        return Cache(config.get_path('general', 'cache'))

    def _get_obj_filename(self, domain, key):
        h = Hasher()
        h.update((domain, key))
        digest = h.format_digest()
        return pjoin(self.cache_path, digest[:2], digest[2:])

    def put(self, domain, key, value):
        """Puts a value to the store

        This should be atomic and race-safe, provided that everybody who
        does a put puts the same value.

        Parameters
        ----------

        domain : str
            Should be a string that is combined with the key to perform
            the lookup; this is present to enforce that keyspaces don't
            collide

        key : object
            Object that is hashable with :cls:`Hasher`.

        value : object
            Pickleable object
        """
        obj_filename = self._get_obj_filename(domain, key)
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

    def get(self, domain, key, default=NOT_PRESENT):
        """Looks up value from store

        Parameters
        ----------

        domain : str
            Should be a string that is combined with the key to perform
            the lookup; this is present to enforce that keyspaces don't
            collide

        key : object
            Object that is hashable with :cls:`Hasher`.

        default : object (optional)
            Object to return if lookup fails; defaults to `NOT_PRESENT`.
        """
        obj_filename = self._get_obj_filename(domain, key)

        try:
            f = file(obj_filename)
        except IOError, e:
            if e.errno != errno.ENOENT:
                raise
            return default
        
        with f:
            return pickle.load(f)
