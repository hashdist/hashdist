import re

from ..hasher import Hasher

from ..common import SHORT_ARTIFACT_ID_LEN
from .. import run_job

class BuildSpec(object):
    """Wraps the document corresponding to a build.json

    The document is wrapped in order to a) signal that is has been
    canonicalized, b) make the artifact id available under the
    artifact_id attribute.
    """

    def __init__(self, build_spec):
        self.doc = canonicalize_build_spec(build_spec)
        self.name = self.doc['name']
        self.version = self.doc['version']
        digest = Hasher(self.doc).format_digest()
        self.digest = digest
        self.artifact_id = '%s/%s' % (self.name, digest)

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
        item = dict(item)
        item.setdefault('strip', 0)
        item.setdefault('target', '.')
        return item

    def canonicalize_dependency(item):
        item = dict(item)
        item.setdefault('in_path', True)
        item.setdefault('in_hdist_compiler_paths', True)
        if item.setdefault('ref', None) == '':
            raise ValueError('Empty ref should be None, not ""')
        item['before'] = sorted(item.get('before', []))
        return item

    result = dict(spec) # shallow copy
    assert_safe_name(result['name'])
    assert_safe_name(result['version'])
    result['build'] = run_job.canonicalize_job_spec(result['build'])
    sources = [canonicalize_source_item(item) for item in result.get('sources', ())]
    sources.sort(key=lambda item: item['key'])
    result['sources'] = sources

    result['files'] = sorted(result.get('files', []), key=lambda item: item['target'])

    return result

def strip_comments(spec):
    """Strips a build spec (which should be in canonical format) of comments
    that should not affect hash
    """
    raise NotImplementedError("please fix")
    def strip_desc(obj):
        r = dict(obj)
        if 'desc' in r:
            del r['desc']
        return r
    
    result = dict(spec)
    result['dependencies'] = [strip_desc(x) for x in spec['dependencies']]
    return result

_SAFE_NAME_RE = re.compile(r'[a-zA-Z0-9-_+]+')
def assert_safe_name(x):
    """Raises a ValueError if x does not match ``[a-zA-Z0-9-_+]+``.

    Returns `x`
    """
    if not _SAFE_NAME_RE.match(x):
        raise ValueError('version or name "%s" is empty or contains illegal characters' % x)
    return x


def shorten_artifact_id(artifact_id, length=SHORT_ARTIFACT_ID_LEN):
    """Shortens the hash part of the artifact_id to the desired length
    """
    name, digest = artifact_id.split('/')
    return '%s/%s' % (name, digest[:length])

