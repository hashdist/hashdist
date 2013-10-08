import copy
from StringIO import StringIO
import re

from nose.tools import eq_
from .. import hasher
from .utils import assert_raises

def test_prune_nohash():
    doc = {'a': [[{'nohash_foo': [1,2,3]},
                 1, True, False, None, 2.3, 'asdf']],
           'nohash_foo': True}
    doc_copy = copy.deepcopy(doc)
    assert {'a': [[{}, 1, True, False, None, 2.3, 'asdf']]} == hasher.prune_nohash(doc)
    # check we didn't change anything in original
    assert doc == doc_copy

def test_hash_document_fp_fails():
    with assert_raises(TypeError):
        hasher.hash_document([1, {'a': {'b': {3.4: 3}}}])

def test_hash_document():
    doc_a = {'a': [[{'nohash_foo': [1,2,3]}, 1, True, False, None, 2, 'asdf']], 'nohash_foo': True}
    h = hasher.hash_document('test', doc_a)
    assert h == 'geecc25mccuaba37cwsquibd2iisgo6f'

#
# Hasher
#

class Sink:
    # "Hashes" the data by simply creating a string out of it
    def __init__(self):
        self.buf = StringIO()
    def update(self, x):
        self.buf.write(x)
    def getvalue(self):
        return self.buf.getvalue()

def assert_serialize(expected, doc):
    sink = Sink()
    serializer = hasher.DocumentSerializer(sink)
    serializer.update(doc)
    eq_(expected, sink.getvalue())

def test_serialization():
    class Foo(object):
        def get_secure_hash(self):
            return 'hashdist.test.test_hasher.Foo', 'foo'

    yield assert_serialize, 'D2:' 'B1:a' 'I1:3' 'B1:b' 'I1:4', {'a' : 3, 'b' : 4}
    yield assert_serialize, 'B1:a', u'a'
    yield assert_serialize, 'B2:\xc2\x99', u'\x99'
    yield assert_serialize, 'B2:\xc2\x99', (u'\x99').encode('UTF-8')
    yield assert_serialize, 'B2:\xc2\x99', buffer((u'\x99').encode('UTF-8'))
    yield assert_serialize, 'F\x00\x00\x00\x00\x00\x00\n@', 3.25
    yield assert_serialize, 'I1:1', 1
    yield assert_serialize, 'L2:' 'I1:1' 'I1:2', [1, 2]
    yield assert_serialize, 'L2:' 'I1:1' 'I1:2', (1, 2)
    yield assert_serialize, 'D2:B1:aI1:3B1:bD1:B1:cL2:I1:1I1:2', {'a' : 3, 'b' : {'c' : [1, 2]}}
    yield assert_serialize, 'O29:hashdist.test.test_hasher.Foo3:foo', Foo()

def test_hashing():
    digest = hasher.Hasher({'a' : 3, 'b' : {'c' : [1, 2]}}).format_digest()
    assert 'kwefguggpl4kiafe5v6rxs23xdptpmgv' == digest

