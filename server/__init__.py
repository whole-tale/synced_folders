#!/usr/bin/env python
# -*- coding: utf-8 -*-

import hashlib
import os
import pathlib

import magic
from girder import events, logger
from girder.api import rest
from girder.constants import AccessType
from girder.exceptions import ValidationException
from girder.models.assetstore import Assetstore
from girder.models.file import File
from girder.models.folder import Folder
from girder.models.item import Item
from girder.utility import toBool
from girder.utility.progress import ProgressContext


def get_checksums_from_host(host_path):
    # give a path, return a dict of checksums mapped to subpaths
    checksums = {}
    for root, dirs, files in os.walk(host_path):
        for name in files:
            path = os.path.join(root, name)
            rel_path = os.path.relpath(path, host_path)
            checksums[get_checksum(path)] = rel_path
    return checksums


def get_checksum(path, size=4 * 1024**2):
    # given a path, get the checksum of the first size bytes, unless the file is smaller, or size
    # is None, in which case the whole file is used
    with open(path, "rb") as f:
        if size is None:
            return hashlib.sha512(f.read()).hexdigest()
        else:
            return hashlib.sha512(f.read(size)).hexdigest()


@rest.boundHandler
def import_sync_folder(self, event):
    params = event.info["params"]
    logger.info("Importing sync folder with params: %s" % params)
    if not params.get("dataType") == "syncFolder":
        logger.warning("Importing using default importer")
        return

    import_cls = SyncFolderImporter
    if params["destinationType"] != "folder":
        raise ValidationException(
            "SyncFolder data can only be imported to girder folders"
        )

    importPath = params.get("importPath")
    if not os.path.exists(importPath):
        raise ValidationException("Not found: %s." % importPath)
    if not os.path.isdir(importPath):
        raise ValidationException("Not a directory: %s." % importPath)

    progress = toBool(params.get("progress", "false"))
    user = self.getCurrentUser()
    assetstore = Assetstore().load(event.info["id"])
    parent = self.model(params["destinationType"]).load(
        params["destinationId"], user=user, level=AccessType.ADMIN, exc=True
    )
    params["fileExcludeRegex"] = r"^_\..*"

    with ProgressContext(progress, user=user, title="Syncing Folder") as ctx:
        importer = import_cls(assetstore, user, ctx, params=params)
        importer.import_data(parent, params["destinationType"], importPath)

    event.preventDefault().addResponse(None)


class SyncFolderImporter:
    def __init__(self, assetstore, user, progress, params=None):
        self.assetstore = assetstore
        self.user = user
        self.progress = progress
        self.params = params or {}
        self.mime = magic.Magic(mime=True)

    def get_state(self, parent):
        state = {}
        for path, fobj in Folder().fileList(
            parent, user=self.user, subpath=False, includeMetadata=False, data=False
        ):
            state[fobj["partialSha512"]] = path
        return state

    def delete_empty_folders(self, parent):
        # delete empty folders
        logger.info(f"Parent: {parent}")
        for folder in Folder().childFolders(parent, parentType="folder", user=self.user):
            self.delete_empty_folders(folder)
            logger.info("Checking folder %s (size: %s)" % (folder["name"], folder["size"]))
            if folder["size"] == 0:
                Folder().remove(folder)

    def import_data(self, parent, parentType, importPath):
        assert parentType == "folder"
        self.progress.update(message="Calculating checksums")
        current_state = get_checksums_from_host(importPath)
        previous_state = self.get_state(parent)

        logger.info("Current state: %s" % current_state)
        logger.info("Previous state: %s" % previous_state)

        for checksum, path in current_state.items():
            if checksum in previous_state:
                if path != previous_state[checksum]:
                    # file has changed location
                    logger.info("Moving %s to %s" % (previous_state[checksum], path))
                    self.move_item(parent, previous_state[checksum], path, importPath, checksum)
            else:
                # file is new or has been updated
                logger.info("Importing %s" % path)
                self.import_item(parent, path, importPath, checksum)

        for checksum, path in previous_state.items():
            if checksum not in current_state and path not in current_state.values():
                # file has been deleted
                logger.info("Deleting %s" % path)
                item = self.get_item_from_rel_path(parent, path)
                Item().remove(item)
        logger.info("Updating folder size")
        Folder().updateSize(parent)
        logger.info("Deleting empty folders")
        self.delete_empty_folders(parent)

    def move_item(self, parent, old_path, new_path, importPath, checksum):
        # get the source item
        item = self.get_item_from_rel_path(parent, old_path)
        logger.info("Item before move: %s" % item)
        new_parent = self.get_folder_from_rel_path(parent, new_path)
        item = Item().move(item, new_parent)
        logger.info("Item after move: %s" % item)

        fpath = os.path.abspath(os.path.expanduser(os.path.join(importPath, new_path)))
        File().update(
            {"partialSha512": checksum}, {"$set": {"path": fpath}}, multi=True,
        )
        return item

    def get_folder_from_rel_path(self, parent, rel_path):
        rel_path = pathlib.Path(rel_path)
        for name in rel_path.parts[:-1]:
            parent = Folder().createFolder(
                parent, name, parentType="folder", creator=self.user, reuseExisting=True,
            )
        return parent

    def get_item_from_rel_path(self, parent, rel_path):
        parent = self.get_folder_from_rel_path(parent, rel_path)
        rel_path = pathlib.Path(rel_path)
        return Item().createItem(
            name=rel_path.parts[-1], creator=self.user, folder=parent, reuseExisting=True
        )

    def import_item(self, parent, rel_path, importPath, checksum):
        item = self.get_item_from_rel_path(parent, rel_path)
        fpath = os.path.join(importPath, rel_path)
        events.trigger(
            "filesystem_assetstore_imported",
            {"id": item["_id"], "type": "item", "importPath": fpath},
        )
        self.importFile(
            item, fpath, self.user, mimeType=self.mime.from_file(fpath), checksum=checksum
        )

    def importFile(self, item, path, user, name=None, mimeType=None, **kwargs):
        stat = os.stat(path)
        name = name or os.path.basename(path)
        size = stat.st_size
        file = File().createFile(
            name=name, creator=self.user, item=item, reuseExisting=True, assetstore=self.assetstore,
            mimeType=mimeType, size=size, saveFile=False
        )
        file["path"] = os.path.abspath(os.path.expanduser(path))
        file["partialSha512"] = kwargs.get("checksum") or get_checksum(path)
        file["mtime"] = stat.st_mtime
        file["imported"] = True
        # manually set size and mimeType in case File was already there
        file["size"] = size
        file["mimeType"] = mimeType
        return File().save(file)


def load(info):
    File().exposeFields(level=AccessType.READ, fields="partialSha512")

    events.bind("rest.post.assetstore/:id/import.before", "sync_folders", import_sync_folder)
