import sys
from pprint import pprint
from textwrap import dedent
from ...core.test.utils import *
from .. import hook
from .. import hook_api
from ...formats.marked_yaml import marked_yaml_load

@temp_working_dir_fixture
def test_hook_loading(d):
    dump('numberechoing.py', """\
    from hashdist import build_stage

    times_called = [0]

    @build_stage()
    def my_build_stage_handler1(ctx, stage):
        import myutils  # should be found in base
        result = myutils.get_one() + times_called[0]
        times_called[0] += 1
        return result
    """)

    dump('base/second.py', """\
    from hashdist import build_stage

    @build_stage()
    def my_build_stage_handler2(ctx, stage):
        return 2
    """)

    dump('base/myutils.py', """\
    def get_one(): return 1
    """)


    with hook.python_path_and_modules_sandbox(['base']):
        ctx = hook_api.PackageBuildContext(None, {}, {})
        hook.load_hooks(ctx, ['numberechoing.py', 'base/second.py'])
        assert 1 == ctx._build_stage_handlers['my_build_stage_handler1'](None, None)
        assert 2 == ctx._build_stage_handlers['my_build_stage_handler1'](None, None)  # returns no. times called
        assert 2 == ctx._build_stage_handlers['my_build_stage_handler2'](None, None)

        # load again, should be reset
        ctx = hook_api.PackageBuildContext(None, {}, {})
        hook.load_hooks(ctx, ['numberechoing.py', 'base/second.py'])
        assert 1 == ctx._build_stage_handlers['my_build_stage_handler1'](None, None)

    assert 'myutils' not in sys.modules
    assert 'base' not in sys.path
