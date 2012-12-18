from textwrap import dedent

from ..core import BuildSpec

from .recipes import Recipe, FetchSourceCode

class ConfigureMakeInstall(Recipe):
    def __init__(self, name, version, source_url, source_key,
                 configure_flags=[], **kw):
        source_fetches = [FetchSourceCode(source_url, source_key, strip=1)]
        Recipe.__init__(self, name, version, source_fetches, **kw)
        self.configure_flags = configure_flags

    def get_commands(self):
        return [['./configure', '--prefix=${TARGET}'] + self.configure_flags,
                ['make'],
                ['make', 'install']]

