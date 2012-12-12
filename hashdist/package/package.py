from textwrap import dedent
import struct

from ..core import get_artifact_id

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

def build_packages(builder, packages):
    built = {} # package -> artifact_id
    source_cache = builder.source_cache

    def _depth_first_build(package):
        if package in built:
            return built[package]

        # Recurse
        for dep_pkg in package.dependencies.values():
            _depth_first_build(dep_pkg)

        # Fetch sources
        for source_item in package.sources:
            source_item.fetch_into(source_cache)

        # Do the build
        builder.ensure_present(package.build_spec)
    
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
            make install
        ''') % locals()
        
        return script

