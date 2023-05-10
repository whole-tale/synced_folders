import os
import shutil
import tempfile
from tests import base

from girder.exceptions import GirderException
from girder.models.assetstore import Assetstore
from girder.models.folder import Folder


def setUpModule():
    base.enabledPlugins.append("synced_folders")
    base.startServer()
    try:
        assetstore = Assetstore().getCurrent()
    except GirderException:
        assetstore = Assetstore().createFilesystemAssetstore("test", tempfile.mkdtemp())
        assetstore["current"] = True
        Assetstore().save(assetstore)


def tearDownModule():
    Assetstore().remove(Assetstore().getCurrent())
    base.stopServer()


class SyncFolderImporterTestCase(base.TestCase):
    def setUp(self):
        super(SyncFolderImporterTestCase, self).setUp()

        self.user = self.model("user").createUser(
            login="admin",
            firstName="admin",
            lastName="admin",
            password="password",
            email="admin@localhost.com",
        )

        self.folder = self.model("folder").createFolder(
            parent=self.user, name="root", parentType="user", public=True
        )
        self.assetstore = Assetstore().getCurrent()

    def tearDown(self):
        self.model("folder").remove(self.folder)
        self.model("user").remove(self.user)
        super(SyncFolderImporterTestCase, self).tearDown()

    @staticmethod
    def _setup_first_folder():
        host_root = tempfile.mkdtemp()
        # create mock structure
        # <host_root>
        # ├── ala.py
        # ├── codeswarm.ogv
        # ├── subfolder1
        # │   └── plugin.json
        # └── subfolder2
        #     └── LICENSE

        # create files
        with open(f"{host_root}/ala.py", "w") as f:
            f.write("ala has a cat")
        with open(f"{host_root}/codeswarm.ogv", "w") as f:
            f.write("codeswarm is a cat")

        # create folders
        subfolder1 = f"{host_root}/subfolder1"
        subfolder2 = f"{host_root}/subfolder2"
        os.mkdir(subfolder1)
        os.mkdir(subfolder2)

        # create files in subfolders
        with open(f"{subfolder1}/plugin.json", "w") as f:
            f.write("plugin.json is a serialized cat")

        with open(f"{subfolder2}/LICENSE", "w") as f:
            f.write("Cats are definitely not licensed")

        return host_root

    @staticmethod
    def _setup_second_folder(host_root=None):
        # Take the first folder and perform following changes:
        # 1. Rename subfolder2 to subfolderA
        # 2. Remove codeswarm.ogv
        # 3. Add new file ala.txt
        # 4. Modify the content of subfolder1/plugin.json

        if host_root is None:
            host_root = tempfile.mkdtemp()

        # rename subfolder2 to subfolderA
        os.rename(f"{host_root}/subfolder2", f"{host_root}/subfolderA")

        # remove codeswarm.ogv
        os.remove(f"{host_root}/codeswarm.ogv")

        # add new file ala.txt
        with open(f"{host_root}/ala.txt", "w") as f:
            f.write("ala is a cat")

        # modify the content of subfolder1/plugin.json
        with open(f"{host_root}/subfolder1/plugin.json", "w") as f:
            f.write("plugin.json is a serialized cat, but modified")

        return host_root

    def testImport(self):
        host_root = self._setup_first_folder()
        resp = self.request(
            path=f"/assetstore/{self.assetstore['_id']}/import",
            method="POST",
            user=self.user,
            params={
                "destinationId": str(self.folder["_id"]),
                "destinationType": "folder",
                "importPath": host_root,
                "dataType": "syncFolder",
            },
        )
        self.assertStatusOk(resp)

        for path, fobj in Folder().fileList(
            self.folder, user=self.user, data=False, subpath=False
        ):
            real_path = os.path.join(host_root, path)
            self.assertTrue(os.path.exists(real_path))
            self.assertEqual(fobj["size"], os.path.getsize(real_path))

        host_root = self._setup_second_folder(host_root=host_root)
        resp = self.request(
            path=f"/assetstore/{self.assetstore['_id']}/import",
            method="POST",
            user=self.user,
            params={
                "destinationId": str(self.folder["_id"]),
                "destinationType": "folder",
                "importPath": host_root,
                "dataType": "syncFolder",
            },
        )
        paths = set()
        for path, fobj in Folder().fileList(
            self.folder, user=self.user, data=False, subpath=False
        ):
            paths.add(path)
            real_path = os.path.join(host_root, path)
            self.assertTrue(os.path.exists(real_path))
            self.assertEqual(fobj["size"], os.path.getsize(real_path))

        self.assertNotIn("codeswarm.ogv", paths)

        # check that folder subfolder2 was removed
        resp = self.request(
            path="/folder",
            method="GET",
            user=self.user,
            params={
                "parentType": "folder",
                "parentId": str(self.folder["_id"]),
                "name": "subfolder2",
            },
        )
        self.assertStatusOk(resp)
        self.assertEqual(len(resp.json), 0)

        shutil.rmtree(host_root, ignore_errors=True)
