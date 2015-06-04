from pprint import pprint
from ...core.test.utils import *
from ...formats import marked_yaml
from .. import spec_ast
from ..exceptions import PackageError
from StringIO import StringIO


def load_when_doc_from_str(s):
    doc = marked_yaml.marked_yaml_load(StringIO(s))
    pdoc = spec_ast.when_transform_yaml(doc)
    return pdoc


def test_leaf_transform():
    x = spec_ast.when_transform_yaml(marked_yaml.int_node(1, None, None))
    assert type(x) is spec_ast.int_node


def test_type_transform():
    pdoc = load_when_doc_from_str('''
    a:
       b: [c, d, 3, 4, null, {a: b}]
       x:
         - 1
         - 2: 3
    ''')
    eq_(type(pdoc.value['a'].value['x'].value[0]), spec_ast.int_node)
    eq_(type(pdoc.value['a'].value['x'].value[1].value[2]), spec_ast.int_node)
    eq_(type(pdoc.value['a'].value['b'].value[4]), spec_ast.null_node)
    eq_(type(pdoc), spec_ast.dict_node)
    # Keys are not transformed:
    eq_(type(pdoc.value.keys()[0]), marked_yaml.unicode_node)
    eq_(type(pdoc.value['a'].value.keys()[0]), marked_yaml.unicode_node)


def test_when_transform():
    pdoc = load_when_doc_from_str('''
    when x == 0:
       b: [c, {when use_d: [d1, d2]}, 3, 4, null, {a: b}]
       x:
         - 1
         - 2: 3
           when: use_2
    ''')
    eq_(set(pdoc.value.keys()), set(['b', 'x']))
    eq_(pdoc.value['b'].when, 'x == 0')
    eq_(pdoc.value['b'].value[0].when, 'x == 0')
    eq_(pdoc.value['b'].value[1].when, '(x == 0) and (use_d)')
    eq_(pdoc.value['b'].value[2].when, '(x == 0) and (use_d)')
    eq_(pdoc.value['b'].value[3].when, 'x == 0')
    eq_(pdoc.value['x'].value[0].when, 'x == 0')
    eq_(pdoc.value['x'].value[1].when, '(x == 0) and (use_2)')


def test_scalar_result_mixed_with_dict():
    doc = load_when_doc_from_str("""\
    dictionary:
        when platform == 'linux':
            when host:
                one: this{{platform}}hey
            two: {'when host': 2, 'when not host': 3}
    """)


def test_eval_dictionary():
    doc = load_when_doc_from_str("""\
    dictionary:
        when platform == 'linux':
            when host:
                one: this{{platform}}hey
            two: {'when host': 2, 'when not host': 3}
    """)
    r = spec_ast.evaluate_doc(doc, {'platform': 'linux', 'host': True})
    assert {'dictionary': {'one': 'thislinuxhey', 'two': 2}} == r
    r = spec_ast.evaluate_doc(doc, {'platform': 'linux', 'host': False})
    assert {'dictionary': {'two': 3}} == r
    r = spec_ast.evaluate_doc(doc, {'platform': 'windows', 'host': False})
    assert {'dictionary': {}} == r

def test_sub_bool_gives_error():
    doc = load_when_doc_from_str("{a: '{{var}}'}")
    with assert_raises(PackageError) as e:
        spec_ast.evaluate_doc(doc, {'var': True})
    assert 'expression must return a string: var' in str(e.exc_val)

def test_eval_list():
    doc = load_when_doc_from_str("""\
    dictionary:
    - when platform == 'linux':
      - when host:
        - 1
      - 2
    - foo{{platform}}nes
    - {nested: dict} # dict of length 1
    - am-on: host
      when: host
    """)
    r = spec_ast.evaluate_doc(doc, {'platform': 'linux', 'host': True})
    assert {'dictionary': [1, 2, 'foolinuxnes', {'nested': 'dict'}, {'am-on': 'host'}]} == r
    r = spec_ast.evaluate_doc(doc, {'platform': 'linux', 'host': False})
    assert {'dictionary': [2, 'foolinuxnes', {'nested': 'dict'}]} == r
    r = spec_ast.evaluate_doc(doc, {'platform': 'windows', 'host': False})
    assert {'dictionary': ['foowindowsnes', {'nested': 'dict'}]} == r
