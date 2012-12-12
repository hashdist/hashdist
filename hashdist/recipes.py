from textwrap import dedent

from .package import Package, DownloadSourceCode, PutScript

def configure_make_install_package(name, version, source_url, source_key, configure_flags=(), **kw):
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

    # Make build script
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


    return Package(name, version,
                   sources=[DownloadSourceCode(source_url, source_key),
                            PutScript('build.sh', script)],
                   command=['/bin/bash', 'build.sh'],
                   dependencies=dependencies,
                   env=env)
