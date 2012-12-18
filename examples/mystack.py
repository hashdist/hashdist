import hashdist as hd
from hashdist.core import BuildStore, InifileConfiguration, SourceCache
import hashdist.recipes as hr

unix = hr.NonhashedUnix()
make = hr.NonhashedMake()
gcc = hr.NonhashedGCCStack()

zlib = hr.ConfigureMakeInstall('zlib', '1.2.7',
                               'git://github.com/erdc-cm/zlib.git',
                               'git:f7d921d70f092380e224502bf92e256936ddce8a',
                               unix=unix, make=make, gcc=gcc)

szip = hr.ConfigureMakeInstall('szip', '2.1',
                               'http://www.hdfgroup.org/ftp/lib-external/szip/2.1/src/szip-2.1.tar.gz',
                               'tar.gz:qBbZXVZi6CeWJavb6n0OYhV9fR8CgCCxB1UAv0g+1e8',
                               configure_flags=['--with-pic'],
                               unix=unix, make=make, gcc=gcc)



hdf5 = hr.ConfigureMakeInstall('hdf5', '1.8.7',
                               'git://github.com/erdc-cm/hdf5.git',
                               'git:802ff8c4ccd931b104a95c3f30ff385008d95f31',
                               configure_flags=['--with-szlib=$szip', '--with-zlib=$zlib',
                                                '--with-pic'],
                               zlib=zlib, szip=szip, unix=unix, make=make, gcc=gcc)

hr.cli.stack_script_cli(hdf5)



#python = hr.ConfigureMakeInstall('python', '2.7.3',
#                                 'http://python.org/ftp/python/2.7.3/Python-2.7.3.tar.bz2',
#                                 'tar.bz2:cmRX4RyxU63D9Ciq8ZAfxWGjdMMOXn2mdCwHQqM4Zjw',
#                                 unix=unix, make=make, gcc=gcc, zlib=zlib)
