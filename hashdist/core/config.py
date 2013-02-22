"""
Handles reading the Hashdist configuration file. By default this is
``~/.hitconfig``.
"""

import os
from os.path import join as pjoin
import ConfigParser
import json

DEFAULT_CONFIG_FILENAME = '~/.hitconfig'

SCHEMA = {
    'global': {
        'cache': ('dir', '~/.hit/cache'),
        'db': ('dir', '~/.hit/db'),
        },
    'sourcecache': {
        'sources': ('dir', '~/.hit/src'),
        },
    'builder': {
        'build-temp': ('dir', '~/.hit/bld'),
        'artifacts': ('dir', '~/.hit/opt'),
        'artifact-dir-pattern': ('str', '{name}/{shorthash}'),
        }
    }


def load_configuration_from_inifile(filename):
    base_dir = os.path.dirname(os.path.realpath(filename))
    parser = ConfigParser.RawConfigParser()
    parser.read(filename)
    result = {}
    for section, section_schema in SCHEMA.items():
        for key, (type, default) in section_schema.items():
            try:
                value = parser.get(section, key)
            except ConfigParser.Error:
                value = default
            if type == 'dir':
                value = os.path.expanduser(value)
                if not os.path.isabs(value):
                    value = pjoin(base_dir, value)
            elif type == 'str':
                pass
            else:
                assert False
            result['%s/%s' % (section, key)] = value
    return result
        
