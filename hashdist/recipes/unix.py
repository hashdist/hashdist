from .recipes import Recipe, hdist_tool

class NonhashedHostPrograms(Recipe):
    def __init__(self, name, programs_and_prefixes=None):
        Recipe.__init__(self, name, "host",
                        hdist=hdist_tool,
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
        return [["hdist", "create-links", "--key=parameters/links", "build.json"]]

unix_programs_bin = (
    "cat cp chmod chown cpio date dd df echo egrep false"
    " fgrep grep hostname ln ls mkdir mv open"
    " ps  pwd readlink rm rmdir sed sleep sync tar touch true uname which"
    # ...and with some doubt:
    " bash"
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
    # awk
    " awk gawk pgawk igawk"
    # findutils
    " find xargs"
    # diffutils
    " sdiff cmp diff3 diff"
    # make
    " make"
    ).split()

class NonhashedUnix(NonhashedHostPrograms):
    def __init__(self):
        links = []
        for prog in unix_programs_bin:
            links.append(('/bin/%s' % prog, '/'))
        for prog in unix_programs_usr_bin:
            links.append(('/usr/bin/%s' % prog, '/usr'))
        NonhashedHostPrograms.__init__(self, "unix", links)

gcc_stack_programs = (
    "addr2line ar strings readelf size gprof objcopy ld.gold c++filt ld.bfd as objdump"
    "nm elfedit strip ranlib ld gold gcc g++ cc"
    ).split()

class NonhashedGCCStack(NonhashedHostPrograms):
    def __init__(self):
        links = []
        for prog in gcc_stack_programs:
            links.append(('/usr/bin/%s' % prog, '/usr'))
        NonhashedHostPrograms.__init__(self, "gcc-stack", links)

