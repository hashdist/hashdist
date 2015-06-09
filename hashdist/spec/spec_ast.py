"""
Tools for dealing with the build spec YAML documents on a structural
level:
 - the 'when (expr):' construct
 - the `{{var}}` expansion.
"""
import re
import sys

from .exceptions import ProfileError, PackageError
from ..formats import marked_yaml
from .version import Version, preprocess_version_literal


GLOBALS_LST = [len, Version]
GLOBALS = dict((entry.__name__, entry) for entry in GLOBALS_LST)


def _handle_dash(expr, parameters):
    new_parameters = dict((key.replace('-', '_dash_'), value) for key, value in parameters.items())
    return expr.replace('-', '_dash_'), new_parameters


def preprocess(expr, parameters):
    expr, parameters = _handle_dash(expr, parameters)
    expr = preprocess_version_literal(expr)
    return expr, parameters


def eval_condition(expr, parameters):
    if expr is None:  # A NoneType argument means no condition, evaluates to True, while 'None' as a str will evaluate False
        return True
    expr_p, parameters_p = preprocess(expr, parameters)
    try:
        return bool(eval(expr_p, GLOBALS, parameters_p))
    except NameError as e:
        raise ProfileError(expr, "parameter not defined: %s" % e)
    except SyntaxError as e:
        raise PackageError(expr, "syntax error in expression '%s'" % expr_p)
    except:
        raise PackageError(expr, "exception %s raised during execution of \"%s\": %r" % (
            sys.exc_info()[0].__name__, expr_p, str(sys.exc_info()[1])))


ALLOW_STRINGIFY = (basestring, int, Version)
DENY_STRINGIFY = (bool,)  # subclass of int..

def eval_strexpr(expr, parameters, node=None):
    """
    We allow *some* stringification, but not most of them; having
    bool turn into 'True' is generally not useful
    """
    expr_p, parameters_p = preprocess(expr, parameters)
    node = node if node is not None else expr
    try:
        result = eval(expr_p, GLOBALS, parameters_p)
        if not isinstance(result, ALLOW_STRINGIFY) or isinstance(result, DENY_STRINGIFY):
            # We want to avoid bools turning into 'True' etc. without explicit
            raise PackageError(expr, "expression must return a string: %s" % expr_p)
        return str(result)
    except NameError as e:
        raise PackageError(expr, "parameter not defined: %s" % e)
    except SyntaxError as e:
        raise PackageError(expr, "syntax error in expression '%s'" % expr_p)



CONDITIONAL_RE = re.compile(r'^when (.*)$')

#
# AST transform style -- returns a document like the one from formats.marked_yaml,
# but also annotates with the 'when' condition in effect at that point, and strips
# the explicit 'when'-clauses from the document
#
def create_node_class(cls):
    class node_class(object):
        def __init__(self, x, when):
            self.value = x
            self.start_mark = x.start_mark
            self.end_mark = x.end_mark
            self.when = when

        def get_value(self, key, default):
            # only relevant on dict_node..
            if key not in self.value:
                return default
            else:
                return self.value[key].value

    node_class.__name__ = cls.__name__
    return node_class


dict_node = create_node_class(marked_yaml.dict_node)
list_node = create_node_class(marked_yaml.list_node)
int_node = create_node_class(marked_yaml.int_node)
unicode_node = create_node_class(marked_yaml.unicode_node)
null_node = create_node_class(marked_yaml.null_node)
bool_node = create_node_class(marked_yaml.bool_node)

class choose_value_node(object):
    """
    Contains a list of children, of which only one should be picked
    (should have a true when clause).

    self.when is really redundant, but present for consistency and
    to mark the common part of the when clause of all children
    """
    def __init__(self, children, when):
        self.children = children
        self.start_mark = children[0].start_mark if children else None
        self.end_mark = children[0].end_mark if children else None
        self.when = when


def sexpr_and(x, y):
    if x is None:
        return y
    elif y is None:
        return x
    else:
        return '(%s) and (%s)' % (x, y)


def sexpr_or(x, y):
    if x is None or y is None:
        return None
    else:
        return '(%s) or (%s)' % (x, y)


def sexpr_implies(when, then):
    assert then is not None
    if when is None:
        return then
    else:
        return 'not (%s) or (%s)' % (when, then)

def when_transform_yaml(doc, when=None):
    """
    Takes the YAML-like document `doc` (dicts, lists, primitive types) and
    transforms it into Node, under the condition `when`.
    """
    if type(doc) is dict and len(doc) == 0:
        # Special case, it's so convenient to do foo.get(key, {})...
        return dict_node(marked_yaml.dict_node({}, None, None), when)
    mapping = {
        marked_yaml.dict_node: _transform_dict,
        marked_yaml.list_node: _transform_list,
        marked_yaml.int_node: int_node,
        marked_yaml.unicode_node: unicode_node,
        marked_yaml.null_node: null_node,
        marked_yaml.bool_node: bool_node}
    return mapping[type(doc)](doc, when)

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
        sub_when = sexpr_and(when, m.group(1))
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
            sub_when = sexpr_and(when, m.group(1))
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
                sub_when = sexpr_and(when, m.group(1))
                to_extend = _transform_list(value, sub_when)
                result.extend(to_extend.value)
            else:
                result.append(when_transform_yaml(item, when))
        elif isinstance(item, dict) and 'when' in item:
            # lst has the form [..., {'when': EXPR, 'sibling_key': 'value'}, ...]
            item_copy = marked_yaml.copy_dict_node(item)
            sub_when = sexpr_and(when, item_copy.pop('when'))
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
    elif isinstance(doc, unicode_node):
        return evaluate_unicode(doc, parameters)
    elif isinstance(doc, choose_value_node):
        return evaluate_choose(doc, parameters)
    elif isinstance(doc, (int_node, null_node, bool_node)):
        return doc.value
    else:
        raise ValueError('doc was not an AST node: %r of type %s' % (doc, type(doc)))

DBRACE_RE = re.compile(r'\{\{([^}]+)\}\}')

def evaluate_unicode(doc, parameters):
    """
    Evaluate anything in {{ }} using eval_strexpr in the context of parameters.
    """
    def dbrace_expand(match):
        return eval_strexpr(match.group(1), parameters, node=doc)
    return marked_yaml.unicode_node(DBRACE_RE.sub(dbrace_expand, doc.value), doc.start_mark, doc.end_mark)


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
