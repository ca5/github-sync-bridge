import { App, Notice, Plugin, PluginSettingTab, Setting, requestUrl } from 'obsidian';

interface SyncPluginSettings {
    serverUrl: string;
    apiKey: string;
}

const DEFAULT_SETTINGS: SyncPluginSettings = {
    serverUrl: 'http://localhost:8000',
    apiKey: 'default-secret-key'
}

export default class SyncPlugin extends Plugin {
    settings: SyncPluginSettings;

    async onload() {
        await this.loadSettings();

        // This adds a settings tab so the user can configure various aspects of the plugin
        this.addSettingTab(new SyncSettingTab(this.app, this));
    }

    onunload() {

    }

    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings() {
        await this.saveData(this.settings);
    }
}

class SyncSettingTab extends PluginSettingTab {
    plugin: SyncPlugin;
    remoteSettings: any;

    constructor(app: App, plugin: SyncPlugin) {
        super(app, plugin);
        this.plugin = plugin;
        this.remoteSettings = null;
    }

    async display(): Promise<void> {
        const {containerEl} = this;

        containerEl.empty();

        containerEl.createEl('h2', {text: 'Sync Server Connection'});

        new Setting(containerEl)
            .setName('Server URL')
            .setDesc('The URL of your remote sync server.')
            .addText(text => text
                .setPlaceholder('http://localhost:8000')
                .setValue(this.plugin.settings.serverUrl)
                .onChange(async (value) => {
                    this.plugin.settings.serverUrl = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('API Key')
            .setDesc('Authentication key for the remote server.')
            .addText(text => text
                .setPlaceholder('Secret key')
                .setValue(this.plugin.settings.apiKey)
                .onChange(async (value) => {
                    this.plugin.settings.apiKey = value;
                    await this.plugin.saveSettings();
                }));

        // Button to load remote settings
        new Setting(containerEl)
            .setName('Connect to Server')
            .setDesc('Load current settings from the server.')
            .addButton(btn => btn
                .setButtonText('Connect & Load')
                .onClick(async () => {
                    await this.fetchRemoteSettings();
                }));

        containerEl.createEl('h2', {text: 'Remote Sync Settings'});

        // These settings depend on fetching from the server
        const settingsDiv = containerEl.createDiv('remote-settings-container');
        this.renderRemoteSettings(settingsDiv);
    }

    async fetchRemoteSettings() {
        try {
            const response = await requestUrl({
                url: `${this.plugin.settings.serverUrl}/api/settings`,
                method: 'GET',
                headers: {
                    'X-API-Key': this.plugin.settings.apiKey
                }
            });

            if (response.status === 200) {
                this.remoteSettings = response.json;
                new Notice('Remote settings loaded.');
                this.display(); // Re-render to show remote settings
            } else {
                new Notice(`Error fetching settings: ${response.status}`);
            }
        } catch (error) {
            new Notice(`Connection failed: ${error.message}`);
        }
    }

    async updateRemoteSettings() {
        if (!this.remoteSettings) return;

        try {
            const response = await requestUrl({
                url: `${this.plugin.settings.serverUrl}/api/settings`,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.plugin.settings.apiKey
                },
                body: JSON.stringify(this.remoteSettings)
            });

            if (response.status === 200) {
                new Notice('Remote settings updated successfully.');
            } else {
                new Notice(`Error updating settings: ${response.status}`);
            }
        } catch (error) {
            new Notice(`Update failed: ${error.message}`);
        }
    }

    async forceSync() {
        try {
            new Notice('Triggering force sync...');
            const response = await requestUrl({
                url: `${this.plugin.settings.serverUrl}/api/sync/force`,
                method: 'POST',
                headers: {
                    'X-API-Key': this.plugin.settings.apiKey
                }
            });

            if (response.status === 200) {
                new Notice('Force sync executed successfully.');
            } else {
                new Notice(`Error forcing sync: ${response.status}`);
            }
        } catch (error) {
            new Notice(`Force sync failed: ${error.message}`);
        }
    }

    renderRemoteSettings(containerEl: HTMLElement) {
        if (!this.remoteSettings) {
            containerEl.createEl('p', { text: 'Not connected. Click "Connect & Load" to view remote settings.' });
            return;
        }

        new Setting(containerEl)
            .setName('Sync .obsidian folder')
            .setDesc('Toggle whether the .obsidian configuration folder is synced.')
            .addToggle(toggle => toggle
                .setValue(this.remoteSettings.sync_obsidian_config)
                .onChange(async (value) => {
                    this.remoteSettings.sync_obsidian_config = value;
                    await this.updateRemoteSettings();
                }));

        new Setting(containerEl)
            .setName('Sync Interval (minutes)')
            .setDesc('How often the background worker should automatically sync.')
            .addText(text => text
                .setValue(this.remoteSettings.auto_sync_interval.toString())
                .onChange(async (value) => {
                    const num = parseInt(value, 10);
                    if (!isNaN(num) && num > 0) {
                        this.remoteSettings.auto_sync_interval = num;
                        await this.updateRemoteSettings();
                    }
                }));

        containerEl.createEl('h2', {text: 'Maintenance'});

        new Setting(containerEl)
            .setName('Force Full Sync')
            .setDesc('Manually trigger a full sync right now.')
            .addButton(btn => btn
                .setButtonText('Force Sync')
                .setWarning()
                .onClick(async () => {
                    await this.forceSync();
                }));
    }
}
