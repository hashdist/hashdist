from StringIO import StringIO
import re

from nose.tools import eq_
from .. import hasher

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

def test_hashing():
    digest = hasher.Hasher({'a' : 3, 'b' : {'c' : [1, 2]}}).format_digest()
    assert 'VYhTUMZ6+KQApO19G8tbuN83sNU' == digest


# If we re-introduce generic ignore capabilities
#def test_hash_json_ignore():
#    ignore = re.compile(r'^(/a/k/x)|(.*/nohash.*)$')
#    assert_json_hash('dict((a)dict((i)dict((x)int(3))(k)dict((y)int(5))))', {
#        'a' : {'i' : {'x' : 3}, 'k': {'x':4,'y':5, 'nohash-x' : {'a' : 'b'}}},
#        'nohash-foo' : [3,4]
#        }, ignore)
