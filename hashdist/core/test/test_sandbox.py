from nose.tools import eq_, assert_raises
from ..sandbox import stable_topological_sort

def test_stable_topological_sort():
    def check(expected, problem):
        # pack simpler problem description into objects
        problem_objs = [dict(id=id, before=before, preserve=id[::-1])
                        for id, before in problem]
        got = stable_topological_sort(problem_objs)
        got_ids = [x['id'] for x in got]
        assert expected == got_ids
        for obj in got:
            assert obj['preserve'] == obj['id'][::-1]
    
    problem = [
        ("t-shirt", []),
        ("sweater", ["t-shirt"]),
        ("shoes", []),
        ("space suit", ["sweater", "socks", "underwear"]),
        ("underwear", []),
        ("socks", []),
        ]

    check(['shoes', 'space suit', 'sweater', 't-shirt', 'underwear', 'socks'], problem)
    # change order of two leaves
    problem[-2], problem[-1] = problem[-1], problem[-2]
    check(['shoes', 'space suit', 'sweater', 't-shirt', 'socks', 'underwear'], problem)
    # change order of two roots (shoes and space suit)
    problem[2], problem[3] = problem[3], problem[2]
    check(['space suit', 'sweater', 't-shirt', 'socks', 'underwear', 'shoes'], problem)

    # error conditions
    with assert_raises(ValueError):
        # repeat element
        check([], problem + [("socks", [])])

    with assert_raises(ValueError):
        # cycle
        check([], [("x", ["y"]), ("y", ["x"])])
