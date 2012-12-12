from .core import get_artifact_id, single_file_key

class SourceItem(object):
    def __init__(self, key, target):
        self.key = key
        self.target = target
        
    def get_spec(self):
        return {'key': self.key,
                'target': self.target}

    def get_secure_hash(self):
        return 'hashdist.package.source_item.SourceItem', self.key

class DownloadSourceCode(SourceItem):
    def __init__(self, url, key, target='.'):
        SourceItem.__init__(self, key, target)
        self.url = url

    def fetch_into(self, source_cache):
        source_cache.fetch_archive(self.url, self.key)
                        
class PutScript(SourceItem):
    def __init__(self, filename, contents, target='.'):
        key = single_file_key(filename, contents)
        SourceItem.__init__(self, key, target)
        self.filename = filename
        self.contents = contents

    def fetch_into(self, source_cache):
        source_cache.put(self.filename, self.contents)


class Package(object):
    def __init__(self, name, version, sources, command, dependencies, env):
        for dep in dependencies:
            if not isinstance(dep, Package):
                raise TypeError('Expected Package instance as dependency')

        self.name = name
        self.version = version
        self.sources = sources
        self.command = command
        self.dependencies = dependencies
        self.env = env
        self.build_spec = self._make_build_spec()
        self.artifact_id = get_artifact_id(self.build_spec)

    def _make_build_spec(self):
        source_specs = [source_item.get_spec() for source_item in self.sources]
        dep_artifact_ids = dict((name, pkg.artifact_id)
                                for name, pkg in self.dependencies.iteritems())
        build_spec = {'name': self.name,
                      'version': self.version,
                      'command': self.command,
                      'env': self.env,
                      'dependencies': dep_artifact_ids,
                      'sources': source_specs}
        return build_spec

    def __hash__(self):
        return hash(self.artifact_id)

    def __eq__(self, other):
        if not isinstance(other, Package):
            return False
        else:
            return self.artifact_id == other.artifact_id

    def __ne__(self, other):
        return not self == other

def build_packages(build_store, source_cache, packages):
    built = {} # package -> artifact_id

    def _depth_first_build(package):
        if package in built:
            return built[package]

        # Recurse
        for dep_pkg in package.dependencies.values():
            _depth_first_build(dep_pkg)

        # Upload/download sources to source cache
        for source_item in package.sources:
            source_item.fetch_into(source_cache)

        # Do the build
        build_store.ensure_present(package.build_spec, source_cache)
    
    for package in packages:
        _depth_first_build(package)    
