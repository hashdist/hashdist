"""
Tools for dealing with the build spec YAML documents on a structural
level:
 - the 'when (expr):' construct
 - the `{{var}}` expansion.
"""
import re
import sys
import ast

from .exceptions import ProfileError, PackageError
from ..formats import marked_yaml
from .version import Version, preprocess_version_literal


GLOBALS_LST = [len, Version]
GLOBALS = dict((entry.__name__, entry) for entry in GLOBALS_LST)


def get_var_references(node):
    result = set()
    for node in ast.walk(node):
        if isinstance(node, ast.Name):
            if node.id not in GLOBALS and node.id not in __builtins__:
                result.add(node.id)
    return frozenset(result)


class CoerceError(Exception):
    """Signals that result coercion failed, is used so that a ProfileError with annotated
       info can be raised instead"""


class BaseExpr(object):
    def __init__(self, expr, node=None):
        if isinstance(expr, basestring):
            node = node or expr
        self.node = node
        self.expr = expr
        if node and hasattr(node, 'start_mark'):
            self.source = str(node.start_mark)
            self.start_mark = node.start_mark
            self.end_mark = node.end_mark
        else:
            self.source = '<string>'


class Expr(BaseExpr):
    """
    Represents a Python expression. The argument to the construtor should be a Python
    expression. It is pre-parsed, parsed, dependencies found and made available in self.references,
    and can be evaluated.

    Currently we don't really combine expressions on the AST level, instead expressions
    are combined on a string level and a new Expr constructed, and the Python AST discarded.
    """

    def __init__(self, expr, result_coercion=lambda x: x, node=None):
        if isinstance(expr, Expr):
            expr = expr.expr
        super(Expr, self).__init__(expr, node=node)
        expr = preprocess_version_literal(expr)
        try:
            root_node = ast.parse(expr, mode='eval')
        except SyntaxError as e:
            raise PackageError(self, "syntax error in expression '%s'" % self.node)
        self.references = get_var_references(root_node)
        self.compiled = compile(root_node, self.source, mode='eval')
        self.result_coercion = result_coercion

    def eval(self, parameters):
        parameters = _handle_dash(parameters)
        try:
            return self.result_coercion(eval(self.compiled, GLOBALS, parameters))
        except CoerceError as e:
            reason = str(e)
            raise PackageError(self, "expression %s: %s" % (reason, self.expr))
        except NameError as e:
            raise ProfileError(self, "in expression '%s': %s" % (self.expr, e))
        except:
            raise PackageError(self, "exception %s raised during execution of \"%s\": %r" % (
                sys.exc_info()[0].__name__, self.node, str(sys.exc_info()[1])))

    def always_true(self):
        return self.expr == 'True'


TRUE_EXPR = Expr('True', bool)


class StrExpr(BaseExpr):
    """
    An string-building expression like "foo{{expr1}}bar{{expr2}}baz". Each of the {{ }}-blocks
    are independent Expr objects.

    All value strings in our AST are of this type (i.e. containing any {{ } is optional}).
    """
    DBRACE_RE = re.compile(r'\{\{([^}]+)\}\}')
    ALLOW_STRINGIFY = (basestring, int, Version)
    DENY_STRINGIFY = (bool,)  # subclass of int..

    def __init__(self, expr, when=None, node=None):
        super(StrExpr, self).__init__(expr, node)
        self.when = when

        self.expressions = []
        def f(match):
            idx = len(self.expressions)
            self.expressions.append(Expr(match.group(1), self.coerce_expr_result, node=self.node))
            return '{{%d}}' % idx
        self.template, __ = self.DBRACE_RE.subn(f, expr)
        self.references = (reduce(frozenset.union, [child.references for child in self.expressions], frozenset())
                           .union(self.when.references if self.when is not None else set()))

    @classmethod
    def coerce_expr_result(cls, x):
        if not isinstance(x, cls.ALLOW_STRINGIFY) or isinstance(x, cls.DENY_STRINGIFY):
            raise CoerceError('must return a string')
        return unicode(x)

    def eval(self, parameters):
        def f(match):
            return self.expressions[int(match.group(1))].eval(parameters)
        result, __ = self.DBRACE_RE.subn(f, self.template)
        return result


def _handle_dash(parameters):
    new_parameters = dict((preprocess_package_name(key), value) for key, value in parameters.items())
    return new_parameters


def preprocess_package_name(name):
    return name.replace('-', '_dash_')


def eval_condition(expr, parameters):
    if expr is None:  # A NoneType argument means no condition, evaluates to True, while 'None' as a str will evaluate False
        return True
    else:
        return expr.eval(parameters)


CONDITIONAL_RE = re.compile(r'^when (.*)$')

#
# AST transform style -- returns a document like the one from formats.marked_yaml,
# but also annotates with the 'when' condition in effect at that point, and strips
# the explicit 'when'-clauses from the document
#
class BaseNode(object):
    def __init__(self, x, when):
        if not isinstance(when, Expr):
            raise TypeError()
        self.value = x
        self.start_mark = x.start_mark
        self.end_mark = x.end_mark
        self.when = when
        self.references = (
            reduce(frozenset.union, [child.references for child in self.get_children()], frozenset())
            .union(self.when.references if self.when is not None else set()))

    def get_children(self):
        return ()


class dict_node(BaseNode):
    def get_children(self):
        return self.value.values()

    def get_value(self, key, default):
        # only relevant on dict_node..
        if key not in self.value:
            return default
        else:
            return self.value[key].value


class list_node(BaseNode):
    def get_children(self):
        return self.value


class int_node(BaseNode):
    pass


class null_node(BaseNode):
    pass


class bool_node(BaseNode):
    pass


class choose_value_node(object):
    """
    Contains a list of children, of which only one should be picked
    (should have a true when clause).

    self.when is really redundant, but present for consistency and
    to mark the common part of the when clause of all children
    """
    def __init__(self, children, when):
        self.children = tuple(children)  # make sure it's immutable
        self.start_mark = children[0].start_mark if children else None
        self.end_mark = children[0].end_mark if children else None
        self.when = when
        self.references = reduce(frozenset.union, (child.references for child in self.children), frozenset())

def expr_and(x, y):
    if x.always_true():
        return y
    elif y.always_true():
        return x
    else:
        return Expr(sexpr_and(x.expr, y.expr), bool)

def expr_or(x, y):
    if x.always_true() or y.always_true():
        return TRUE_EXPR
    else:
        return Expr(sexpr_or(x.expr, y.expr), bool)

def expr_implies(when, then):
    if when.always_true():
        return then
    else:
        return Expr(sexpr_implies(when.expr, then.expr), bool)


def sexpr_and(x, y):
    # The Expr acts simply as a wrapper that should probably die somehow..
    if isinstance(x, Expr):
        x = x.expr
    if isinstance(y, Expr):
        y = y.expr
    if x is None:
        return y
    elif y is None:
        return x
    else:
        return '(%s) and (%s)' % (x, y)


def sexpr_or(x, y):
    # The Expr acts simply as a wrapper that should probably die somehow..
    if isinstance(x, Expr):
        x = x.expr
    if isinstance(y, Expr):
        y = y.expr
    if x is None or y is None:
        return None
    else:
        return '(%s) or (%s)' % (x, y)


def sexpr_implies(when, then):
    assert then is not None
    # The Expr acts simply as a wrapper that should probably die somehow..
    if when is None:
        return then
    else:
        return 'not (%s) or (%s)' % (when, then)


def when_transform_yaml(doc, when=TRUE_EXPR):
    """
    Takes the YAML-like document `doc` (dicts, lists, primitive types) and
    transforms it into Node, under the condition `when`.
    """
    assert when is not None
    if type(doc) is dict and len(doc) == 0:
        # Special case, it's so convenient to do foo.get(key, {})...
        return dict_node(marked_yaml.dict_node({}, None, None), when)
    mapping = {
        marked_yaml.dict_node: _transform_dict,
        marked_yaml.list_node: _transform_list,
        marked_yaml.int_node: int_node,
        marked_yaml.unicode_node: StrExpr,
        marked_yaml.null_node: null_node,
        marked_yaml.bool_node: bool_node}
    return mapping[type(doc)](doc, Expr(when, result_coercion=bool))

def _transform_dict(doc, when):
    # Probe whether we should assume merge-in-dict or choose-a-scalar behaviour
    if len(doc) > 0:
        key, value = doc.items()[0]
        if CONDITIONAL_RE.match(unicode(key)) and not isinstance(value, dict):
            return _transform_choose_scalar(doc, when)
    return _transform_dict_merge(doc, when)


def _transform_choose_scalar(doc, when):
    children = []
    for key, value in doc.items():
        m = CONDITIONAL_RE.match(unicode(key))
        if not m:
            raise PackageError(value, "all dict entries must be a 'when'-clause if a sibling when-clause "
                                      "contains a scalar")
        sub_when = expr_and(when, Expr(m.group(1), True))
        children.append(when_transform_yaml(value, sub_when))
    return choose_value_node(children, when)


def _transform_dict_merge(doc, when):
    assert isinstance(doc, marked_yaml.dict_node)
    result = marked_yaml.dict_like(doc)

    for key, value in doc.items():
        m = CONDITIONAL_RE.match(unicode(key))
        if m:
            if not isinstance(value, dict):
                raise PackageError(value, "'when' dict entry must contain another dict")
            sub_when = expr_and(when, Expr(m.group(1), True))
            to_merge = _transform_dict(value, sub_when)
            for k, v in to_merge.value.items():
                if k in result:
                    raise PackageError(k, "key '%s' conflicts with another key of the same name "
                                       "in another when-clause" % k)
                result[k] = v
        else:
            result[key] = when_transform_yaml(value, when)
    return dict_node(result, when)

def _transform_list(doc, when):
    result = []
    for item in doc:
        if isinstance(item, dict) and len(item) == 1:
            # lst the form [..., {'when EXPR': BODY}, ...]
            key, value = item.items()[0]
            m = CONDITIONAL_RE.match(unicode(key))
            if m:
                if not isinstance(value, list):
                    raise PackageError(value, "'when' clause within list must contain another list")
                sub_when = expr_and(when, Expr(m.group(1), bool))
                to_extend = _transform_list(value, sub_when)
                result.extend(to_extend.value)
            else:
                result.append(when_transform_yaml(item, when))
        elif isinstance(item, dict) and 'when' in item:
            # lst has the form [..., {'when': EXPR, 'sibling_key': 'value'}, ...]
            item_copy = marked_yaml.copy_dict_node(item)
            sub_when = expr_and(when, Expr(item_copy.pop('when'), bool))
            result.append(when_transform_yaml(item_copy, sub_when))
        else:
            result.append(when_transform_yaml(item, when))
    return list_node(marked_yaml.list_node(result, doc.start_mark, doc.end_mark), when)


def has_sub_conditions(doc):
    """
    Returns False if all `.when` attributes are the same in the entire subtree `doc`,
    or True if there is variation.
    """
    if isinstance(doc, dict):
        for child in doc.value.values():
            if child.when != doc.when:
                return True
        else:
            return False
    elif isinstance(doc, list):
        for child in doc.value:
            if child.when != doc.when:
                return True
        else:
            return False
    else:
        return False

def check_no_sub_conditions(doc):
    if has_sub_conditions(doc):
        raise PackageError(doc, 'when-clause present in a place it is disallowed')


#
# Immediate evaluation given parameter values, keeping the marked_yaml ast..
#
def evaluate_doc(doc, parameters):
    """
    Evaluates `doc`, which should be an AST of dict_node/list_node/...

    The result is using the marked_yaml node format.

    Code flow:

    The convention is that container classes evaluate the `when` attribute
    of their children in order to figure out whether to include them. The
    `doc` argument never has its when attribute examined in the scope of
    the call.
    """
    if isinstance(doc, dict_node):
        return evaluate_dict(doc, parameters)
    elif isinstance(doc, list_node):
        return evaluate_list(doc, parameters)
    elif isinstance(doc, choose_value_node):
        return evaluate_choose(doc, parameters)
    elif isinstance(doc, StrExpr):
        return doc.eval(parameters)
    elif isinstance(doc, (int_node, null_node, bool_node)):
        return doc.value
    else:
        raise ValueError('doc was not an AST node: %r of type %s' % (doc, type(doc)))


def evaluate_dict(doc, parameters):
    result = {}

    for key, value in doc.value.items():
        if eval_condition(value.when, parameters):
            result[key] = evaluate_doc(value, parameters)
    return marked_yaml.dict_node(result, doc.start_mark, doc.end_mark)


def evaluate_list(doc, parameters):
    result = marked_yaml.list_node([], doc.start_mark, doc.end_mark)
    for item in doc.value:
        if eval_condition(item.when, parameters):
            result.append(evaluate_doc(item, parameters))
    return result


def evaluate_choose(doc, parameters):
    results = [evaluate_doc(x, parameters) for x in doc.children
               if eval_condition(x.when, parameters)]
    if len(results) != 1:
        raise PackageError(doc, "Exactly one of the when-conditions should apply "
                           "in every situation")
    return results[0]
