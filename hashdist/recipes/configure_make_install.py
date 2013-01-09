from textwrap import dedent

from .recipes import Recipe, FetchSourceCode

class ConfigureMakeInstall(Recipe):
    def __init__(self, name, version, source_url, source_key,
                 configure_flags=[], strip=None, **kw):
        if strip is None:
            strip = 0 if source_key.startswith('git:') else 1
        source_fetches = [FetchSourceCode(source_url, source_key, strip=strip)]
        Recipe.__init__(self, name, version, source_fetches, **kw)
        self.configure_flags = configure_flags

    def get_commands(self):
        return [
            ['LDFLAGS=$HDIST_LDFLAGS', 'CFLAGS=$HDIST_CFLAGS', './configure', '--prefix=${ARTIFACT}'] +
            self.configure_flags,
            ['make'],
            ['make', 'install']
            ]
    
    def get_files(self):
        artifact_json = {
          "install": {
            "commands": [
              ["hdist", "create-links", "--key=install/parameters/links", "artifact.json"]
            ],
            "parameters": {
              "links": [
                {"action": "symlink", "select": "$ARTIFACT/*/**/*", "prefix": "$ARTIFACT",
                 "target": "$PROFILE"}
              ]
            }
          }
        }

        return [
            {"target": "$ARTIFACT/artifact.json", "object": artifact_json}
        ]
