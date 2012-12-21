import hashdist as hd
from hashdist.core import BuildStore, InifileConfiguration, SourceCache
import hashdist.recipes as hr

unix = hr.NonhashedUnix()
gcc = hr.NonhashedGCCStack()

ccache = hr.CCache(gcc=gcc, unix=unix)

zlib = hr.ConfigureMakeInstall('zlib', '1.2.7',
                               'http://downloads.sourceforge.net/project/libpng/zlib/1.2.7/zlib-1.2.7.tar.gz',
                               'tar.gz:+pychjjvuMuO9eTdVFPkVXUeHFMLFZXu1Gbhvpt+JsU',
                               unix=unix, gcc=gcc)

szip = hr.ConfigureMakeInstall('szip', '2.1',
                               'git://github.com/erdc-cm/szip.git',
                               'git:87863577a4656d5414b0d598c91fed1dd227f74a',
                               configure_flags=['--with-pic'],
                               unix=unix, gcc=gcc)

hdf5 = hr.ConfigureMakeInstall('hdf5', '1.8.10',
                               'http://www.hdfgroup.org/ftp/HDF5/current/src/hdf5-1.8.10.tar.bz2',
                               'tar.bz2:+m5rN7eXbtrIYHMrh8UDcOO+ujrnhNBfFvKYwDOkWkQ',
                               configure_flags=['--with-szlib', '--with-pic'],
                               zlib=zlib, szip=szip, unix=unix, gcc=gcc)

profile = hr.Profile([hdf5, szip, zlib])

hr.cli.stack_script_cli(profile)


