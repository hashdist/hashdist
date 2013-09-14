from ...core.test.utils import *
from .. import utils

def test_substitute():
    env = {"A": "a", "B": "b"}
    def check(want, x):
        eq_(want, utils.substitute_profile_parameters(x, env))
    def check_noop(x):
        check(x, x)
    def check_raises(x):
        with assert_raises(KeyError):
            utils.substitute_profile_parameters(x, env)
    yield check_raises, "a${{Ax}}b"
    yield check_noop, "$A$B"
    yield check_noop, "${A}x"
    yield check_noop, "\\${A}x"
    yield check_noop, "\\\\${A}x"
    yield check_noop, "${A}\$\${x}"

    yield check, "abcb\n\nb", "a${{B}}c${{B}}\n\n${{B}}"
