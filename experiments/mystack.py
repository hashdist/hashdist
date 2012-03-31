

#from hashdist import pkgs
import hashdist as dist
import hashdist

class SPKGPackageSource:

    def get_package(self, package_name, **kw):


        return SPKGPackage(**kw)


system = hashdist.AlreadyInstalledOnSystemSource()
spkg = hashdist.SPKGPackageSource('/home/dagss/...')
pypi = hashdist.PyPIPackageSource('http://sciencepypi')

#pkgs = hashdist.PackageFinder([system, spkg, pypi])



blas = spkg.reference_blas()

ATLAS = spkg.ATLAS()
ATLAS = system.ATLAS('/sysadmins/stupid/path/for/ATLAS')


petsc = pkgs.petsc(blas=ATLAS)
                   


numpy = pkgs.numpy(blas=ATLAS, CFLAGS='-O0')

profile = hashdist.profile([petsc, numpy])


hashdist.distribution_command_line(profile,
                                   distro_dir='/home/dagss/my_hashdist')


