import os
import re
from .recipes import Recipe, FetchSourceCode

from ..host import get_host_packages

# since, on a given host, the only thing that determines a host package is
# the name, we intern the instances (to avoid having the "libc6" build spec
# re-generated 30 times...)
_interned = {}

_INTERESTING_FILE_RE = re.compile(r'^/usr/(lib.*|include|bin)/.*$')

class HostPackage(Recipe):
    def __init__(self, name):
        Recipe.__init__(self, name, 'host', in_profile=False)

    def __new__(cls, *args):
        key = tuple(args)
        if key in _interned:
            x = _interned[key]
        else:
            x = _interned[key] = object.__new__(cls, *args)
        return x

    def _initialize(self, logger, cache):
        try:
            hostpkgs = cache.get(HostPackage, 'hostpkgs')
        except KeyError:
            hostpkgs = get_host_packages(logger, cache)
            cache.put(HostPackage, 'hostpkgs', hostpkgs, on_disk=False)
        for dep in hostpkgs.get_immediate_dependencies(self.name):
            recipe = _interned.get(dep, None)
            if recipe is None:
                recipe = _interned[dep] = HostPackage(dep)
                recipe.initialize(logger, cache)
            self.dependencies[dep] = recipe

        self.files_to_link = files = []
        for filename in hostpkgs.get_files_of(self.name):
            if (_INTERESTING_FILE_RE.match(filename) and os.path.isfile(filename)):
                files.append(filename)

    def get_parameters(self):
        rules = []
        rules.append({"action": "symlink",
                      "select": self.files_to_link,
                      "prefix": "/usr",
                      "target": "$ARTIFACT"})
        return {"links": rules}

    def get_commands(self):
        return [["hdist", "create-links", "--key=parameters/links", "build.json"]]
                

