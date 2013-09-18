import os
import re
from ..deps import sh

from ..core import cached_method

from .host import WrongHostTypeError, HostPackages

_DEPENDS = re.compile(r'\s*Depends: ([^<>]+)')
_SHA1 = re.compile(r'SHA1: (.*)$')

_CACHE_DOMAIN = 'hashdist.host.debian'
cached = cached_method(_CACHE_DOMAIN)

class DebianHostPackages(HostPackages):
    def __init__(self, logger, cache):
        self.cache = cache
        self.logger = logger

        try:
            # Invalidate cache if host system package state has changed
            mtime = os.stat('/var/lib/dpkg/status').st_mtime
        except OSError, e:
            raise WrongHostTypeError('Not a Debian-based system')
        if cache.get(_CACHE_DOMAIN, 'mtime', None) != mtime:
            logger.debug('Debian package state changed, invalidating cache')
            cache.invalidate(_CACHE_DOMAIN)
            cache.put(_CACHE_DOMAIN, 'mtime', mtime)
        
    @staticmethod
    def is_supported(cache):
        result = cache.get(_CACHE_DOMAIN, 'is_debian_system', None)
        if result is None:
            # Check that all commands are available
            try:
                sh.dpkg_query('-h')
                sh.apt_cache('-h')
            except sh.CommandNotFound, e:
                raise WrongHostTypeError('Not a Debian-based system')
                result = False
            else:
                result = True
            cache.put(DebianHostPackages, ('is_debian_system',), result)
        return result

    @cached
    def is_package_installed(self, pkgname):
        try:
            out = sh.dpkg_query('-W', '-f', '${Status}', pkgname)
            installed  = (str(out) == 'install ok installed')
        except sh.ErrorReturnCode, e:
            installed = False
        return installed

    @cached
    def get_immediate_dependencies(self, pkgname):
        self.logger.debug('Getting dependencies of Debian package "%s"' % pkgname)
        if pkgname == 'libc6':
            # for now, break dependency cycle here; TODO: proper treatment of
            # cyclic dependencies
            return ()
            
        deps = set()
        for line in sh.apt_cache('depends', '--installed', pkgname):
            m = _DEPENDS.match(line.strip())
            if m:
                deps.add(m.group(1))
        return deps

    @cached
    def get_files_of(self, pkgname):
        """Returns the names of the files installed by the given package
        """
        self.logger.debug('Getting installed files for Debian package "%s"' % pkgname)
        result = []
        for line in sh.dpkg_query('--listfiles', pkgname):
            line = line.strip()
            result.append(line)
        return result

    @cached
    def get_package_key(self, pkgname):
        try:
            for line in sh.apt_cache('show', pkgname):
                m = _SHA1.match(line.strip())
                if m:
                    return 'deb:' + m.group(1)
        except sh.ErrorReturnCode, e:
            raise UnknownPackageError(pkgname)

    def get_system_description(self):
        return 'Debian'
