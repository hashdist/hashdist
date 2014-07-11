"""
:mod:`hashdist.core.hasher` -- Utilities for hashing
====================================================

"""

import json
import hashlib
import base64
import struct

hash_type = hashlib.sha256

def check_no_floating_point(doc):
    """Verifies that the document `doc` does not contain floating-point numbers.
    """
    if isinstance(doc, float):
        raise TypeError("floating-point number not allowed in document")
    elif isinstance(doc, dict):
        for k, v in doc.iteritems():
            check_no_floating_point(k)
            check_no_floating_point(v)
    elif isinstance(doc, list):
        for item in doc:
            check_no_floating_point(item)
    elif isinstance(doc, (int, bool, basestring)) or doc is None:
        pass

def hash_document(doctype, doc):
    """
    Computes a hash from a document. This is done by serializing to as
    compact JSON as possible with sorted keys, then perform sha256
    an. The string ``{doctype}|`` is prepended to the hashed string
    and serves to make sure different kind of documents yield different
    hashes even if they are identical.

    Some unicode characters have multiple possible code-points, so
    that this definition; however, this should be considered an
    extreme corner case.  In general it should be very unusual for
    hashes that are publicly shared/moves beyond one computer to
    contain anything but ASCII. However, we do not enforce this, in
    case one wishes to encode references in the local filesystem.

    Floating-point numbers are not supported (these have multiple
    representations).

    """
    check_no_floating_point(doc)
    serialized = json.dumps(doc, indent=None, sort_keys=True, separators=(',', ':'), encoding='utf-8',
                            ensure_ascii=True, allow_nan=False)
    h = hashlib.sha256(doctype + '|')
    h.update(serialized)
    return format_digest(h)

def prune_nohash(doc):
    """
    Returns a copy of the document with every key/value-pair whose key
    starts with ``'nohash_'`` is removed.
    """
    if isinstance(doc, (int, bool, float, basestring)) or doc is None:
        r = doc
    elif isinstance(doc, dict):
        r = {}
        for key, value in doc.iteritems():
            assert isinstance(key, basestring)
            if not key.startswith('nohash_'):
                r[key] = prune_nohash(value)
    elif isinstance(doc, (list, tuple)):
        r = [prune_nohash(child) for child in doc]
    else:
        raise TypeError('document contains illegal type %r' % type(doc))
    return r




def argsort(seq):
    return sorted(range(len(seq)), key=seq.__getitem__)

class DocumentSerializer(object):
    """
    Stable non-Python-specific serialization of nested
    objects/documents. The primary usecase is for hashing (see
    :class:`Hasher`), and specifically hashing of JSON documents, thus
    no de-serialization is implemented. The idea is simply that by
    hashing a proper serialization format we ensure that we don't
    weaken the hash function.

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
       be reproducible in other languages. However that is a
       possibility for further extension, as long as string keys are
       treated as today.

    In order to prevent somebody from constructing colliding documents,
    each object is hashed with an envelope specifying the type and the
    length (in number of items in the case of a container, or number of bytes
    in the case of str/unicode/buffer).

    In general, see unit tests for format examples/details.

    Parameters
    ----------

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
        elif isinstance(x, set):
            raise TypeError('sets not supported') # more friendly error
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

    This is the standard hashing method of HashDist.
    """
    def __init__(self, x=None):
        DocumentSerializer.__init__(self, hash_type())
        if x is not None:
            self.update(x)

    def digest(self):
        return self._wrapped.digest()

    def format_digest(self):
        """
        The HashDist standard digest.
        """
        return format_digest(self._wrapped)


def format_digest(hasher):
    """The HashDist standard format for encoding hash digests

    This is one of the cases where it is prudent to just repeat the
    implementation in the docstring::

        base64.b32encode(hasher.digest()[:20]).lower()

    Parameters
    ----------
    hasher : hasher object
        An object with a `digest` method (a :class:`Hasher` or
        an object from the :mod:`hashlib` module)
    """
    return base64.b32encode(hasher.digest()[:20]).lower()


class HashingWriteStream(object):
    """
    Utility for hashing and writing to a stream at the same time.
    The `stream` may be `None` for convenience.

    """
    def __init__(self, hasher, stream):
        self.hasher = hasher
        self.stream = stream

    def write(self, x):
        self.hasher.update(x)
        if self.stream is not None:
            self.stream.write(x)

    def digest(self):
        return self.hasher.digest()


class HashingReadStream(object):
    """
    Utility for reading from a stream and hashing at the same time.
    """
    def __init__(self, hasher, stream):
        self.stream = stream
        self.hasher = hasher

    def read(self, *args):
        buf = self.stream.read(*args)
        self.hasher.update(buf)
        return buf

    def digest(self):
        return self.hasher.digest()
