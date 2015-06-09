"""
Version type, as well as pre-preprocessing tools to introduce the version literal
in Python expressions.
"""
import re
import operator

from .exceptions import PackageError

# Import distlib versions here, rest of Hashdist should import from here
from ..deps.distlib import version as distlib_version
from ..deps.distlib.version import UnsupportedVersionError


normalized_scheme = distlib_version.get_scheme('normalized')


class Version(distlib_version.NormalizedVersion):
    """
    Inherit from distlib's NormalizeVersion -- we may want to provide convenience
    functions for matching against sets of versions etc. later.
    """


# To pick up a version literal, we pick up a very large set, then complain if it's
# not a NormalizedVersion
VERSION_LITERAL_RE = re.compile('(?<![\w.])\d+.[A-Za-z0-9-_.]+')


def preprocess_version_literal(expr):
    """
    Implements the 'version literal', e.g., 2.34d.b3 (any dotted alphanumeric
    starting with a digit). Everything in `expr` matching `VERSION_LITERAL_RE`
    is wrapped in `Version('<...>')`. Versions in strings are left unharmed.

    Raises PackageError if the version is not valid.
    """
    expr_without_strings, string_literals = extract_string_literals(expr)
    def replace(s):
        s = s.group(0)
        if not normalized_scheme.is_valid_version(s):
            raise PackageError(s, 'Illegal version: "%s". Try "%s" instead?' % (normalized_scheme.suggest(s)))
        return "Version('%s')" % s
    expr_with_version_literals, __ = VERSION_LITERAL_RE.subn(replace, expr_without_strings)
    return insert_string_literals(expr_with_version_literals, string_literals)


# The below is taken from pyparsing.quotedString.reString
STRING_RE = re.compile('(?:"(?:[^"\\n\\r\\\\]|(?:"")|(?:\\\\x[0-9a-fA-F]+)|(?:\\\\.))*")|'
                       '(?:\'(?:[^\'\\n\\r\\\\]|(?:\'\')|(?:\\\\x[0-9a-fA-F]+)|(?:\\\\.))*\')')


def extract_string_literals(expr):
    """
    Takes a Python expression string `expr`, and replaces all strings
    with identifiers `__s0s`, `__s1s`, and so on, and returns the new
    string and a dict of identifiers.

    After this step, search and replace-operations will not touch the
    contents of strings.

    NOTE: This extracts `'x''x'` as a single string token, while in
    reality it is two. However as long as the token is just substituted
    back this should not matter, the point is to extract all string tokens
    from text while `replace_version_literal` replaces version literals.
    """
    literals = {}
    def replace(x):
        varname = '__s%ds' % len(literals)
        literals[varname] = x.group(0)
        return varname
    new_expr, __ = STRING_RE.subn(replace, expr)
    return new_expr, literals


def insert_string_literals(expr, literals):
    """
    Undoes `extract_string_literals`. Called after processing.
    """
    for varname, literal in literals.items():
        expr = expr.replace(varname, literal)
    return expr
