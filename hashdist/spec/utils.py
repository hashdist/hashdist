import re
from .exceptions import ProfileError

_STACK_SUBST_RE = re.compile(r'\{\{([^}]*)\}\}')

def substitute_profile_parameters(s, parameters):
    """
    Substitutes using the syntax ``{{param}}``.

    If {{param}} is undefined, the empty string is returned instead.
    """
    def repl(m):
        return parameters.get(m.group(1), '')

    return _STACK_SUBST_RE.subn(repl, s)[0]


class GraphCycleError(Exception):
    pass

def topological_sort(roots, get_deps):
    def toposort(node):
        if node in visiting:
            raise GraphCycleError()
        if node not in visited:
            visiting.add(node)
            for dep in sorted(get_deps(node)):
                toposort(dep)
            visiting.remove(node)
            visited.add(node)
            result.append(node)

    visited = set()
    visiting = set()
    result = []
    for node in sorted(roots):
        toposort(node)
    return result

def to_env_var(x):
    return x.upper().replace('-', '_')
