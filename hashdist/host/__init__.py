import subprocess
import errno

from .host import WrongHostTypeError
from ..core import null_cache
from ..hdist_logging import null_logger

_host_packages_class = None

def get_host_packages(logger=null_logger, cache=null_cache):
    """Returns a HostPackages object corresponding to the current host
    """
    global _host_packages_class
    if _host_packages_class is None:
        result = None

        from .debian import DebianHostPackages
        if DebianHostPackages.is_supported(cache):
            _host_packages_class = DebianHostPackages
        else:
            raise NotImplementedError('No HostPackages support for this system')
    return _host_packages_class(logger, cache)
    
