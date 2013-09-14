import re

_STACK_SUBST_RE = re.compile(r'\$\{\{([^}]*)\}\}')

def substitute_stack_parameters(s, parameters):
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
