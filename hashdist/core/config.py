"""
Handles reading the Hashdist configuration file. By default this is
``~/.hashdistconfig``.
"""

import os
from ConfigParser import RawConfigParser

DEFAULT_CONFIG_FILENAME = os.path.expanduser('~/.hashdistconfig')

class InifileConfiguration(object):
    """
    Provides access to configuration data.

    This default implementation simply wraps a RawConfigParser.
    """
    
    def __init__(self, config_parser):
        self.config_parser = config_parser

    @staticmethod
    def create_from_string(s):
        from StringIO import StringIO
        parser = RawConfigParser()
        parser.readfp(StringIO(s))
        return InifileConfiguration(parser)

    @staticmethod
    def create(filename=None):
        if filename is None:
            filename = DEFAULT_CONFIG_FILENAME
        parser = RawConfigParser()
        parser.read(filename)
        return InifileConfiguration(parser)

    def get(self, section, key):
        return self.config_parser.get(section, key)

    def get_path(self, section, key):
        x = self.get(section, key)
        return os.path.expanduser(x)

