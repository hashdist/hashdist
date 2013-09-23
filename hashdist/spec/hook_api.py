"""
The API exported to Python hook files that are part of stack descriptions.
A significant portion of the package building logic should eventually find
its way into here.

Hook files are re-loaded for every package build, and so decorators etc.
are run again. The machinery used to Hashdist to load hook files is
found in .hook.
"""
import types
from .utils import substitute_profile_parameters

class IllegalHookFileError(Exception):
    pass

class IllegalPackageSpecError(Exception):
    pass


class PackageBuildContext(object):
    def __init__(self):
        import hook
        self._build_stage_handlers = {'bash': hook.bash_handler}
        self._modules = []
        self.parameters = {}

    def register_build_stage_handler(self, handler_name, handler_func):
        """
        Registers a function as a handler for a given stage handler type.
        """
        if handler_name in self._build_stage_handlers:
            raise IllegalHookFileError('handler for build stage "%s" already registered' % handler_name)
        self._build_stage_handlers[handler_name] = handler_func
    
    def register_module(self, mod):
        """
        Hold a reference to the registered module; this is necesary to avoid
        them getting deallocated under our feet, as we don't allow them to live
        in sys.modules.
        """
        self._modules.append(mod)

    def dispatch_build_stage(self, stage):
        # Copy stage dict and substitute all string arguments
        stage = self.deep_sub(stage)
        handler = stage.get('handler', stage['name'])
        if handler not in self._build_stage_handlers:
            raise IllegalPackageSpecError('build stage handler "%s" not registered' % handler)
        return self._build_stage_handlers[handler](self, stage)

    def sub(self, s):
        """
        Substitute ``${{var}}`` in `s` with variables from `self.parameters` in `s`,
        and return resulting string.
        """
        return substitute_profile_parameters(s, self.parameters)

    def deep_sub(self, doc):
        """
        Recursively walk the document `doc`, and for all non-key strings, make
        a substitution as described in `sub`. A deep copy is returned.
        """
        if isinstance(doc, dict):
            return dict((key, self.deep_sub(value)) for key, value in doc.iteritems())
        elif isinstance(doc, (list, tuple)):
            return [self.deep_sub(item) for item in doc]
        elif isinstance(doc, basestring):
            return self.sub(doc)
        elif isinstance(doc, (int, bool, float, NoneType)):
            return doc
        else:
            raise TypeError("unexpected item in documents of type %r: %s" % (type(doc), doc))
        


def build_stage(handler_name=None):
    """
    Decorator used to register a function as a handler generating the
    code for a given build stage.

    Parameters
    ----------

    handler_name : str (optional)
        Name of the handler, defaults to the name of the function.
    """
    def decorator(func):
        handler_name_ = handler_name
        if handler_name_ is None:
            handler_name_ = func.__name__
        import hook
        hook.current_package_context.register_build_stage_handler(handler_name_, func)
        return func
    return decorator
