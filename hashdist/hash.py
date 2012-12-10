"""
Utilities and single configuration point for hashing
====================================================

"""

import hashlib
import base64
import struct

create_hasher = hashlib.sha256

def encode_digest(hasher):
    """Hashdist's standard format for encoding hash digests

    Parameters
    ----------
    hasher : hasher object
        Should pass the object returned by create_hasher to extract its digest.
    """
    return base64.b64encode(hasher.digest()[:20], altchars='+-').replace('=', '')



def hash_json(hasher, doc, ignore_pattern=None, prefix=''):
    """Hashes a JSON structure, ignoring some of the keys

    The `hasher` is updated with the contents of the JSON structure `doc`
    (i.e., a nested structure of dict, list, str, and various scalar types). Assuming
    that the "outer" nodes are dictionaries, their key names are matched
    against `ignore_pattern` and ignored if there is a match. Consider
    for instance this document::

        {"a" : { "b" : 1, "c" : 2}}

    To ignore the inner ``"b"`` key, `ignore_pattern` should be set up to
    match ``"/a/b"``.

    Parameters
    ----------

    hasher : hasher object
        Will be used to hash the document

    doc : json document
        Document to hash

    ignore_pattern : compiled regex or None
        Document keys to ignore (see description above)

    prefix : str or None (optional)
        Prefix to add to all keys in the document (when `doc` is a dict),
        mainly for internal use.

    Returns
    -------

    No return value
    """
    # We need to protect against documents that hash to the same
    # value. We do this by using envelopes corresponding to the object
    # structure (of the form "type(item)(item)..."); and making
    # sure that ( and ) are escaped in any strings, and the escape
    # character escaped too.
    
    def sanitize(x):
        return x.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    if isinstance(doc, (str, unicode)):
        hasher.update('str(')
        hasher.update(sanitize(doc))
        hasher.update(')')
    elif isinstance(doc, float):
        # can contain ", but always 8 bytes so don't bother to sanitize or envelope
        hasher.update('float')
        hasher.update(struct.pack('<d', doc))
    elif isinstance(doc, int):
        # assume: ints can't contain " in stringification
        hasher.update('int(%d)' % doc)
    elif isinstance(doc, (list, tuple)):
        hasher.update('list')
        for item in doc:
            hasher.update('(')
            hash_json(hasher, item, None)
            hasher.update(')')
    elif isinstance(doc, dict):
        hasher.update('dict(')
        for key, value in sorted(doc.items()):
            if not isinstance(key, (str, unicode)):
                raise TypeError('doc is not a JSON document (non-str key)')
            q_key = '/'.join((prefix, key))
            if ignore_pattern is not None and ignore_pattern.match(q_key):
                continue
            hasher.update('(')
            hasher.update(sanitize(key))
            hasher.update(')')
            hash_json(hasher, value, ignore_pattern, q_key)
        hasher.update(')')
    else:
        raise TypeError('doc is not a JSON document')
