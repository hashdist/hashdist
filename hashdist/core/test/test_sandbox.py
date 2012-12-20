from nose.tools import eq_, assert_raises
from ..sandbox import stable_topological_sort

def test_stable_topological_sort():
    problem = [
        ("t-shirt", []),
        ("sweater", ["t-shirt"]),
        ("shoes", []),
        ("space suit", ["sweater", "socks", "underwear"]),
        ("underwear", []),
        ("socks", []),
        ]
    eq_(stable_topological_sort(problem),
        ['shoes', 'space suit', 'sweater', 't-shirt', 'underwear', 'socks'])
    # change order of two leaves
    problem[-2], problem[-1] = problem[-1], problem[-2]
    eq_(stable_topological_sort(problem),
        ['shoes', 'space suit', 'sweater', 't-shirt', 'socks', 'underwear'])
    # change order of two roots (shoes and space suit)
    problem[2], problem[3] = problem[3], problem[2]
    eq_(stable_topological_sort(problem),
        ['space suit', 'sweater', 't-shirt', 'socks', 'underwear', 'shoes'])

    # error conditions
    with assert_raises(ValueError):
        # repeat element
        stable_topological_sort(problem + [("socks", [])])

    with assert_raises(ValueError):
        # cycle
        stable_topological_sort([("x", ["y"]), ("y", ["x"])])
