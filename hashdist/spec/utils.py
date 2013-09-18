import re

_STACK_SUBST_RE = re.compile(r'\$\{\{([^}]*)\}\}')

def substitute_profile_parameters(s, parameters):
    """
    Substitutes using the syntax ``${{param}}``, leaving shell substitutions
    (`${var}`, `$var`) alone. Escapes of $, ``\$``, has no special meaning
    here.
    """
    def repl(m):
        try:
            return parameters[m.group(1)]
        except:
            raise KeyError('Tried to substitute undefined parameter "%s"' % m.group(1))
    return _STACK_SUBST_RE.subn(repl, s)[0]



class GraphCycleError(Exception):
    pass

def topological_sort(roots, get_deps):
    def toposort(node):
        if node in visiting:
            raise GraphCycleError()
        if node not in visited:
            visiting.add(node)
            for dep in get_deps(node):
                toposort(dep)
            visiting.remove(node)
            visited.add(node)
            result.append(node)

    visited = set()
    visiting = set()
    result = []
    for node in roots:
        toposort(node)
    return result
    
