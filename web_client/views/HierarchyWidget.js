import { wrap } from 'girder/utilities/PluginUtils';
import { getCurrentUser } from 'girder/auth';

import AssetstoreModel from 'girder/models/AssetstoreModel';
import router from 'girder/router';
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
    e.preventDefault();
    var assetstore = new AssetstoreModel({ _id: this.parentModel.attributes.assetstoreId });
    assetstore.off('g:imported').on('g:imported', function () {
        router.navigate('folder/' + this.parentModel.id, { trigger: true });
    }, this).off('g:error').on('g:error', function (err) {
        this.$('.g-validation-failed-message').text(err.responseJSON.message);
    }, this).import({
        importPath: this.parentModel.attributes.syncPath,
        destinationId: this.parentModel.id,
        destinationType: 'folder',
        progress: true,
        dataType: 'syncFolder'
    });
}

HierarchyWidget.prototype.events['click .g-sync-button'] = _syncFolder;
