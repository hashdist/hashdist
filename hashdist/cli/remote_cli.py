import sys
import os
import subprocess
import shutil
from os.path import join as pjoin, exists as pexists
from textwrap import dedent
import json
from ..core.fileutils import robust_rmtree
from ..formats.config import (
    DEFAULT_STORE_DIR,
    DEFAULT_CONFIG_DIRS,
    DEFAULT_CONFIG_FILENAME_REPR,
    DEFAULT_CONFIG_FILENAME,
    get_config_example_filename,
    load_config_file
)
from .main import register_subcommand


class RemoteAddError(Exception):
    pass

class RemoteRemoveError(Exception):
    pass

class RemotePCSError(Exception):
    pass

def remote_pcs_test(remote,logger):
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
    from pcs_api.bytes_io import (MemoryByteSource, MemoryByteSink,
                                  FileByteSource, FileByteSink,
                                  StdoutProgressListener)
    from pcs_api.models import (CPath,
                                CFolder,
                                CBlob,
                                CUploadRequest,
                                CDownloadRequest)
    logger.info("Setting up cloud storage app")
    remote_path = pjoin(DEFAULT_STORE_DIR, "remotes", remote)
    app_info_path = pjoin(remote_path, "app_info_data.txt")
    user_credentials_path = pjoin(remote_path, "user_credentials_data.txt")
    if not os.path.exists(app_info_path):
        msg = 'No remote application information: ' \
            + repr(app_info_path)
        logger.critical(msg)
        msg = "Run 'hit remote add ...'"
        logger.critical(msg)
        exit(1)
    apps_repo = AppInfoFileRepository(app_info_path)
    if not os.path.exists(user_credentials_path):
        msg = 'No user credentials found: ' + repr(user_credentials_path)
        logger.critical(msg)
        msg = "Run 'hit remote add ...'"
        logger.critical(msg)
        exit(1)
    user_credentials_repo = UserCredentialsFileRepository(
        user_credentials_path)
    provider_name = apps_repo._app_info.keys()[0].split(".")[0]
    app_info = apps_repo.get(provider_name)
    user_info = user_credentials_repo.get(app_info)
    storage = StorageFacade.for_provider(provider_name) \
        .app_info_repository(apps_repo, app_info.app_name) \
        .user_credentials_repository(user_credentials_repo,
                                     user_info.user_id) \
        .build()
    msg = "Cloud storage user_id = " + repr(storage.get_user_id())
    logger.info(msg)
    msg = "Cloud storage quota = " + repr(storage.get_quota())
    logger.info(msg)
    logger.info("Cloud storage is  ready")
    fpath = CPath('/test_dir')
    storage.create_folder(fpath)
    bpath = fpath.add("test.txt")
    file_contents_uploaded = b"Test file contents"
    upload_request = CUploadRequest(
        bpath, MemoryByteSource(file_contents_uploaded)).content_type('text/plain')
    upload_request.progress_listener(StdoutProgressListener())
    storage.upload(upload_request)
    file_contents_downloaded = MemoryByteSink()
    download_request = CDownloadRequest(bpath,
                                        file_contents_downloaded)
    download_request.progress_listener(StdoutProgressListener())
    storage.download(download_request)
    storage.delete(fpath)
    if file_contents_uploaded != file_contents_downloaded.get_bytes():
        raise RemotePCSError

@register_subcommand
class Remote(object):

    """
    Manage remote build store and source cache.

    Currently, only common cloud-based storage is supported
    (https://github.com/netheosgithub/pcs_api).


    Example:: **First**, create a dropbox app for your remote at
    https://www.dropbox.com/developers/apps. Next, add the remote:

        $ hit remote add --pcs="dropbox" --app-name="hd_osx" \\
          --app-id=x --app-secret=y

    """
    command = 'remote'

    @staticmethod
    def setup(ap):
        ap.add_argument('subcommand', choices=['add', 'remove', 'show'])
        ap.add_argument('name', default="primary", nargs="?",
                        help="Name of remote")
        ap.add_argument('--pcs', default="dropbox",
                        help='Use personal cloud service')
        ap.add_argument('--test-pcs', action="store_true",
                        help='Test personal cloud service')
        ap.add_argument('--app-name', default="hashdist_PLATFORM",
                        help='Name of the app on the cloud service')
        ap.add_argument('--app-id', default=None,
                        help='ID of the app on cloud service')
        ap.add_argument('--app-secret', default=None,
                        help='Secret for the app on cloud service')
        ap.add_argument('--objects', default="build_and_source",
                        help="Work on 'build','source', or 'build_and_source'")
    @staticmethod
    def run(ctx, args):
        from pcs_api.credentials.app_info_file_repo \
            import AppInfoFileRepository
        from pcs_api.credentials.user_creds_file_repo \
            import UserCredentialsFileRepository
        from pcs_api.credentials.user_credentials import UserCredentials
        from pcs_api.oauth.oauth2_bootstrap import OAuth2BootStrapper
        from pcs_api.storage import StorageFacade
        # Required for registering providers :
        from pcs_api.providers import (dropbox,
                                       googledrive)
        #
        if args.subcommand == 'add':
            ctx.logger.info("Attempting to add remote")
            remote_bld = None
            remote_src = None
            if (args.name.startswith('http://') or
                args.name.startswith('https://')):
                config = ctx.get_config()
                with open(ctx._config_filename,'r') as config_file:
                    config_lines = config_file.readlines()
                if args.objects in ['build', 'build_and_source']:
                    for bld_dict in config['build_stores']:
                        if bld_dict.values()[-1].startswith(args.name):
                            ctx.logger.warning("Already has" + repr(args.name))
                            break
                    else:
                        for line_no,line in enumerate(config_lines):
                            if line.strip().startswith("build_stores:"):
                                local_bld = config_lines[line_no+1].strip()
                                assert local_bld.startswith('- dir:')
                                remote_bld = ' - url: {0}/bld\n' \
                                    .format(args.name)
                                config_lines.insert(line_no+2, remote_bld)
                                break
                if args.objects in ['source', 'build_and_source']:
                    for src_dict in config['source_caches']:
                        if src_dict.values()[-1].startswith(args.name):
                            ctx.logger.warning("Already has" + repr(args.name))
                            break
                    else:
                        for line_no,line in enumerate(config_lines):
                            if line.strip().startswith("source_caches:"):
                                local_src = config_lines[line_no+1].strip()
                                assert local_src.startswith('- dir:')
                                remote_src = ' - url: {0}/src\n' \
                                    .format(args.name)
                                config_lines.insert(line_no+2, remote_src)
                #write temporary config file and check for correctness
                if remote_bld or remote_src:
                    tmp_config_path = pjoin(DEFAULT_STORE_DIR, 'config_tmp.yaml')
                    with open(tmp_config_path, 'w') as config_file:
                        config_file.writelines(config_lines)
                    new_config = load_config_file(tmp_config_path, ctx.logger)
                    if (remote_bld and
                        args.objects in ['build', 'build_and_source'] and
                        {'url':remote_bld.strip(' -url:').strip('\n')}
                        not in new_config['build_stores']):
                        raise RemoteAddError
                    if (remote_src and
                        args.objects in ['source', 'build_and_source'] and
                        {'url': remote_src.strip(' -url:').strip('\n')}
                        not in new_config['source_caches']):
                        raise RemoteAddError
                    try:
                        shutil.copy(tmp_config_path, ctx._config_filename)
                    except:
                        raise RemoteAddError
                    else:
                        ctx.logger.info("Wrote "+repr(ctx._config_filename))
            elif args.pcs:
                remote_path = pjoin(DEFAULT_STORE_DIR, "remotes", args.name)
                try:
                    if not os.path.exists(remote_path):
                        os.makedirs(remote_path)
                except:
                    msg = "Could not create:" + repr(remote_path)
                    ctx.logger.critical(msg)
                    exit(1)
                if None in [args.app_id, args.app_secret]:
                    msg = "Supply both --app-id and --app-secret"
                    ctx.logger.critical(msg)
                    exit(1)
                app_info_data = '{pcs}.{app_name} = {{ "appId": "{app_id}", \
                "appSecret": "{app_secret}", \
                "scope": ["sandbox"] }}'.format(**args.__dict__)
                app_info_path = pjoin(remote_path, "app_info_data.txt")
                user_credentials_path = pjoin(remote_path,
                                              "user_credentials_data.txt")
                f = open(app_info_path, "w")
                f.write(app_info_data)
                f.close()
                ctx.logger.info("Wrote "+repr(ctx._config_filename))
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
                if args.test_pcs:
                    remote_pcs_test(args.name,ctx.logger)
        elif args.subcommand == 'remove':
            ctx.logger.info("Attempting to remove remote")
            if (args.name.startswith('http://') or
                args.name.startswith('https://')):
                config = ctx.get_config()
                with open(ctx._config_filename,'r') as config_file:
                    config_lines = config_file.readlines()
                if args.objects in ['build', 'build_and_source']:
                    remote_bld = ' - url: {0}/bld\n'.format(args.name)
                    try:
                        config_lines.remove(remote_bld)
                    except ValueError:
                        ctx.logger.warning("Not found in config")
                if args.objects in ['source', 'build_and_source']:
                    remote_src = ' - url: {0}/src\n' \
                        .format(args.name)
                    try:
                        config_lines.remove(remote_src)
                    except ValueError:
                        ctx.logger.warning("Not found in config")
                #write temporary config file and check for correctness
                tmp_config_path = pjoin(DEFAULT_STORE_DIR, 'config_tmp.yaml')
                with open(tmp_config_path, 'w') as config_file:
                    config_file.writelines(config_lines)
                new_config = load_config_file(tmp_config_path, ctx.logger)
                if  args.name in config['build_stores']:
                    raise RemoteRemoveError
                if  args.name in config['source_caches']:
                    raise RemoteRemoveError
                try:
                   shutil.copy(tmp_config_path, ctx._config_filename)
                except:
                   raise RemoteRemoveError
                else:
                   ctx.logger.info("Wrote "+repr(ctx._config_filename))
            else:
                remote_path = pjoin(DEFAULT_STORE_DIR, "remotes", args.name)
                print remote_path
                try:
                    robust_rmtree(remote_path, ctx.logger)
                except:
                    raise RemoteRemoveError
                ctx.logger.info("Removed remote: "+repr(args.name))
        elif args.subcommand == 'show':
            config = ctx.get_config()
            for source_mirror in config['source_caches'][1:]:
                sys.stdout.write(source_mirror.values()[-1] + " (fetch:src)\n")
            for build_mirror in config['build_stores'][1:]:
                sys.stdout.write(build_mirror.values()[-1] + " (fetch:bld)\n")
            for remote_name in os.listdir(pjoin(DEFAULT_STORE_DIR, "remotes")):
                sys.stdout.write(remote_name + " (push)\n")
                if args.verbose:
                    import pprint
                    pp = pprint.PrettyPrinter(indent=4)
                    sys.stdout.write('=' * len(remote_name) + '\n')
                    with open(pjoin(DEFAULT_STORE_DIR,
                                    "remotes",
                                    remote_name,
                                    "app_info_data.txt"), "r") as f:
                        for line in f.readlines():
                            if not line.strip().startswith("#"):
                                app_name, app_dict = line.split("=")
                                sys.stdout.write(app_name + " = \n")
                                pp.pprint(json.loads(app_dict))
                        sys.stdout.write("\n")
                    with open(pjoin(DEFAULT_STORE_DIR,
                                    "remotes",
                                    remote_name,
                                    "user_credentials_data.txt"), "r") as f:
                        for line in f.readlines():
                            if not line.strip().startswith("#"):
                                app_user, app_cred_dict = line.split("=")
                                sys.stdout.write(app_user + " = \n")
                                pp.pprint(json.loads(app_cred_dict))
                if args.test_pcs:
                    remote_pcs_test(remote_name,ctx.logger)
        else:
            raise AssertionError()


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
        ap.add_argument('--dry-run', action='store_true',
                        help='Show what would happen')
        ap.add_argument('--force', action='store_true',
                        help='Force push of all packages')
        ap.add_argument('--objects', default="build_and_source",
                        help="Push 'build','source', or 'build_and_source'")
        ap.add_argument('name', default="primary", nargs="?",
                        help="Name of remote")

    @staticmethod
    def run(ctx, args):
        import hashlib
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
        from pcs_api.bytes_io import (MemoryByteSource, MemoryByteSink,
                                      FileByteSource, FileByteSink,
                                      StdoutProgressListener)
        from pcs_api.models import (CPath,
                                    CFolder,
                                    CBlob,
                                    CUploadRequest,
                                    CDownloadRequest)
        # set up store and change to the artifact root  dir
        from ..core import BuildStore, SourceCache
        remote_path = pjoin(DEFAULT_STORE_DIR, "remotes", args.name)
        if not args.dry_run:
            ctx.logger.info("Setting up cloud storage app")
            app_info_path = pjoin(remote_path, "app_info_data.txt")
            user_credentials_path = pjoin(remote_path,
                                          "user_credentials_data.txt")
            if not os.path.exists(app_info_path):
                msg = 'No remote application information: ' \
                      + repr(app_info_path)
                ctx.logger.critical(msg)
                msg = "Run 'hit remote add ...'"
                ctx.logger.critical(msg)
                exit(1)
            apps_repo = AppInfoFileRepository(app_info_path)
            if not os.path.exists(user_credentials_path):
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
            storage = StorageFacade.for_provider(provider_name) \
                .app_info_repository(apps_repo, app_info.app_name) \
                .user_credentials_repository(user_credentials_repo,
                                             user_info.user_id) \
                .build()
            msg = "Cloud storage user_id = " + repr(storage.get_user_id())
            ctx.logger.info(msg)
            msg = "Cloud storage quota = " + repr(storage.get_quota())
            ctx.logger.info(msg)
            ctx.logger.info("Cloud storage is  ready")

        if args.objects in ['build', 'build_and_source']:
            store = BuildStore.create_from_config(ctx.get_config(), ctx.logger)
            os.chdir(store.artifact_root)
            # try loading the local copy of the remote manifest
            try:
                with open(pjoin(remote_path,
                                "build_manifest.json"), "r") as manifest_file:
                    local_manifest = json.loads(manifest_file.read())
            except:
                msg = "Empty local manifest; build_manifest.json not read"
                ctx.logger.warn(msg)
                local_manifest = {}
            if args.dry_run:
                msg = "Comparing build store to local copy of remote manifest"
                ctx.logger.info(msg)
                skipping = ''
                pushing = ''
                for package in os.listdir(store.artifact_root):
                    for artifact in os.listdir(pjoin(store.artifact_root,
                                                     package)):
                        if (package in local_manifest and
                                artifact in local_manifest[package]):
                            skipping += package + "/" + \
                                artifact + " Skipping\n"
                        else:
                            pushing += package + "/" + artifact + " Pushing\n"
                sys.stdout.write(skipping)
                sys.stdout.write("Use --force to push all artifacts\n")
                sys.stdout.write(pushing)
            else:
                try:
                    remote_manifest_string = MemoryByteSink()
                    fpath = CPath('/bld/')
                    bpath = fpath.add("build_manifest.json")
                    download_request = CDownloadRequest(bpath,
                                                        remote_manifest_string)
                    download_request.progress_listener(
                        StdoutProgressListener())
                    storage.download(download_request)
                    manifest = json.loads(
                        str(remote_manifest_string.get_bytes()))
                except:
                    msg = "Failed to get remote manifest; " + \
                          "ALL PACKAGES WILL BE PUSHED"
                    ctx.logger.warn(msg)
                    manifest = {}
                ctx.logger.info("Writing local copy of remote  manifest")
                with open(pjoin(remote_path, "build_manifest.json"), "w") as f:
                    f.write(json.dumps(manifest))
                ctx.logger.info("Calculating which packages to push")
                push_manifest = {}
                for package in os.listdir(store.artifact_root):
                    if package not in manifest:
                        manifest[package] = {}
                    for artifact in os.listdir(pjoin(store.artifact_root,
                                                     package)):
                        if (artifact in manifest[package] and
                                not args.force):
                            msg = package + "/" + artifact + \
                                " already on remote"
                            ctx.logger.info(msg)
                            # could compare the hashes of the binary package
                        else:
                            if package not in push_manifest:
                                push_manifest[package] = set()
                            push_manifest[package].add(artifact)
                ctx.logger.info("Artifacts to push" + repr(push_manifest))
                for package, artifacts in push_manifest.iteritems():
                    for artifact in artifacts:
                        artifact_path = pjoin(package, artifact)
                        artifact_tgz = artifact + ".tar.gz"
                        artifact_tgz_path = pjoin(package, artifact_tgz)
                        ctx.logger.info("Packing and hashing " +
                                        repr(artifact_tgz_path))
                        subprocess.check_call(["tar", "czf",
                                               artifact_tgz_path,
                                               artifact_path])
                        with open(artifact_tgz_path, "rb") as f:
                            sha1 = hashlib.sha1()
                            sha1.update(f.read())
                            manifest[package][artifact] = sha1.hexdigest()
                        msg = "Pushing " + repr(artifact_tgz_path) + "\n"
                        ctx.logger.info(msg)
                        fpath = CPath('/bld/' + package)
                        storage.create_folder(fpath)
                        bpath = fpath.add(artifact_tgz)
                        upload_request = CUploadRequest(
                            bpath, FileByteSource(artifact_tgz_path))
                        upload_request.progress_listener(
                            StdoutProgressListener())
                        storage.upload(upload_request)
                        ctx.logger.info("Cleaning up and syncing manifest")
                        os.remove(artifact_tgz_path)
                        new_manifest_string = json.dumps(manifest)
                        new_manifest_bytes = bytes(new_manifest_string)
                        manifest_byte_source = MemoryByteSource(
                            new_manifest_bytes)
                        fpath = CPath('/bld/')
                        bpath = fpath.add("build_manifest.json")
                        upload_request = CUploadRequest(
                            bpath,
                            manifest_byte_source).content_type('text/plain')
                        upload_request.progress_listener(
                            StdoutProgressListener())
                        storage.upload(upload_request)
                        with open(pjoin(remote_path,
                                        "build_manifest.json"), "w") as f:
                            f.write(new_manifest_string)
        if args.objects in ['source', 'build_and_source']:
            cache = SourceCache.create_from_config(ctx.get_config(),
                                                   ctx.logger)
            os.chdir(cache.cache_path)
            # try loading the local copy of the remote manifest
            try:
                with open(pjoin(remote_path,
                                "source_manifest.json"), "r") as manifest_file:
                    local_manifest = json.loads(manifest_file.read())
            except:
                msg = "Using an empty local manifest because " + \
                      "source_manifest.json could not be read"
                ctx.logger.warn(msg)
                local_manifest = {}
            if args.dry_run:
                msg = "Comparing source to last local copy of remote manifest"
                ctx.logger.info(msg)
                skipping = ''
                pushing = ''
                for subdir in [pjoin('packs', pack_type) for
                               pack_type in ['tar.bz2', 'tar.gz', 'zip']]:
                    for source_pack in os.listdir(pjoin(cache.cache_path,
                                                        subdir)):
                        if (subdir in local_manifest and
                                source_pack in local_manifest[subdir]):
                            skipping += subdir + "/" + \
                                source_pack + " Skipping\n"
                        else:
                            pushing += subdir + "/" + \
                                source_pack + " Pushing\n"
                sys.stdout.write(skipping)
                sys.stdout.write("Use --force to push skipped source packs\n")
                sys.stdout.write(pushing)
            else:
                try:
                    remote_manifest_string = MemoryByteSink()
                    fpath = CPath('/src/')
                    bpath = fpath.add("source_manifest.json")
                    download_request = CDownloadRequest(bpath,
                                                        remote_manifest_string)
                    download_request.progress_listener(
                        StdoutProgressListener())
                    storage.download(download_request)
                    manifest = json.loads(
                        str(remote_manifest_string.get_bytes()))
                except:
                    msg = "Failed to get remote manifest; " + \
                          "all packages will be pushed"
                    ctx.logger.warn(msg)
                    manifest = {}
                ctx.logger.info("Writing local copy of remote  manifest")
                with open(pjoin(remote_path, "source_manifest.json"), "w") as f:
                    f.write(json.dumps(manifest))
                ctx.logger.info("Calculating which packages to push")
                push_manifest = {}
                for subdir in [pjoin('packs', pack_type)
                               for pack_type in ['tar.bz2', 'tar.gz', 'zip']]:
                    if subdir not in manifest:
                        manifest[subdir] = []
                    for source_pack in os.listdir(pjoin(cache.cache_path,
                                                        subdir)):
                        if source_pack in manifest[subdir] and not args.force:
                            msg = subdir + "/" + source_pack + \
                                " already on remote"
                            ctx.logger.info(msg)
                        else:
                            if subdir not in push_manifest:
                                push_manifest[subdir] = set()
                            push_manifest[subdir].add(source_pack)
                ctx.logger.info("Source packs to push" + repr(push_manifest))
                for subdir, source_packs in push_manifest.iteritems():
                    for source_pack in source_packs:
                        manifest[subdir].append(source_pack)
                        source_pack_path = pjoin(subdir, source_pack)
                        msg = "Pushing " + repr(source_pack_path) + "\n"
                        sys.stdout.write(msg)
                        fpath = CPath('/src/' + subdir)
                        storage.create_folder(fpath)
                        bpath = fpath.add(source_pack)
                        upload_request = CUploadRequest(
                            bpath,
                            FileByteSource(source_pack_path))
                        upload_request.progress_listener(
                            StdoutProgressListener())
                        storage.upload(upload_request)
                        ctx.logger.info("Syncing manifest")
                        new_manifest_string = json.dumps(manifest)
                        new_manifest_bytes = bytes(new_manifest_string)
                        manifest_byte_source = MemoryByteSource(
                            new_manifest_bytes)
                        fpath = CPath('/src')
                        bpath = fpath.add("source_manifest.json")
                        upload_request = CUploadRequest(
                            bpath,
                            manifest_byte_source).content_type('text/plain')
                        upload_request.progress_listener(
                            StdoutProgressListener())
                        storage.upload(upload_request)
                        with open(pjoin(remote_path,
                                        "source_manifest.json"), "w") as f:
                            f.write(new_manifest_string)
