"""
Utilities and single configuration point for hashing
====================================================

"""

import hashlib
import base64
import struct

hash_type = hashlib.sha256

def argsort(seq):
    return sorted(range(len(seq)), key=seq.__getitem__)

class DocumentSerializer(object):
    """
    Stable one-non-Python-specific serialization of nested
    objects/documents. The primary usecase is for hashing (see
    :class:`Hasher`), and specifically hashing of JSON documents,
    thus no de-serialization is written. However, by
    hashing-through-serialization we ensure that we don't weaken the
    hash function.

    The API used is that of ``hashlib`` (i.e. an update method).

    A core goal is that it should be completely stable, and easy to
    reimplement in other languages. Thus we stay away from
    Python-specific pickling mechanisms etc.

    Supported types: Basic scalars (ints, floats, True, False, None),
    bytes, unicode, and buffers, lists/tuples and dicts.

    Additionally, when encountering user-defined objects with the
    ``get_secure_hash`` method, that method is called and the result
    used as the "serialization". The method should return a tuple
    (type_id, secure_hash); the former should be a string representing
    the "type" of the object (often the fully qualified class name), in order to
    avoid conflicts with the hashes of other objects, and the latter a
    hash of the contents.

    The serialization is "type-safe" so that ``"3"`` and ``3`` and ``3.0``
    will serialize differently. Lists and tuples
    are treated as the same (``(1,)`` and ``[1]`` are the same) and
    buffers, strings and Unicode objects (in their UTF-8 encoding) are
    also treated the same.

    .. note::

       Currently only string keys are supported for dicts, and the
       items are serialized in the order of the keys. This is because all
       Python objects implement comparison, and comparing by arbitrary
       Python objects could lead to easy misuse (hashes that are not
       stable across processes).

       One could instead sort the keys by their hash (getting rid of
       comparison), but that would make the hash-stream (and thus the
       unit tests) much more complicated, and the idea is this should
       be reproducable in other languages. However that is a
       possibility for further extension, as long as string keys are
       treated as today.

    Format
    ------

    In order to prevent somebody from constructing colliding documents,
    each object is hashed with an envelope specifying the type and the
    length (in number of items in the case of a container, or number of bytes
    in the case of str/unicode/buffer).

    In general, see unit tests for format examples/details.

    Constructor parameters
    ----------------------

    wrapped : object
        `wrapped.update` is called with strings or buffers to emit the
        resulting stream (the API of the ``hashlib`` hashers)
    
    
    """
    def __init__(self, wrapped):
        self._wrapped = wrapped
    
    def update(self, x):
        # note: w.update does hashing of str/buffer, self.update recurses to treat object
        w = self._wrapped
        if isinstance(x, (bytes, str)):
            # this one matters when streaming so put it first
            w.update('B%d:' % len(x))
            w.update(x)
        elif isinstance(x, unicode):
            self.update(x.encode('UTF-8'))
        elif isinstance(x, float):
            s = struct.pack('<d', x)
            assert len(s) == 8
            w.update('F')
            w.update(s)
        elif isinstance(x, int):
            # need to provide for arbitrary size...
            s = str(x)
            w.update('I%d:' % len(s))
            w.update(s)
        elif isinstance(x, (list, tuple)):
            w.update('L%d:' % len(x))
            for child in x:
                self.update(child)
        elif isinstance(x, dict):
            w.update('D%d:' % len(x))
            keys = x.keys()
            indices = argsort(keys)
            for i in indices:
                if not isinstance(keys[i], (str, unicode)):
                    raise NotImplementedError('hashing of dict with non-string key')
                self.update(keys[i])
                self.update(x[keys[i]])
        elif x is True:
            w.update('T')
        elif x is False:
            w.update('F')
        elif x is None:
            w.update('N')
        elif hasattr(x, 'get_secure_hash'):
            x_type, h = x.get_secure_hash()
            w.update('O%d:' % len(x_type))
            w.update(x_type)
            w.update('%d:' % len(h))
            w.update(h)
        else:
            # treated same as first case, but we can only fall back to
            # acquiring the buffer interface after we've tried the
            # rest
            buf = buffer(x)
            w.update('B%d:' % len(buf))
            w.update(buf)

class Hasher(DocumentSerializer):
    """
    Cryptographically hashes buffers or nested objects ("JSON-like" object structures).
    See :class:`DocumentSerializer` for more details.

    This is the standard hashing method of Hashdist.
    """
    def __init__(self, x=None):
        DocumentSerializer.__init__(self, hash_type())
        if x is not None:
            self.update(x)

    def raw_digest(self):
        return self._wrapped.digest()

    def format_digest(self):
        """
        The Hashdist standard digest.
        """
        return format_digest(self._wrapped)


def format_digest(hasher):
    """Hashdist's standard format for encoding hash digests

    Parameters
    ----------
    hasher : hasher object
        Should pass the object returned by create_hasher to extract its digest.
    """
    return base64.b64encode(hasher.digest(), altchars='+-').replace('=', '')
