from pprint import pprint
from ...core.test.utils import *
from ...formats import marked_yaml
from .. import when
from StringIO import StringIO

def test_leaf_transform():
    x = when.transform_doc_with_conditionals(marked_yaml.int_node(1, None, None))
    assert type(x) is when.int_node


def test_type_transform():
    stream = StringIO('''
    a:
       b: [c, d, 3, 4, null, {a: b}]
       x:
         - 1
         - 2: 3
    ''')
    doc = marked_yaml.marked_yaml_load(stream)
    pdoc = when.transform_doc_with_conditionals(doc)
    eq_(type(pdoc['a']['x'][0]), when.int_node)
    eq_(type(pdoc['a']['x'][1][2]), when.int_node)
    eq_(type(pdoc['a']['b'][4]), when.null_node)
    eq_(type(pdoc), when.dict_node)
    # Keys are not transformed:
    eq_(type(pdoc.keys()[0]), marked_yaml.unicode_node)
    eq_(type(pdoc['a'].keys()[0]), marked_yaml.unicode_node)


def test_when_transform():
    stream = StringIO('''
    when x == 0:
       b: [c, {when use_d: [d1, d2]}, 3, 4, null, {a: b}]
       x:
         - 1
         - 2: 3
           when: use_2
    ''')

    doc = marked_yaml.marked_yaml_load(stream)
    pdoc = when.transform_doc_with_conditionals(doc)
    eq_(set(pdoc.keys()), set(['b', 'x']))
    eq_(pdoc['b'].when, 'x == 0')
    eq_(pdoc['b'], ['c', 'd1', 'd2', 3, 4, None, {'a': 'b'}])
    eq_(pdoc['b'][0].when, 'x == 0')
    eq_(pdoc['b'][1].when, '(x == 0) and (use_d)')
    eq_(pdoc['b'][2].when, '(x == 0) and (use_d)')
    eq_(pdoc['b'][3].when, 'x == 0')
    eq_(pdoc['x'], [1, {2: 3}])
    eq_(pdoc['x'][0].when, 'x == 0')
    eq_(pdoc['x'][1].when, '(x == 0) and (use_2)')
