from .package import PackageSpec

class IllegalProfileError(Exception):
    pass


class ProfileBuildState(object):
    """
    What can be known of a profile when all referenced package specs are loaded.
    Used to maintain state during the building process.
    """
    def __init__(self, profile):
        self.profile = profile
        self.built_packages = set()

        self._load_packages()

    def _load_packages(self):
        package_includes = self.profile.get_packages()
        self.package_specs = {}
        for pkgname, settings in package_includes.iteritems():
            filename = self.profile.find_package_file(pkgname)
            if filename is None:
                raise IllegalProfileError('no spec found for package %s' % pkgname)
            self.package_specs[pkgname] = PackageSpec.load_from_file(filename)

    def get_ready_list(self):
        ready = []
        for name, pkg in self.package_specs.iteritems():
            if name in self.built_packages:
                continue
            if all(dep_name in self.built_packages for dep_name in pkg.build_deps):
                ready.append(name)
        return ready

