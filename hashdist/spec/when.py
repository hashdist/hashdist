"""
Tools for dealing with YAML documents with the 'when (expr):' construct.
"""
import re

from ..formats import marked_yaml
from .profile import eval_condition


CONDITIONAL_RE = re.compile(r'^when (.*)$')

#
# AST transform style -- returns a document like the one from formats.marked_yaml,
# but also annotates with the 'when' condition in effect at that point, and strips
# the explicit 'when'-clauses from the document
#
def create_node_class(cls):
    class node_class(cls):
        def __init__(self, x, when):
            cls.__init__(self, x, x.start_mark, x.end_mark)
            self.when = when

        def __new__(self, x, when):
            return cls.__new__(self, x, x.start_mark, x.end_mark)
    node_class.__name__ = cls.__name__
    return node_class


dict_node = create_node_class(marked_yaml.dict_node)
list_node = create_node_class(marked_yaml.list_node)
int_node = create_node_class(marked_yaml.int_node)
unicode_node = create_node_class(marked_yaml.unicode_node)
null_node = create_node_class(marked_yaml.null_node)
bool_node = create_node_class(marked_yaml.bool_node)


def sexpr_and(x, y):
    if x is None:
        return y
    elif y is None:
        return x
    else:
        return '(%s) and (%s)' % (x, y)


def when_transform_yaml(doc, when=None):
    """
    Takes the YAML-like document `doc` (dicts, lists, primitive types) and
    transforms it into Node, under the condition `when`.
    """
    mapping = {
        marked_yaml.dict_node: _transform_dict,
        marked_yaml.list_node: _transform_list,
        marked_yaml.int_node: int_node,
        marked_yaml.unicode_node: unicode_node,
        marked_yaml.null_node: null_node,
        marked_yaml.bool_node: bool_node}
    return mapping[type(doc)](doc, when)

def _transform_dict(doc, when):
    result = dict_node(marked_yaml.dict_like(doc), when)

    for key, value in doc.items():
        m = CONDITIONAL_RE.match(unicode(key))
        if m:
            if not isinstance(value, dict):
                raise PackageError(value, "'when' dict entry must contain another dict")
            sub_when = sexpr_and(when, m.group(1))
            to_merge = _transform_dict(value, sub_when)
            for k, v in to_merge.items():
                if k in result:
                    raise PackageError(k, "key '%s' conflicts with another key of the same name "
                                       "in another when-clause" % k)
                result[k] = v
        else:
            result[key] = when_transform_yaml(value, when)
    return result

def _transform_list(doc, when):
    result = list_node(marked_yaml.list_node([], doc.start_mark, doc.end_mark), when)
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
                result.extend(to_extend)
            else:
                result.append(when_transform_yaml(item, when))
        elif isinstance(item, dict) and 'when' in item:
            # lst has the form [..., {'when': EXPR, 'sibling_key': 'value'}, ...]
            item_copy = marked_yaml.copy_dict_node(item)
            sub_when = sexpr_and(when, item_copy.pop('when'))
            result.append(when_transform_yaml(item_copy, sub_when))
        else:
            result.append(when_transform_yaml(item, when))
    return result


def has_sub_conditions(doc):
    """
    Returns False if all `.when` attributes are the same in the entire subtree `doc`,
    or True if there is variation.
    """
    if isinstance(doc, dict):
        for child in doc.values():
            if child.when != doc.when:
                return True
        else:
            return False
    elif isinstance(doc, list):
        for child in doc:
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
# Immediate evaluation given parameter values
#

def recursive_process_conditional_dict(doc, parameters):
    result = dict_like(doc)

    for key, value in doc.items():
        m = CONDITIONAL_RE.match(key)
        if m:
            if eval_condition(m.group(1), parameters):
                if not isinstance(value, dict):
                    raise PackageError(value, "'when' dict entry must contain another dict")
                to_merge = recursive_process_conditional_dict(value, parameters)
                for k, v in to_merge.items():
                    if k in result:
                        raise PackageError(k, "key '%s' conflicts with another key of the same name "
                                           "in another when-clause" % k)
                    result[k] = v
        else:
            result[key] = recursive_process_conditionals(value, parameters)
    return result

def recursive_process_conditional_list(lst, parameters):
    if hasattr(lst, 'start_mark'):
        result = list_node([], lst.start_mark, lst.end_mark)
    else:
        result = []
    for item in lst:
        if isinstance(item, dict) and len(item) == 1:
            # lst the form [..., {'when EXPR': BODY}, ...]
            key, value = item.items()[0]
            m = CONDITIONAL_RE.match(key)
            if m:
                if eval_condition(m.group(1), parameters):
                    if not isinstance(value, list):
                        raise PackageError(value, "'when' clause within list must contain another list")
                    to_extend = recursive_process_conditional_list(value, parameters)
                    result.extend(to_extend)
            else:
                result.append(recursive_process_conditionals(item, parameters))
        elif isinstance(item, dict) and 'when' in item:
            # lst has the form [..., {'when': EXPR, 'sibling_key': 'value'}, ...]
            if eval_condition(item['when'], parameters):
                item_copy = copy_dict_node(item)
                del item_copy['when']
                result.append(recursive_process_conditionals(item_copy, parameters))
        else:
            result.append(recursive_process_conditionals(item, parameters))
    return result

def recursive_process_conditionals(doc, parameters):
    if isinstance(doc, dict):
        return recursive_process_conditional_dict(doc, parameters)
    elif isinstance(doc, list):
        return recursive_process_conditional_list(doc, parameters)
    else:
        return doc
