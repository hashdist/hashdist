"""
The API exported to Python hook files that are part of stack descriptions.


Hook files are re-loaded for every package build, and so decorators etc.
are run again. The machinery used to Hashdist to load hook files is
found in .hook.
"""

class IllegalHookFileError(Exception):
    pass


class PackageBuildContext(object):
    def __init__(self):
        self._build_stage_handlers = {}
        self._modules = []

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
