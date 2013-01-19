from .recipes import Recipe, hdist_tool
from unix import NonhashedHostPrograms
osx10_8_programs_bin = (
    "cat cp chmod date dd df echo"
    " hostname ln ls mkdir mv"
    " ps  pwd rm rmdir sleep sync"
    # ...and with some doubt:
    " bash"
    " expr link test unlink"
    ).split()

osx10_8_programs_usr_bin = (
    # coreutils
    " printf csplit who"
    " comm  head tr pathchk nice"
    " fmt base64 paste sort tee uniq sum stat fold arch install"
    " logname wc users join pr printenv unexpand"
    " split tsort cut cksum whoami env yes mkfifo id"
    " expand basename nl tty groups tail "
    " du dirname od seq"
    # awk
    " awk"
    #sed
    " sed"
    # findutils
    " find xargs"
    # diffutils
    " sdiff cmp diff3 diff"
    # make
    " make libtool"
    " cpio egrep false fgrep grep open readlink tar touch true uname which"
    ).split()

osx10_8_programs_usr_sbin = (
    " chown"
    ).split()

class NonhashedOSX10_8(NonhashedHostPrograms):
    def __init__(self):
        links = []
        for prog in osx10_8_programs_bin:
            links.append(('/bin/%s' % prog, '/'))
        for prog in osx10_8_programs_usr_bin:
            links.append(('/usr/bin/%s' % prog, '/usr'))
        for prog in osx10_8_programs_usr_sbin:
            links.append(('/sbin/%s' % prog, '/usr'))
        NonhashedHostPrograms.__init__(self, "unix", links)

clang_stack_programs = (
    "addr2line ar strings readelf size gprof objcopy ld.gold c++filt ld.bfd as objdump"
    "nm elfedit strip ranlib ld gold clang clang++ gcc g++ cc" 
    ).split()

class NonhashedClangStack(NonhashedHostPrograms):
    def __init__(self):
        links = []
        for prog in clang_stack_programs:
            links.append(('/usr/bin/%s' % prog, '/usr'))
        NonhashedHostPrograms.__init__(self, "clang-stack", links)

