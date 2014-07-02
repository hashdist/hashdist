"""
Add a "hit shell" subcommand to open an IPython shell
"""

from .frontend_cli import ProfileFrontendBase, add_profile_args

try:
    import IPython
    from .main import register_subcommand
except ImportError:
    # "hit shell" is only available if we have IPython
    register_subcommand = lambda x:None



@register_subcommand
class IPythonShell(ProfileFrontendBase):
    """
    Open an IPython shell with hashdist set up
    """
    command = 'shell'

    @staticmethod
    def setup(ap):
        add_profile_args(ap)

    def profile_builder_action(self):
        self.ipython_start()

    def global_namespace(self):
        return dict(
            cli=self,
            builder=self.builder,
            profile=self.profile,
        )

    def ipython_start(self):
        from IPython.frontend.terminal.ipapp import TerminalIPythonApp
        ip = TerminalIPythonApp.instance()
        ip.initialize(argv=[])
        for key, value in self.global_namespace().items():
            ip.shell.user_global_ns[key] = value
        ip.start()


