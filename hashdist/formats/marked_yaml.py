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


from hashdist.deps.yaml.composer import Composer
from hashdist.deps.yaml.reader import Reader
from hashdist.deps.yaml.scanner import Scanner
from hashdist.deps.yaml.composer import Composer
from hashdist.deps.yaml.resolver import Resolver
from hashdist.deps.yaml.parser import Parser
from hashdist.deps.yaml.constructor import (Constructor, BaseConstructor, SafeConstructor,
                                            ConstructorError)
from hashdist.deps import jsonschema

class ValidationError(Exception):
    def __init__(self, mark, message=None, wrapped=None):
        self.mark = mark
        self.message = message
        self.wrapped = wrapped

    def __str__(self):
        return '%s, line %d: %s' % (self.mark.name, self.mark.line, self.message)


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

dict_node = create_node_class(dict)
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
    def __repr__(self):
        return "null"

def is_null(x):
    return type(x) is null_node

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
    try:
        return MarkedLoader(stream, filecaption).get_single_data()
    except ConstructorError as e:
        raise ValidationError(e.problem_mark, e.problem, e)

def load_yaml_from_file(filename, filecaption=None):
    with open(filename) as f:
        return marked_yaml_load(f, filecaption)


def validate_yaml(doc, schema):
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as e:
        raise ValidationError(e.instance.start_mark, e.message, e)
