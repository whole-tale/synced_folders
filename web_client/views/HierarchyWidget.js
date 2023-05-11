import { wrap } from 'girder/utilities/PluginUtils';
import { getCurrentUser } from 'girder/auth';

import AssetstoreModel from 'girder/models/AssetstoreModel';
import HierarchyWidget from 'girder/views/widgets/HierarchyWidget';

import SyncedFoldersHierarchyWidget from '../templates/HierarchyWidget.pug';

wrap(HierarchyWidget, 'render', function (render) {
    var widget = this;

    console.log('HierarchyWidget', widget.parentModel.resourceName, widget.parentModel);

    if (getCurrentUser() && widget.parentModel.resourceName === 'folder' && widget.parentModel.attributes.isSyncFolder) {
        render.call(widget);
        $(SyncedFoldersHierarchyWidget()).prependTo(widget.$('.g-folder-header-buttons'));
        document.getElementsByClassName('g-sync-button')[0].style.display = 'inline';
    } else {
        render.call(widget);
    }
});

function _syncFolder(e) {
    var assetstore = new AssetstoreModel({ _id: this.parentModel.attributes.assetstoreId });
    assetstore.import({
        importPath: this.parentModel.attributes.syncPath,
        destinationId: this.parentModel.id,
        destinationType: 'folder',
        progress: true,
        dataType: 'syncFolder'
    });
}

HierarchyWidget.prototype.events['click .g-sync-button'] = _syncFolder;
