import re

from ..hasher import Hasher


class InvalidBuildSpecError(ValueError):
    pass


class BuildSpec(object):
    def __init__(self, build_spec):
        self.doc = canonicalize_build_spec(build_spec)
        self.artifact_id = get_artifact_id(self.doc)


def as_build_spec(obj):
    if isinstance(obj, BuildSpec):
        return obj
    else:
        return BuildSpec(obj)

def canonicalize_build_spec(spec):
    """Puts the build spec on a canonical form + basic validation

    See module documentation for information on the build specification.

    Parameters
    ----------
    spec : json-like
        The build specification

    Returns
    -------
    canonical_spec : json-like
        Canonicalized and verified build spec
    """
    def canonicalize_source_item(item):
        item = dict(item) # copy
        if 'strip' not in item:
            item['strip'] = 0
        if 'target' not in item:
            item['target'] = "."
        return item

    result = dict(spec) # shallow copy
    assert_safe_name(result['name'])
    assert_safe_name(result['version'])

    if 'sources' in result:
        sources = [canonicalize_source_item(item) for item in result['sources']]
        sources.sort(key=lambda item: item['key'])
        result['sources'] = sources

    if 'files' in result:
        result['files'] = sorted(result['files'], key=lambda item: item['target'])

    return result

_SAFE_NAME_RE = re.compile(r'[a-zA-Z0-9-_+]+')
def assert_safe_name(x):
    """Raises a ValueError if x does not match ``[a-zA-Z0-9-_+]+``.

    Returns `x`
    """
    if not _SAFE_NAME_RE.match(x):
        raise ValueError('"%s" is empty or contains illegal characters')
    return x

def get_artifact_id(build_spec, is_canonical=False):
    """Produces the hash/"artifact id" from the given build spec.

    This can be produced merely from the textual form of the spec without
    considering any run-time state on any system.
    
    """
    if not is_canonical:
        build_spec = canonicalize_build_spec(build_spec)
    digest = Hasher(build_spec).format_digest()
    name = assert_safe_name(build_spec['name'])
    version = assert_safe_name(build_spec['version'])
    
    return '%s/%s/%s' % (name, version, digest)

def shorten_artifact_id(artifact_id, length):
    """Shortens the hash part of the artifact_id to the desired length
    """
    return artifact_id[:artifact_id.rindex('/') + length + 1]

