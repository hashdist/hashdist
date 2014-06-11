from pprint import pprint
import os
from os.path import join as pjoin
from textwrap import dedent
from .. import config
from .. import marked_yaml
from ...core.test.utils import temp_working_dir_fixture, working_directory, dump, logger



@temp_working_dir_fixture
def test_schema_error(d):
    dump('config.yaml', """\
        # a comment

        build_stores: {a: 3}
        cache: a
        build_temp: a
        source_caches: [{dir: a}]
        gc_roots: a
    """)
    try:
        cfg = config.load_config_file('config.yaml', logger)
    except marked_yaml.ValidationError as e:
        assert str(e) == "config.yaml, line 3: {'a': 3} is not of type 'array'"
    else:
        assert False

@temp_working_dir_fixture
def test_load_config(d):
    dump('config.yaml', """\
        build_stores:
        - dir: ./ba
        build_temp: ./bld
        source_caches:
        - dir: ./src
        - url: http://server.com/source_cache
        cache: ./cache
        gc_roots: ./gcroots
    """)
    with working_directory('/'):
        c = config.load_config_file(pjoin(d, 'config.yaml'), logger)

    assert c == {
        'build_stores': [{'dir': pjoin(d, 'ba')}],
        'build_temp': pjoin(d, 'bld'),
        'cache': pjoin(d, 'cache'),
        'gc_roots': pjoin(d, 'gcroots'),
        'source_caches': [{'dir': pjoin(d, 'src')},
                          {'url': 'http://server.com/source_cache'}]}
