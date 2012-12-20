from textwrap import dedent

from .recipes import Recipe, find_dependency_in_spec, FetchSourceCode

class CCache(Recipe):

    version = '3.1.8'
    url = 'http://samba.org/ftp/ccache/ccache-3.1.8.tar.bz2'
    key = 'tar.bz2:tGtdS0-QwOTi6d8GnUHe0HG3MFNTX-EV5VJZ4-yt8-0'

    def __init__(self, gcc, unix):
        Recipe.__init__(self, 'ccache', CCache.version,
                        [FetchSourceCode(CCache.url, CCache.key, strip=1)],
                        before=[gcc],
                        gcc=gcc, unix=unix)

    def get_files(self):
        files = []
        for progname in ['gcc', 'g++', 'cc']:
            files.append({
                'target': '$ARTIFACT/bin/%s' % progname,
                'executable': True,
                'expandvars': True,
                'text':
                    dedent("""\
                    #!/bin/bash

                    function getpath() {
                      local source="$${BASH_SOURCE[0]}"
                      local dir="$$( dirname "$$source" )"
                      while [ -h "$$source" ]; do
                        source="$$(readlink "$$source")"
                        [[ $$source != /* ]] && source="$$dir/$$source"
                        dir="$$( cd -P "$$( dirname "$$source"  )" && pwd )"
                      done
                      echo "$$( cd -P "$$( dirname "$$source" )" && pwd )"
                    }

                    p="$$(getpath)"
                    exec "$$p/ccache" "$$p/../../../../$gcc_id/bin/%s" $$*
                    """ % progname).splitlines()
                })
        return files

    def get_commands(self):
        script = [
            ['./configure', '--prefix=${ARTIFACT}'],
            ['make'],
            ['make', 'install'],
            ]
        return script

        
