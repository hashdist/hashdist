"""
Interface to remote storage
"""
from os.path import join as pjoin, exists as pexists
import subprocess

class RemotePCSError(Exception):
    pass

class HandlerBase(object):
    def put_bytes(self, bytes, remote_path):
        raise NotImplementedError
    def mkdir(self, remote_path):
        raise NotImplementedError
    def get_bytes(self, remote_path):
        raise NotImplementedError
    def put_file(self, local_path, remote_path):
        raise NotImplementedError
    def get_file(self, local_path, remote_path):
        raise NotImplementedError
    def check(self):
        raise NotImplementedError


class RemoteHandlerSSH(HandlerBase):
    """
    Handle remote using passwordless ssh
    """
    def __init__(self, remote_config_path, ctx):
        sshserver_path = pjoin(remote_config_path, "sshserver")
        with open(sshserver_path, 'r') as f:
            serverinfo = f.readlines()[0]
        self.sshserver, self.remote_root = serverinfo.split(":")
        if self.remote_root[-1] is  '/':
            self.remote_root = self.remote_root[:-1]
        self.ctx = ctx
    def mkdir(self, remote_path):

        subprocess.check_call(["ssh",
                               self.sshserver,
                               'mkdir -p ' + self.remote_root + remote_path])
    def put_bytes(self, bytes, remote_path):
        sshpipe = subprocess.Popen(['ssh',
                                    self.sshserver,
                                    'cat - > ' +
                                    self.remote_root +
                                    remote_path],
                                   stdin = subprocess.PIPE)
        sshpipe.stdin.write(str(bytes))
        sshpipe.stdin.flush()
        sshpipe.terminate()
    def get_bytes(self, remote_path):
        sshpipe = subprocess.Popen(['ssh',
                                    self.sshserver,
                                    'cat ' +
                                    self.remote_root +
                                    remote_path],
                                   stdout = subprocess.PIPE)
        remote_path_string = sshpipe.stdout.read()
        sshpipe.terminate()
        return bytes(remote_path_string)
    def put_file(self, local_path, remote_path):
        subprocess.check_call(["scp",
                               local_path,
                               self.sshserver + ":" +
                               self.remote_root +
                               remote_path])
    def get_file(self, local_path, remote_path):
        subprocess.check_call(["scp",
                               self.sshserver + ":" +
                               self.remote_root +
                               remote_path,
                               local_path])
    def check(self):
        with open("test.txt", "w") as f:
            f.write("Test file\n")
        self.mkdir('/test_dir')
        self.put_file("test.txt",
                      "/test_dir/test.txt")
        self.get_file("test_remote.txt",
                      "/test_dir/test.txt")
        with open("test_remote.txt", "r") as f:
            assert "Test file\n" == f.read()
        os.remove("test.txt")
        os.remove("test_remote.txt")
        file_contents_uploaded = b"Test file contents"
        self.put_bytes(file_contents_uploaded, "/test_dir/test.txt")
        file_contends_downloaded = self.get_bytes("/test_dir/test.txt")
        subprocess.check_call(['ssh',
                               self.sshserver,
                               'rm',
                               self.remote_root + '/test_dir/test.txt'])
        subprocess.check_call(['ssh',
                               self.sshserver,
                               'rmdir',
                               self.remote_root + '/test_dir'])


class RemoteHandlerPCS(HandlerBase):
    """
    Handle remote with Personal Cloud Storage API
    """
    def __init__(self, remote_config_path, ctx):
        # Required for providers registration :
        from pcs_api.providers import (dropbox,
                                       googledrive)
        #
        from pcs_api.credentials.app_info_file_repo \
            import AppInfoFileRepository
        from pcs_api.credentials.user_creds_file_repo \
            import UserCredentialsFileRepository
        from pcs_api.credentials.user_credentials import UserCredentials
        from pcs_api.storage import StorageFacade
        ctx.logger.info("Setting up cloud storage app")
        app_info_path = pjoin(remote_config_path, "app_info_data.txt")
        user_credentials_path = pjoin(remote_config_path,
                                      "user_credentials_data.txt")
        if not pexists(app_info_path):
            msg = 'No remote application information: ' \
                  + repr(app_info_path)
            ctx.logger.critical(msg)
            msg = "Run 'hit remote add ...'"
            ctx.logger.critical(msg)
            exit(1)
        apps_repo = AppInfoFileRepository(app_info_path)
        if not pexists(user_credentials_path):
            msg = 'No user credentials found: ' \
                + repr(user_credentials_path)
            ctx.logger.critical(msg)
            msg = "Run 'hit remote add ...'"
            ctx.logger.critical(msg)
            exit(1)
        user_credentials_repo = UserCredentialsFileRepository(
            user_credentials_path)
        provider_name = apps_repo._app_info.keys()[0].split(".")[0]
        app_info = apps_repo.get(provider_name)
        user_info = user_credentials_repo.get(app_info)
        self.storage = StorageFacade \
            .for_provider(provider_name) \
            .app_info_repository(apps_repo, app_info.app_name) \
            .user_credentials_repository(user_credentials_repo,
                                         user_info.user_id) \
            .build()
        msg = "Cloud storage user_id = " + repr(self.storage.get_user_id())
        ctx.logger.info(msg)
        msg = "Cloud storage quota = " + repr(self.storage.get_quota())
        ctx.logger.info(msg)
        ctx.logger.info("Cloud storage is  ready")
        self.ctx = ctx

    def put_bytes(self, local_bytes, remote_path):
        from pcs_api.bytes_io import (MemoryByteSource,
                                      StdoutProgressListener)
        from pcs_api.models import (CPath,
                                    CUploadRequest)
        byte_source = MemoryByteSource(local_bytes)
        bpath = CPath(remote_path)
        upload_request = CUploadRequest(bpath,
                                        byte_source).content_type('text/plain')
        upload_request.progress_listener(StdoutProgressListener())
        self.storage.upload(upload_request)
    def get_bytes(self, remote_path):
        from pcs_api.bytes_io import (MemoryByteSink,
                                      StdoutProgressListener)
        from pcs_api.models import (CPath,
                                    CDownloadRequest)
        remote_bytes = MemoryByteSink()
        bpath = CPath(remote_path)
        download_request = CDownloadRequest(bpath,
                                            remote_bytes)
        download_request.progress_listener(StdoutProgressListener())
        self.storage.download(download_request)
        return remote_bytes.get_bytes()
    def mkdir(self, remote_path):
        from pcs_api.models import CPath
        fpath = CPath(remote_path)
        self.storage.create_folder(fpath)
    def put_file(self, local_path, remote_path):
        from pcs_api.bytes_io import (FileByteSource,
                                      StdoutProgressListener)
        from pcs_api.models import (CPath,
                                    CUploadRequest)
        bpath = CPath(remote_path)
        upload_request = CUploadRequest(
            bpath, FileByteSource(local_path))
        upload_request.progress_listener(
            StdoutProgressListener())
        self.storage.upload(upload_request)
    def get_file(self, local_path, remote_path):
        from pcs_api.bytes_io import (FileByteSink,
                                      StdoutProgressListener)
        from pcs_api.models import (CPath,
                                    CDownloadRequest)
        bpath = CPath(remote_path)
        download_request = CDownloadRequest(
            bpath, FileByteSink(local_path))
        download_request.progress_listener(
            StdoutProgressListener())
        self.storage.download(download_request)
    def check(self):
        from pcs_api.bytes_io import (MemoryByteSource,
                                      MemoryByteSink,
                                      StdoutProgressListener)
        from pcs_api.models import (CPath,
                                    CUploadRequest,
                                    CDownloadRequest)
        msg = "Cloud storage user_id = " + repr(self.storage.get_user_id())
        self.ctx.logger.info(msg)
        msg = "Cloud storage quota = " + repr(self.storage.get_quota())
        self.ctx.logger.info(msg)
        self.ctx.logger.info("Cloud storage is  ready")
        fpath = CPath('/test_dir')
        self.storage.create_folder(fpath)
        bpath = fpath.add("test.txt")
        file_contents_uploaded = b"Test file contents"
        upload_request = CUploadRequest(
            bpath,
            MemoryByteSource(file_contents_uploaded)).content_type('text/plain')
        upload_request.progress_listener(StdoutProgressListener())
        self.storage.upload(upload_request)
        file_contents_downloaded = MemoryByteSink()
        download_request = CDownloadRequest(bpath,
                                            file_contents_downloaded)
        download_request.progress_listener(StdoutProgressListener())
        self.storage.download(download_request)
        self.storage.delete(fpath)
        if file_contents_uploaded != file_contents_downloaded.get_bytes():
            raise RemotePCSError

def bootstrap_PCS(args, app_info_path, user_credentials_path):
    from pcs_api.providers import (dropbox,
                                   googledrive)
    from pcs_api.credentials.app_info_file_repo \
        import AppInfoFileRepository
    from pcs_api.credentials.user_creds_file_repo \
        import UserCredentialsFileRepository
    from pcs_api.storage import StorageFacade
    from pcs_api.oauth.oauth2_bootstrap import OAuth2BootStrapper
    apps_repo = AppInfoFileRepository(app_info_path)
    user_credentials_repo = UserCredentialsFileRepository(
        user_credentials_path)
    storage = StorageFacade.for_provider(args.pcs) \
        .app_info_repository(apps_repo, args.app_name) \
        .user_credentials_repository(user_credentials_repo) \
        .for_bootstrap() \
        .build()
    bootstrapper = OAuth2BootStrapper(storage)
    bootstrapper.do_code_workflow()
