import sys
import os
import shutil
from os.path import join as pjoin, exists as pexists
from textwrap import dedent

from ..formats.config import (
    DEFAULT_STORE_DIR,
    DEFAULT_CONFIG_DIRS,
    DEFAULT_CONFIG_FILENAME_REPR,
    DEFAULT_CONFIG_FILENAME,
    get_config_example_filename
)
from .main import register_subcommand

@register_subcommand
class InitHome(object):
    __doc__ = """
    Initialize the current user's home directory for HashDist.

    Create the ~/.hashdist directory. Further configuration can
    then by done by modifying %s.
    """ % DEFAULT_CONFIG_FILENAME_REPR
    command = 'init-home'

    @staticmethod
    def setup(ap):
        pass

    @staticmethod
    def run(ctx, args):
        for path in [DEFAULT_STORE_DIR, DEFAULT_CONFIG_FILENAME]:
            if pexists(path):
                ctx.logger.error('%s already exists, aborting\n' % path)
                return 2

        for path in DEFAULT_CONFIG_DIRS:
            os.makedirs(pjoin(DEFAULT_STORE_DIR, path))
            sys.stdout.write('Directory %s created.\n' % path)
        shutil.copyfile(get_config_example_filename(), DEFAULT_CONFIG_FILENAME)
        sys.stdout.write('Default configuration file %s written.\n' % DEFAULT_CONFIG_FILENAME)

@register_subcommand
class SelfCheck(object):
    """
    Verifies the consistency of a HashDist configuration file.
    """
    command = 'self-check'

    @staticmethod
    def setup(ap):
        pass

    @staticmethod
    def run(ctx, args):
        # This is done implicitly when the context is loaded.
        ctx.get_config()
        ctx.logger.info('The configuration now appears to be consistent.')


@register_subcommand
class ClearSources(object):
    """
    Empties the source cache. Must be used with the --force argument.

    Example::

        $ hit clearsource --force

    """

    @staticmethod
    def setup(ap):
        ap.add_argument('--force', action='store_true', help='Yes, actually do this')

    @staticmethod
    def run(ctx, args):
        from ..core import SourceCache
        source_cache = SourceCache.create_from_config(ctx.get_config(), ctx.logger)
        source_cache.delete_all()

@register_subcommand
class Purge(object):
    """
    Removes a build artifact from the build store. The specific artifact ID must be
    given, e.g.::

        $ hit purge python/2qbgsltd4mwz

    Alternatively, to wipe the entire build store::

        $ hit purge --force '*'

    Remember to quote in your shell.
    """

    @staticmethod
    def setup(ap):
        ap.add_argument('artifact_id')
        ap.add_argument('--force', action='store_true', help='Needed to delete more than 1 artifact')

    @staticmethod
    def run(ctx, args):
        from ..core import BuildStore
        store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
        if args.artifact_id == '*':
            if not args.force:
                ctx.logger.error('Did not use --force flag')
                return 1
            store.delete_all()
        else:
            path = store.delete(args.artifact_id)
            if path is None:
                sys.stderr.write('Artifact %s not found\n' % args.artifact_id)
            else:
                sys.stderr.write('Removed directory: %s\n' % path)

@register_subcommand
class RemoteStore(object):
    """
    Work with remote build store

    Example::

        $ hit remote-store --add --pcs="dropbox" --appName="hashdist_test"

    """
    command = 'remote-store'

    @staticmethod
    def setup(ap):
        ap.add_argument('--add', action='store_true', help='Add a remote build store')
        ap.add_argument('--pcs', default="dropbox",help='Personal cloud service to use for the remote build store')
        ap.add_argument('--appName', default="hashdist_test",help='Name of up you set up via web interface')
        ap.add_argument('--appId', help='ID assigned to app by pcs')
        ap.add_argument('--appSecret',help='secret assigned to app by pcs')

    @staticmethod
    def run(ctx, args):
        from pcs_api.credentials.app_info_file_repo import AppInfoFileRepository
        from pcs_api.credentials.user_creds_file_repo import UserCredentialsFileRepository
        from pcs_api.credentials.user_credentials import UserCredentials
        from pcs_api.oauth.oauth2_bootstrap import OAuth2BootStrapper
        from pcs_api.storage import StorageFacade
        # Required for registering providers :
        from pcs_api.providers import *
        if args.add:
            remote_path = pjoin(DEFAULT_STORE_DIR,"remote")
            try:
                os.makedirs(remote_path)
            except:
                #todo properly just ensure this dir exists
                pass
            app_info_data = """{pcs}.{appName} = {{ "appId": "{appId}", "appSecret": "{appSecret}", "scope": ["sandbox"] }}""".format(**args.__dict__)
            app_info_path=pjoin(remote_path,"app_info_data.txt")
            user_credentials_path=pjoin(remote_path,"user_credentials_data.txt")
            f = open(app_info_path,"w")
            f.write(app_info_data)
            f.close()
            apps_repo = AppInfoFileRepository(app_info_path)
            user_credentials_repo = UserCredentialsFileRepository(user_credentials_path)
            storage = StorageFacade.for_provider(args.pcs) \
                .app_info_repository(apps_repo, args.appName) \
                .user_credentials_repository(user_credentials_repo) \
                .for_bootstrap() \
                .build()
            bootstrapper = OAuth2BootStrapper(storage)
            bootstrapper.do_code_workflow()
        else:
            f = open(pjoin(DEFAULT_STORE_DIR,"remote","app_info_data.txt"),"r")
            print f.readlines()
            f.close()
            f = open(pjoin(DEFAULT_STORE_DIR,"remote","user_credentials_data.txt"),"r")
            print f.readlines()
            f.close()

@register_subcommand
class Push(object):
    """
    Push artifacts to remote build store

    Example::

        $ hit push

    """
    command = 'push'

    @staticmethod
    def setup(ap):
        ap.add_argument('--dryrun', action='store_true', help='Show what would happen')
    
    @staticmethod
    def run(ctx, args):
        # Required for providers registration :
        from pcs_api.providers import *
        #
        from pcs_api.credentials.app_info_file_repo import AppInfoFileRepository
        from pcs_api.credentials.user_creds_file_repo import UserCredentialsFileRepository
        from pcs_api.credentials.user_credentials import UserCredentials
        from pcs_api.storage import StorageFacade
        from pcs_api.bytes_io import (MemoryByteSource, MemoryByteSink,
                                      FileByteSource, FileByteSink,
                                      StdoutProgressListener)
        from pcs_api.models import CPath, CFolder, CBlob, CUploadRequest, CDownloadRequest
        if args.dryrun:
            from ..core import BuildStore
            store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
            os.chdir(store.artifact_root)
            for package in os.listdir(store.artifact_root):
                for artifact in os.listdir(pjoin(store.artifact_root,package)):
                    print "tar czvf {package}/{artifact}.tar.gz {package}/{artifact}".format(package=package,artifact=artifact)
            import pdb
            pdb.set_trace()
            os.system('cd %s; tar xzvf %s; rm -f %s' % (self.artifact_root,temp_path,temp_path))
        else:
            import pdb
            pdb.set_trace()
            remote_path = pjoin(DEFAULT_STORE_DIR,"remote")
            app_info_path=pjoin(remote_path,"app_info_data.txt")
            user_credentials_path=pjoin(remote_path,"user_credentials_data.txt")
            if not os.path.exists(app_info_path):
                print('Not found any application information repository file: ', app_info_path)
                print('Refer to documentation and class AppInfoFileRepository to setup pcs_api for a quick test')
                exit(1)
            apps_repo = AppInfoFileRepository(app_info_path)
            if not os.path.exists(user_credentials_path):
                print('Not found any users credentials repository file: ', user_credentials_path)
                print('Refer to documentation and class UserCredentialsFileRepository to setup pcs_api for a quick test')
                exit(1)
            user_credentials_repo = UserCredentialsFileRepository(user_credentials_path)
            provider_name = apps_repo._app_info.keys()[0].split(".")[0]
            app_info = apps_repo.get(provider_name)
            user_info = user_credentials_repo.get(app_info)
            storage = StorageFacade.for_provider(provider_name) \
                       .app_info_repository(apps_repo,app_info.app_name) \
                       .user_credentials_repository(user_credentials_repo,user_info.user_id) \
                       .build()
            print("user_id = ", storage.get_user_id())
            print("quota = ", storage.get_quota())
            from ..core import BuildStore
            store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
            os.chdir(store.artifact_root)
            for package in os.listdir(store.artifact_root):
                for artifact in os.listdir(pjoin(store.artifact_root,package)):
                    os.system("tar czvf {package}/{artifact}.tar.gz {package}/{artifact}".format(package=package,artifact=artifact))
                    fpath = CPath('/'+package)
                    storage.create_folder(fpath)
                    bpath=fpath.add(artifact+".tar.gz")
                    storage.upload(CUploadRequest(bpath,FileByteSource(pjoin(package,artifact+".tar.gz"))))
