from . import recipes

class NonhashedHostPrograms(recipes.Recipe):
    def __init__(self, name, programs_and_prefixes=None):
        recipes.Recipe.__init__(self, name, "host",
                                hdist=recipes.hdist_tool,
                                is_virtual=True)
        self.programs_and_prefixes = programs_and_prefixes

    def get_parameters(self):
        rules = []
        for program, prefix in sorted(self.programs_and_prefixes):
            rules.append({"action": "symlink",
                          "select": program,
                          "prefix": prefix,
                          "target": "$ARTIFACT"})
        return {"links": rules}

    def get_commands(self):
        return [["hdist", "create-links", "build.json"]]

unix_programs_bin = (
    "cat cp chmod chown cpio date dd df echo egrep false"
    " fgrep grep hostname ln ls mkdir mv open"
    " ps  pwd readlink rm rmdir sed sleep sync tar touch true uname which"
    ).split()

# list mainly taken from Ubuntu coreutils; could probably be filtered a bit more
unix_programs_usr_bin = (
    # coreutils
    "expr printf csplit who stdbuf"
    " timeout comm [ head sha224sum tr sha256sum pathchk nice"
    " fmt chcon hostid base64 paste sort tee uniq sum stat fold arch install"
    " logname nproc wc sha1sum users sha384sum join pr printenv unexpand"
    " split tsort cut link cksum whoami env yes mkfifo id factor"
    " expand basename nl tty shuf groups tac ptx truncate tail test"
    " unlink sha512sum du dirname od md5sum seq"
    # additions
    " awk gawk pgawk igawk"
    ).split()

class NonhashedUnix(NonhashedHostPrograms):
    def __init__(self):
        links = []
        for prog in unix_programs_bin:
            links.append(('/bin/%s' % prog, '/'))
        for prog in unix_programs_usr_bin:
            links.append(('/usr/bin/%s' % prog, '/usr'))
        NonhashedHostPrograms.__init__(self, "unix", links)

class NonhashedMake(NonhashedHostPrograms):
    def __init__(self):
        NonhashedHostPrograms.__init__(self, "make", [("/usr/bin/make", "/usr")])


gcc_stack_programs = (
    "addr2line ar strings readelf size gprof objcopy ld.gold c++filt ld.bfd as objdump"
    "nm elfedit strip ranlib ld gold gcc g++"
    ).split()

class NonhashedGCCStack(NonhashedHostPrograms):
    def __init__(self):
        links = []
        for prog in gcc_stack_programs:
            links.append(('/usr/bin/%s' % prog, '/usr'))
        NonhashedHostPrograms.__init__(self, "gcc-stack", links)

