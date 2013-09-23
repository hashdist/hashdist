from ..marked_yaml import marked_yaml_load

def test_marked_yaml():
    def loc(obj):
        return (obj.start_mark.line, obj.start_mark.column, obj.end_mark.line, obj.end_mark.column)
    
    d = marked_yaml_load( # note: test very sensitive to whitespace in string below
    '''\
    a:
      [b, c, {d: e}]
    f:
      g: h''')

    assert d == {'a': ['b', 'c', {'d': 'e'}], 'f': {'g': 'h'}}
    assert loc(d['a'][2]['d']) == (1, 17, 1, 18)
    assert loc(d) == (0, 4, 3, 10)
    assert loc(d['a']) == (1, 6, 1, 20)

    assert isinstance(d['a'][2]['d'], unicode)
    assert isinstance(d, dict)
    assert isinstance(d['f'], dict)
    assert isinstance(d['a'], list)

