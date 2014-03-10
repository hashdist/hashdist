"""
A PyYAML loader subclass that is fit for parsing DSLs: It annotates
positions in source code, and only parses values as strings.

The loader is based on `SafeConstructor`, i.e., the behaviour of
`yaml.safe_load`, but in addition:

 - Every dict/list/unicode/int is replaced with dict_node/list_node/unicode_node/int_node,
   which subclasses dict/list/unicode to add the attributes `start_mark`
   and `end_mark`. (See the yaml.error module for the `Mark` class.)

 - Every string is always returned as unicode, no ASCII-ficiation is
   attempted.

"""

from hashdist.deps.yaml.error import Mark
from hashdist.deps.yaml.composer import Composer
from hashdist.deps.yaml.reader import Reader
from hashdist.deps.yaml.scanner import Scanner
from hashdist.deps.yaml.composer import Composer
from hashdist.deps.yaml.resolver import Resolver
from hashdist.deps.yaml.parser import Parser
from hashdist.deps.yaml.constructor import (Constructor, BaseConstructor, SafeConstructor,
                                            ConstructorError)
from hashdist.deps.yaml import dump as _orig_yaml_dump
from hashdist.deps import jsonschema

from .templated_stream import TemplatedStream

def _find_mark(doc):
    """Traverse a document to try to find a start_mark attribute"""
    if hasattr(doc, 'start_mark'):
        return doc.start_mark
    elif isinstance(doc, dict):
        for key, value in doc.iteritems():
            mark = _find_mark(key) or _find_mark(value)
            if mark:
                return mark
    elif isinstance(doc, list):
        for item in doc:
            mark = _find_mark(item)
            if mark:
                return mark
    else:
        return None

class ValidationError(Exception):
    def __init__(self, mark, message=None, wrapped=None):
        if not isinstance(mark, Mark):
            mark = _find_mark(mark)
        self.mark = mark
        self.message = message
        self.wrapped = wrapped

    def __str__(self):
        loc = '<unknown location>' if self.mark is None else '%s, line %d' % (self.mark.name, self.mark.line + 1)
        return '%s: %s' % (loc, self.message)

class ExpectedKeyMissingError(KeyError, ValidationError):
    def __init__(self, mark, message, **kw):
        KeyError.__init__(self, message)
        ValidationError.__init__(self, mark, message, **kw)

    def __str__(self):
        return ValidationError.__str__(self)

def create_node_class(cls, name=None):
    class node_class(cls):
        def __init__(self, x, start_mark, end_mark):
            if cls is not object:
                cls.__init__(self, x)
            self.start_mark = start_mark
            self.end_mark = end_mark

        def __new__(self, x, start_mark, end_mark):
            if cls is not object:
                return cls.__new__(self, x)
            else:
                return object.__new__(self)

    node_class.__name__ = name if name else '%s_node' % cls.__name__
    return node_class

list_node = create_node_class(list)
int_node = create_node_class(int)
unicode_node_base = create_node_class(unicode)
class unicode_node(unicode_node_base):
    # override to drop the irritating u in reprs, as it will be in Python 3 anyway
    def __repr__(self):
        r = unicode_node_base.__repr__(self)
        if r.startswith('u'):
            r = r[1:]
        return r

class null_node(create_node_class(object, name='null_node')):
    def __nonzero__(self):
        return False

    def __repr__(self):
        return "null"

def is_null(x):
    return type(x) is null_node or x is None

class dict_node(create_node_class(dict)):
    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            raise ExpectedKeyMissingError(self, 'expected key "%s" not found' % key)

def copy_dict_node(d):
    """
    Makes a copy of the dict `d`, preserving dict_node status if it is a dict_node,
    otherwise returning a dict.
    """
    if isinstance(d, dict_node):
        return dict_node(d, d.start_mark, d.end_mark)
    else:
        return dict(d)

def dict_like(d):
    """
    Make a new dict, preserving any start/end marks of `d`.
    """
    if isinstance(d, dict_node):
        return dict_node({}, d.start_mark, d.end_mark)
    else:
        return {}

class NodeConstructor(SafeConstructor):
    # To support lazy loading, the original constructors first yield
    # an empty object, then fill them in when iterated. Due to
    # laziness we omit this behaviour (and will only do "deep
    # construction") by first exhausting iterators, then yielding
    # copies.
    def construct_yaml_map(self, node):
        obj, = SafeConstructor.construct_yaml_map(self, node)
        return dict_node(obj, node.start_mark, node.end_mark)

    def construct_yaml_seq(self, node):
        obj, = SafeConstructor.construct_yaml_seq(self, node)
        return list_node(obj, node.start_mark, node.end_mark)

    def construct_yaml_str(self, node):
        obj = SafeConstructor.construct_scalar(self, node)
        assert isinstance(obj, unicode)
        return unicode_node(obj, node.start_mark, node.end_mark)

    def construct_yaml_int(self, node):
        obj = SafeConstructor.construct_yaml_int(self, node)
        return int_node(obj, node.start_mark, node.end_mark)

    def construct_yaml_null(self, node):
        return null_node(None, node.start_mark, node.end_mark)

NodeConstructor.add_constructor(
        u'tag:yaml.org,2002:map',
        NodeConstructor.construct_yaml_map)

NodeConstructor.add_constructor(
        u'tag:yaml.org,2002:seq',
        NodeConstructor.construct_yaml_seq)

NodeConstructor.add_constructor(
        u'tag:yaml.org,2002:str',
        NodeConstructor.construct_yaml_str)

NodeConstructor.add_constructor(
        u'tag:yaml.org,2002:int',
        NodeConstructor.construct_yaml_int)

NodeConstructor.add_constructor(
        u'tag:yaml.org,2002:null',
        NodeConstructor.construct_yaml_null)


class MarkedLoader(Reader, Scanner, Parser, Composer, NodeConstructor, Resolver):
    def __init__(self, stream, filecaption):
        Reader.__init__(self, stream, filecaption)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        SafeConstructor.__init__(self)
        Resolver.__init__(self)

def marked_yaml_load(stream, filecaption=None):
    return MarkedLoader(stream, filecaption).get_single_data()


def load_yaml_from_file(filename, parameters=None, filecaption=None):
    if parameters == None: parameters = {}

    with open(filename) as file_stream:
        expanded_stream = TemplatedStream(file_stream, parameters)
        expanded_stream.name = filename
        return marked_yaml_load(expanded_stream, filecaption)

def validate_yaml(doc, schema):
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as e:
        raise ValidationError(e.instance.start_mark, e.message, e)

def raw_tree(doc):
    """
    Converts a document consisting of subclasses of
    basestring/dict/list/etc. to raw str/dict/list/etc.
    """
    if isinstance(doc, basestring):
        return str(doc)
    elif isinstance(doc, int):
        return int(doc)
    elif isinstance(doc, bool):
        return bool(doc)
    elif isinstance(doc, null_node):
        return None
    elif isinstance(doc, dict):
        return dict(((raw_tree(key), raw_tree(value)) for key, value in doc.items()))
    elif isinstance(doc, (list, tuple)):
        return [raw_tree(child) for child in doc]
    else:
        raise TypeError('document contains illegal type %r' % type(doc))

def yaml_dump(doc, **opts):
    return _orig_yaml_dump(raw_tree(doc), **opts)
