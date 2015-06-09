#encoding: utf-8
from nose.tools import eq_
from .. import version
from ..version import Version


def test_version():
    assert Version('1.2b1') == Version('1.2b1')
    assert Version('1.2b1') != Version('1.2c1')
    assert Version('1.2b1') < Version('1.2c1')
    assert Version('1.2b1') <= Version('1.2c1')
    assert Version('1.2c1') > Version('1.2b1')
    assert Version('1.2c1') >= Version('1.2b1')
    assert Version('1.2.3') > Version('1.2')
    assert Version('1.2.3') < Version('1.3')

    assert Version('1.10.1') > Version('1.9')

    eq_(str(Version('1.2.3')), "1.2.3")
    eq_(repr(Version('1.2.3')), "Version('1.2.3')")
    eq_(hash(Version('1.2')), hash(Version('1.2')))


def test_extract_string_literals():

    def f(s):
        mangled_s, literals = version.extract_string_literals(s)
        got = version.insert_string_literals(mangled_s, literals)
        eq_(s, got)
        return mangled_s
    
    eq_(f('x == "foo bar: Æ "'), 'x == __s0s')
    eq_(f("x == 'foo'"), 'x == __s0s')
    eq_(f("x('bar') == 'foo''a'"), 'x(__s0s) == __s1s')
    eq_(f(r"x == 'foo\'a''\''"), 'x == __s0s')


def test_version_literal():
    eq_(version.preprocess_version_literal('x == "3.4.5" == \'3.4.5\' == 3.4.5 == 3.4'),
        "x == \"3.4.5\" == '3.4.5' == Version('3.4.5') == Version('3.4')")
    eq_(version.preprocess_version_literal('a1.2.3'), 'a1.2.3')
    eq_(version.preprocess_version_literal('a.b.1.2.3'), 'a.b.1.2.3')
    eq_(version.preprocess_version_literal('"1.2"'), '"1.2"')
    eq_(version.preprocess_version_literal('1.2.1a1'), "Version('1.2.1a1')")
