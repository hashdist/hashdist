from textwrap import dedent

from ..core import BuildSpec

from .recipes import Recipe, FetchSourceCode

class ConfigureMakeInstall(Recipe):
    def __init__(self, name, version, source_url, source_key,
                 configure_flags=[], strip=None, **kw):
        if strip is None:
            strip = 0 if source_key.startswith('git:') else 1
        source_fetches = [FetchSourceCode(source_url, source_key, strip=strip)]
        Recipe.__init__(self, name, version, source_fetches, **kw)
        self.configure_flags = configure_flags

    def get_env(self):
        return {'CCACHE_PATH': '/home/dagss/.hdist/opt/gcc-stack/host/o982/bin'}

    def get_commands(self):
        return [
            ['which', 'gcc'],
            ['gcc', '--version'],
            ['LDFLAGS=$HDIST_ACREL_LDFLAGS', 'CFLAGS=$HDIST_CFLAGS', './configure', '--prefix=${ARTIFACT}'] +
            self.configure_flags,
            ['make'],
            ['make', 'install']
            ]

