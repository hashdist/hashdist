from StringIO import StringIO
import re

from nose.tools import eq_
from .. import hash

class MockHasher:
    # "Hashes" the data by simply creating a string out of it
    def __init__(self):
        self.buf = StringIO()
    def update(self, x):
        self.buf.write(x)
    def getvalue(self):
        return self.buf.getvalue()

def assert_json_hash(expected, doc, ignore=None):
    h = MockHasher()
    hash.hash_json(h, doc, ignore)
    eq_(expected, h.getvalue())

def test_hash_json_basic():
    yield assert_json_hash, 'dict((a)int(3)(b)int(4))', {'a' : 3, 'b' : 4}
    yield assert_json_hash, 'str(\()', u'('
    yield assert_json_hash, r'str(\\\))', r'\)'
    yield assert_json_hash, r'str(\)int\(4\)\()', ')int(4)('
    yield assert_json_hash, 'float\x00\x00\x00\x00\x00\x00\n@', 3.25
    yield assert_json_hash, 'int(1)', 1
    yield assert_json_hash, 'list(int(1))(int(2))', [1, 2]
    yield assert_json_hash, 'list(int(1))(int(2))', (1, 2)

def test_hash_json_ignore():
    ignore = re.compile(r'^(/a/k/x)|(.*/nohash.*)$')
    assert_json_hash('dict((a)dict((i)dict((x)int(3))(k)dict((y)int(5))))', {
        'a' : {'i' : {'x' : 3}, 'k': {'x':4,'y':5, 'nohash-x' : {'a' : 'b'}}},
        'nohash-foo' : [3,4]
        }, ignore)
