import hashdist as hd
from hashdist.core import BuildStore, InifileConfiguration, SourceCache
import hashdist.recipes as hr

unix = hr.UnhashedUnix()
make = hr.UnhashedMake()
gcc = hr.UnhashedGCCStack()

zlib = hr.ConfigureMakeInstall('zlib', '1.2.7',
                               'http://zlib.net/zlib-1.2.7.tar.gz',
                               'tar.gz:+pychjjvuMuO9eTdVFPkVXUeHFMLFZXu1Gbhvpt+JsU',
                               unix=unix, make=make, gcc=gcc)

python = hr.ConfigureMakeInstall('python', '2.7.3',
                                 'http://python.org/ftp/python/2.7.3/Python-2.7.3.tar.bz2',
                                 'tar.bz2:cmRX4RyxU63D9Ciq8ZAfxWGjdMMOXn2mdCwHQqM4Zjw',
                                 unix=unix, make=make, gcc=gcc, zlib=zlib)


import logging
logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

build_store = BuildStore.create_from_config(InifileConfiguration.create(), logger)
source_cache = SourceCache.create_from_config(InifileConfiguration.create(), logger)


#print zlib.format_tree(build_store)

hr.cli.stack_script_cli(zlib)

