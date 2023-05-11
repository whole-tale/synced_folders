/* eslint-disable import/first */

import router from 'girder/router';
import events from 'girder/events';
import { exposePluginConfig } from 'girder/utilities/PluginUtils';

exposePluginConfig('synced_folders', 'plugins/synced_folders/config');

import ConfigView from './views/ConfigView';
router.route('plugins/synced_folders/config', 'SyncedFoldersConfig', function () {
    events.trigger('g:navigateTo', ConfigView);
});
