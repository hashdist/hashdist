"""
Internal side of the Python hook file machinery.

The current strategy is to always reload the .py files for every new
package build. This makes the @stage_handler decorators execute again
and register with the global `current_package_context`.
"""

import imp
import sys
import contextlib
from . import hook_api

HOOK_MOD_NAME = '__hashdist_build_hook__'

current_package_context = None

def load_hooks(ctx, hook_files):
    """
    Takes a newly constructed PackageBuildContext `ctx` and runs hook files given in `hook_files`; these
    will register callbacks in `ctx` when ran.
    """
    global current_package_context
    assert current_package_context is None
    assert HOOK_MOD_NAME not in sys.modules
    imp.acquire_lock()
    try:
        current_package_context = ctx  # assign to global var
        # call imports, which uses decorators that register with current_package_context
        for filename in hook_files:
            mod = imp.load_source(HOOK_MOD_NAME, filename)
            current_package_context.register_module(mod)
            del sys.modules[HOOK_MOD_NAME]
    finally:
        imp.release_lock()
        current_package_context = None

@contextlib.contextmanager
def python_path_and_modules_sandbox(python_path_entries=()):
    """
    Context manager that temporarily inserts additional entries in sys.path.
    After exiting the context manager, sys.path and sys.modules are reverted
    to the contents they had on entry.
    """
    old_sys_path = sys.path[:]
    old_modules = dict(sys.modules)
    try:
        sys.path[0:0] = python_path_entries
        yield
    finally:
        sys.path[:] = old_sys_path
        sys.modules.clear()
        sys.modules.update(old_modules)

def bash_handler(ctx, stage):
    if 'files' in stage:
        for f in stage['files']:
            ctx.bundle_file(f)
    return stage['bash'].strip().split('\n')
