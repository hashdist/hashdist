import os
from os.path import join as pjoin

from .marked_yaml import marked_yaml_load

class PackageSpec(object):
    def __init__(self, doc, build_deps, run_deps):
        self.doc = doc
        self.build_deps = build_deps
        self.run_deps = run_deps        

    @staticmethod
    def load(doc, resolver):
        deps = doc.get('dependencies', {})
        build_deps = PackageSpecSet(resolver, deps.get('build', []))
        run_deps = PackageSpecSet(resolver, deps.get('run', []))
        return PackageSpec(doc, build_deps, run_deps)

class PackageSpecSet(object):
    """
    A dict-like representing a subset of packages, but they are lazily
    loaded
    """
    def __init__(self, resolver, packages):
        self.resolver = resolver
        self.packages = packages
        self._values = None

    def __getitem__(self, key):
        if key not in self.packages:
            raise KeyError('Package %s not found' % key)
        return self.resolver.parse_package(key)

    def values(self):
        if self._values is None:
            self._values = [self[key] for key in self.packages]
        return self._values

    def keys(self):
        return list(self.packages)

    def __repr__(self):
        return '<%s: %r>' % (self.__class__.__name__, self.packages)


_package_spec_cache = {}
class PackageSpecResolver(object):
    def __init__(self, path):
        self.path = path

    def parse_package(self, pkgname):
        filename = os.path.realpath(pjoin(self.path, pkgname, '%s.yaml' % pkgname))
        obj = _package_spec_cache.get(filename, None)
        if obj is None:
            with open(filename) as f:
                doc = marked_yaml_load(f)
            obj = _package_spec_cache[filename] = PackageSpec.load(doc, self)
        return obj

