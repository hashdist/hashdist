import ast
from pprint import pprint
from ...core.test.utils import *
from ...formats import marked_yaml
from .. import spec_ast
from ..exceptions import PackageError
from ..exceptions import ProfileError
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
    eq_(pdoc.value['b'].when.expr, 'x == 0')
    eq_(pdoc.value['b'].value[0].when.expr, 'x == 0')
    eq_(pdoc.value['b'].value[1].when.expr, '(x == 0) and (use_d)')
    eq_(pdoc.value['b'].value[2].when.expr, '(x == 0) and (use_d)')
    eq_(pdoc.value['b'].value[3].when.expr, 'x == 0')
    eq_(pdoc.value['x'].value[0].when.expr, 'x == 0')
    eq_(pdoc.value['x'].value[1].when.expr, '(x == 0) and (use_2)')


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

def test_Expr():
    e = spec_ast.Expr('x or 2', int)
    eq_(e.eval({'x': False}), 2)
    eq_(e.eval({'x': True}), 1)
    with assert_raises(ProfileError) as ex:
        e.eval({})
    assert 'parameter not defined' in str(ex.exc_val)
    with assert_raises(PackageError) as ex:
        spec_ast.Expr('<<<')
    assert 'syntax error' in str(ex.exc_val)
    eq_(e.references, set(['x']))

def test_StrExpr():
    e = spec_ast.StrExpr('plain string')
    eq_(e.eval({}), 'plain string')

    e = spec_ast.StrExpr('x is {{str(x)}} causing {{x or 2}}')
    eq_(e.eval({'x': False}), 'x is False causing 2')

    with assert_raises(PackageError):  # ends up returning bool, not allowed
        eq_(e.eval({'x': True}), 'x is False causing 2')
    eq_(e.references, set(['x']))

