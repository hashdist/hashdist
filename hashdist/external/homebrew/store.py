import os
import subprocess

from .package import HomebrewPackage

pjoin = os.path.join

class HomebrewStore():
    """Group together methods for interacting with the Homebrew Store"""

    def __init__(self, store_path, logger):
        self.store_path = store_path
        self.logger = logger
        self._search_cache = None

    @staticmethod
    def create_from_config(config, logger):
        """Creates a HomebrewStore from the settings in the configuration
        """

        return HomebrewStore(config['homebrew'],
                             logger)

    def brew(self, *args):
        # Inherit stdin/stdout in order to interact with user about any passwords
        # required to connect to any servers and so on
        path_to_brew = pjoin(self.store_path, 'bin', 'brew')
        p = subprocess.Popen([path_to_brew] + list(args),
                             stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()
        return p.returncode, out, err

    def checked_brew(self, *args):
        retcode, out, err = self.brew(*args)
        # Just fetch the output
        if retcode != 0:
            msg = 'brew call %r failed with code %d' % (args, retcode)
            self.logger.error(msg)
            raise RuntimeError(msg)
        return out

    def has(self, pkgname):
        return pkgname in self.get_search_cache()

    def get_package_spec(self, profile, pkgname):
        if not self.has(pkgname):
            raise RuntimeError('Could not compute spec for package: %s' % pkgname)
        path_to_brew = pjoin(self.store_path, 'bin', 'brew')
        doc = {
            'profile_links': [],
            'sources': [],
            'build_stages': [{'handler': 'bash',
                              'bash': '%s unlink %s' % (path_to_brew, pkgname),
                              'bash': '%s install %s' % (path_to_brew, pkgname)}],
            'dependencies': {'run': [], 'build': []}}
        return HomebrewPackage(pkgname, doc, self.store_path)

    def get_search_cache(self):
        if not self._search_cache:
            out_raw = self.checked_brew('search')
            self._search_cache = out_raw.split()
        return self._search_cache

    def install_package():
        pass

    def link_package():
        pass
