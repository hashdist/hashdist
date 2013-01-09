
class WrongHostTypeError(Exception):
    pass

class HostPackages(object):
    def check_package_key(self, pkgname, key):
        if not is_package_installed(pkgname):
            return False
        else:
            return self.get_package_key(pkgname) == key

    def get_all_dependencies(self, pkgnames):
        packages = set()
        
        def dfs(current):
            if current not in packages:
                packages.add(current)
                for dep in self.get_immediate_dependencies(current):
                    dfs(dep)

        if isinstance(pkgnames, str):
            pkgnames = [pkgnames]
        for pkg in pkgnames:
            dfs(pkg)
        
        return packages

    def check_package(self, pkgname, key):
        if not self.is_package_installed(pkgname):
            return False
        else:
            return self.get_package_key(pkgname) == key

    def get_system_description(self):
        raise NotImplementedError()
