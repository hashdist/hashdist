from textwrap import dedent
import struct

from ..hasher import Hasher
from .source_item import DownloadSourceCode, PutScript

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
        
        self._secure_hash = Hasher([name, version, sources, command, env]).raw_digest()
        self._weak_hash = struct.unpack('=i', self._secure_hash[:4])[0]

    def get_build_spec(self, builder):
        dep_specs = dict((key, dep.artifact_id) for key, dep in self.dependencies.iteritems)
            

    def _make_hash(self):
        h = create_hasher()
        h.update(self.name)
        h.update(self.version)

    def get_secure_hash(self):
        return 'hashdist.package.package.Package', self._secure_hash

    def __hash__(self):
        return self._weak_hash

    def __eq__(self, other):
        if not isinstance(other, Package):
            return False
        else:
            return self._secure_hash == other._secure_hash

    def __ne__(self, other):
        return not self == other

def build_packages(builder, packages):
    built = {} # package -> artifact_id
    source_cache = builder.source_cache

    def _depth_first_build(package):
        if package in built:
            return built[package]

        # Fetch sources
        for source_item in package.sources:
            source_item.fetch_into(source_cache)
        source_specs = [source_item.get_spec() for source_item in package.sources]

        # Recurse and get dependency ids
        dep_artifact_ids = {}
        for dep_name, dep_pkg in package.dependencies.iteritems():
            dep_artifact_ids[dep_name] = _depth_first_build(dep_pkg)

        build_spec = {'name': package.name,
                      'version': package.version,
                      'command': package.command,
                      'env': package.env,
                      'dependencies': dep_artifact_ids,
                      'sources': source_specs}
        
        artifact_id, path = builder.ensure_present(build_spec)
        return artifact_id
    
    for package in packages:
        _depth_first_build(package)    


class ConfigureMakeInstallPackage(Package):
    def __init__(self, name, version, source_url, source_key, configure_flags=(), **kw):
        script = self._make_script(configure_flags)
        
        # Split **kw into dependencies (packages) and env (strings, ints, floats)
        dependencies = {}
        env = {}
        for key, value in kw.iteritems():
            if isinstance(value, Package):
                dependencies[key] = value
            elif isinstance(value, (str, int, float)):
                env[key] = value
            else:
                raise TypeError('Meaning of passing argument %s of type %r not understood' %
                                (key, type(value)))

        Package.__init__(self, name, version,
                         sources=[DownloadSourceCode(source_url, source_key),
                                  PutScript('build.sh', script)],
                         command=['/bin/bash', 'build.sh'],
                         dependencies=dependencies,
                         env=env)
    @staticmethod
    def _make_script(configure_flags):
        configure_flags_s = ' '.join(
            '"%s"' % flag.replace('\\', '\\\\').replace('"', '\\"')
            for flag in configure_flags)
        
        script = dedent('''\
            set -e
            cd zlib-1.2.7
            ./configure %(configure_flags_s)s --prefix="${PREFIX}"
            make
            make DESTDIR="${STAGE}" install
        ''') % locals()
        
        return script

