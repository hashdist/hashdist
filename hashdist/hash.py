"""
Single configuration point for hashing
"""

import hashlib
import base64

create_hasher = hashlib.sha256

def encode_digest(hasher):
    """Hashdist's standard format for encoding hash digests"""
    return base64.b64encode(hasher.digest(), altchars='+-').replace('=', '')
