import { App, Modal, Notice, Plugin, PluginSettingTab, Setting, SuggestModal, requestUrl } from 'obsidian';

// ─── 型定義 ──────────────────────────────────────────────

interface SyncPluginSettings {
    serverUrl: string;
    apiKey: string;
}

export interface RemoteSettings {
    auto_sync_interval: number;
    github_branch_patterns: string[];
}

interface SyncStatus {
    last_sync_at: string | null;
    last_sync_result: 'success' | 'failed' | 'skipped' | null;
    last_sync_message: string;
    is_vault_ready: boolean;
    ob_auth_configured: boolean;
    ob_sync_configured: boolean;
    startup_log: string[];
    vault_dir: string;
}

interface GitStatus {
    branch: string;
    changed_files: string[];
    is_clean: boolean;
}

interface GitBranches {
    current: string;
    branches: string[];
}

// ─── デフォルト設定 ──────────────────────────────────────

const DEFAULT_SETTINGS: SyncPluginSettings = {
    serverUrl: 'http://localhost:8000',
    apiKey: 'default-secret-key',
};

// ─── プラグイン本体 ──────────────────────────────────────

export default class SyncBridgePlugin extends Plugin {
    settings: SyncPluginSettings;
    /** 設定タブへの参照（コマンドから状態を同期するため） */
    settingTab: SyncSettingTab | null = null;

    async onload() {
        await this.loadSettings();
        const tab = new SyncSettingTab(this.app, this);
        this.settingTab = tab;
        this.addSettingTab(tab);

        // ─── コマンドパレット ─────────────────────────────

        this.addCommand({
            id: 'connect-server',
            name: 'サーバーに接続 / ステータス取得',
            callback: () => this.settingTab?.fetchAll(),
        });

        this.addCommand({
            id: 'refresh-status',
            name: 'ステータス更新',
            callback: () => this.settingTab?.refreshStatus(),
        });

        this.addCommand({
            id: 'force-sync',
            name: 'Github Sync: 強制同期',
            callback: () => this.settingTab?.forceSync(),
        });

        this.addCommand({
            id: 'git-push',
            name: 'Git: Push',
            callback: () => this.settingTab?.pushChanges(),
        });

        this.addCommand({
            id: 'git-pull',
            name: 'Git: Pull',
            callback: () => this.settingTab?.pullChanges(),
        });

        this.addCommand({
            id: 'git-commit',
            name: 'Git: コミット',
            callback: () => {
                new CommitMessageModal(this.app, async (message) => {
                    if (!this.settingTab) return;
                    this.settingTab.commitMessage = message;
                    await this.settingTab.commitChanges();
                }).open();
            },
        });

        this.addCommand({
            id: 'git-checkout',
            name: 'Git: ブランチ切り替え',
            callback: async () => {
                const tab = this.settingTab;
                if (!tab?.gitBranches) {
                    new Notice('先にサーバーに接続してください');
                    return;
                }
                new BranchSuggestModal(this.app, tab.gitBranches.branches, async (branch) => {
                    await tab.checkoutBranch(branch);
                }).open();
            },
        });
    }

    onunload() {}

    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings() {
        await this.saveData(this.settings);
    }
}

// ─── コマンド用モーダル ──────────────────────────────────

/** コミットメッセージ入力モーダル */
class CommitMessageModal extends Modal {
    private onSubmit: (message: string) => void;
    private input = '';

    constructor(app: App, onSubmit: (message: string) => void) {
        super(app);
        this.onSubmit = onSubmit;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.createEl('h3', { text: 'Git コミット' });

        new Setting(contentEl)
            .setName('コミットメッセージ')
            .addText(text => text
                .setPlaceholder('コミットメッセージを入力...')
                .onChange(v => { this.input = v; })
                .inputEl.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') this.submit();
                }));

        new Setting(contentEl)
            .addButton(btn => btn
                .setButtonText('📝 コミット')
                .setCta()
                .onClick(() => this.submit()))
            .addButton(btn => btn
                .setButtonText('キャンセル')
                .onClick(() => this.close()));
    }

    private submit() {
        if (!this.input.trim()) {
            new Notice('コミットメッセージを入力してください');
            return;
        }
        this.close();
        this.onSubmit(this.input.trim());
    }

    onClose() {
        this.contentEl.empty();
    }
}

/** ブランチ選択モーダル（コマンドパレット風） */
class BranchSuggestModal extends SuggestModal<string> {
    private branches: string[];
    private onChoose: (branch: string) => void;

    constructor(app: App, branches: string[], onChoose: (branch: string) => void) {
        super(app);
        this.branches = branches;
        this.onChoose = onChoose;
        this.setPlaceholder('ブランチを選択...');
    }

    getSuggestions(query: string): string[] {
        return this.branches.filter(b => b.toLowerCase().includes(query.toLowerCase()));
    }

    renderSuggestion(branch: string, el: HTMLElement) {
        el.createEl('div', { text: `🌿 ${branch}` });
    }

    onChooseSuggestion(branch: string) {
        this.onChoose(branch);
    }
}

/** ブランチ切り替え時の未コミット変更処理方法を選ぶモーダル */
class CheckoutModeModal extends Modal {
    private branch: string;
    private changedFiles: string[];
    private onChoose: (mode: string, commitMessage?: string) => void;
    private commitMessage = '';

    constructor(
        app: App,
        branch: string,
        changedFiles: string[],
        onChoose: (mode: string, commitMessage?: string) => void,
    ) {
        super(app);
        this.branch = branch;
        this.changedFiles = changedFiles;
        this.onChoose = onChoose;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.createEl('h3', { text: `🔀 ブランチ切り替え: ${this.branch}` });
        contentEl.createEl('p', {
            text: `未コミットの変更が ${this.changedFiles.length} 件あります。どのように処理しますか？`,
        });

        // 変更ファイル一覧（折りたたみ）
        if (this.changedFiles.length > 0) {
            const details = contentEl.createEl('details');
            details.createEl('summary', { text: `変更ファイル (${this.changedFiles.length} 件)` });
            const ul = details.createEl('ul', { cls: 'git-changed-files' });
            this.changedFiles.forEach(f => ul.createEl('li', { text: f }));
        }

        contentEl.createEl('hr');

        // コミットメッセージ欄（commit_push 用）
        const commitMsgSetting = new Setting(contentEl)
            .setName('📝 コミット & Push のメッセージ（省略可）')
            .setDesc('空欄の場合は自動生成されます')
            .addText(text => text
                .setPlaceholder('コミットメッセージ...')
                .onChange(v => { this.commitMessage = v; }));

        // ── 3択ボタン ─────────────────────────────────────

        new Setting(contentEl)
            .setName('📦 Stash して引き継ぐ')
            .setDesc('変更を一時保存し、新ブランチに持ち込む')
            .addButton(btn => btn
                .setButtonText('Stash')
                .setCta()
                .onClick(() => { this.close(); this.onChoose('stash'); }));

        new Setting(contentEl)
            .setName('⬆️ コミット & Push してから切り替え')
            .setDesc('現在のブランチにコミット・Push してから切り替える')
            .addButton(btn => btn
                .setButtonText('Commit & Push')
                .onClick(() => { this.close(); this.onChoose('commit_push', this.commitMessage); }));

        new Setting(contentEl)
            .setName('🗑️ 変更を破棄して切り替え')
            .setDesc('未コミットの変更をすべて削除してから切り替える（元に戻せません）')
            .addButton(btn => btn
                .setButtonText('Discard & Switch')
                .setWarning()
                .onClick(() => { this.close(); this.onChoose('discard'); }));

        new Setting(contentEl)
            .addButton(btn => btn
                .setButtonText('キャンセル')
                .onClick(() => this.close()));
    }

    onClose() {
        this.contentEl.empty();
    }
}

// ─── 設定タブ ────────────────────────────────────────────

class SyncSettingTab extends PluginSettingTab {
    plugin: SyncBridgePlugin;

    // サーバーから取得したデータ（未接続なら null）
    remoteSettings: RemoteSettings | null = null;
    syncStatus: SyncStatus | null = null;
    gitStatus: GitStatus | null = null;
    gitBranches: GitBranches | null = null;

    // コールドスタート待機状態
    private isInitializing = false;
    private initPhase = '';
    private initLog: string[] = [];
    private retryTimer: number | null = null;

    // コミットメッセージ入力用
    commitMessage = '';

    constructor(app: App, plugin: SyncBridgePlugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    // ─── API ヘルパー ─────────────────────────────────────

    private get headers() {
        return { 'X-API-Key': this.plugin.settings.apiKey };
    }

    private url(path: string) {
        return `${this.plugin.settings.serverUrl}${path}`;
    }

    private async apiGet<T>(path: string): Promise<T> {
        const res = await requestUrl({ url: this.url(path), method: 'GET', headers: this.headers, throw: false });
        if (res.status === 503) {
            const body = res.json ?? {};
            if (body.status === 'initializing') {
                const err: any = new Error('initializing');
                err.isInitializing = true;
                err.phase = body.phase ?? '';
                err.log = body.startup_log ?? [];
                throw err;
            }
        }
        if (res.status !== 200) throw new Error(res.json?.detail ?? `HTTP ${res.status}`);
        return res.json as T;
    }

    private async apiPost<T>(path: string, body?: object): Promise<T> {
        const res = await requestUrl({
            url: this.url(path),
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: body ? JSON.stringify(body) : undefined,
            throw: false,
        });
        if (res.status !== 200) {
            const detail = res.json?.detail ?? `HTTP ${res.status}`;
            throw new Error(detail);
        }
        return res.json as T;
    }

    // ─── データ取得 ───────────────────────────────────────

    private stopRetry() {
        if (this.retryTimer !== null) {
            window.clearTimeout(this.retryTimer);
            this.retryTimer = null;
        }
    }

    private scheduleRetry() {
        this.stopRetry();
        this.retryTimer = window.setTimeout(() => {
            this.retryTimer = null;
            this.fetchAll();
        }, 3000);
    }

    async fetchAll() {
        try {
            [this.remoteSettings, this.syncStatus, this.gitStatus, this.gitBranches] =
                await Promise.all([
                    this.apiGet<RemoteSettings>('/api/settings'),
                    this.apiGet<SyncStatus>('/api/sync/status'),
                    this.apiGet<GitStatus>('/api/git/status'),
                    this.apiGet<GitBranches>('/api/git/branches'),
                ]);
            // 接続成功 → 初期化待ち状態を解除
            this.stopRetry();
            this.isInitializing = false;
            new Notice('✅ サーバーに接続しました');
        } catch (e: any) {
            if (e.isInitializing) {
                this.isInitializing = true;
                this.initPhase = e.phase;
                this.initLog = e.log;
                this.scheduleRetry();
            } else {
                new Notice(`❌ 接続失敗: ${e.message}`);
            }
        }
        this.display();
    }

    async refreshStatus() {
        try {
            [this.syncStatus, this.gitStatus, this.gitBranches] = await Promise.all([
                this.apiGet<SyncStatus>('/api/sync/status'),
                this.apiGet<GitStatus>('/api/git/status'),
                this.apiGet<GitBranches>('/api/git/branches'),
            ]);
            this.isInitializing = false;
        } catch (e: any) {
            if (e.isInitializing) {
                this.isInitializing = true;
                this.initPhase = e.phase;
                this.initLog = e.log;
                this.scheduleRetry();
            } else {
                new Notice(`ステータス更新失敗: ${e.message}`);
            }
        }
        this.display();
    }

    // ─── Git 操作 ─────────────────────────────────────────

    async checkoutBranch(branch: string) {
        try {
            // git status を確認して未コミット変更があれば選択モーダルを表示
            const status = await this.apiGet<GitStatus>('/api/git/status');
            const hasDirty = !status.is_clean;

            const doCheckout = async (mode: string, commitMessage?: string) => {
                new Notice(`🔀 ${branch} に切り替え中...`);
                const result = await this.apiPost<{ branch: string; note: string }>(
                    '/api/git/checkout',
                    { branch, mode, commit_message: commitMessage ?? '' }
                );
                const noteText = result.note ? ` (${result.note})` : '';
                new Notice(`✅ ${branch} に切り替えました${noteText}`);
                await this.refreshStatus();
                // ブランチ切り替え後は強制同期も実行してiPhone等にすぐ反映させる
                await this.forceSync();
            };

            if (!hasDirty) {
                await doCheckout('stash');
            } else {
                new CheckoutModeModal(
                    this.app,
                    branch,
                    status.changed_files,
                    async (mode, commitMessage) => {
                        try {
                            await doCheckout(mode, commitMessage);
                        } catch (e: any) {
                            new Notice(`❌ 切り替え失敗: ${e.message}`);
                        }
                    }
                ).open();
            }
        } catch (e: any) {
            new Notice(`❌ 切り替え失敗: ${e.message}`);
        }
    }

    async commitChanges() {
        if (!this.commitMessage.trim()) {
            new Notice('コミットメッセージを入力してください');
            return;
        }
        try {
            new Notice('📝 コミット中...');
            await this.apiPost('/api/git/commit', { message: this.commitMessage });
            new Notice('✅ コミットしました');
            this.commitMessage = '';
        } catch (e) {
            new Notice(`❌ コミット失敗: ${e.message}`);
        }
        await this.refreshStatus();
    }

    async pushChanges() {
        try {
            new Notice('⬆️ Push 中...');
            const result = await this.apiPost<{ branch: string }>('/api/git/push');
            new Notice(`✅ ${result.branch} を Push しました`);
        } catch (e) {
            new Notice(`❌ Push 失敗: ${e.message}`);
        }
        await this.refreshStatus();
    }

    async pullChanges() {
        try {
            new Notice('⬇️ Pull 中...');
            const result = await this.apiPost<{ branch: string; output: string }>('/api/git/pull');
            new Notice(`✅ Pull 完了 (${result.branch})`);
        } catch (e) {
            new Notice(`❌ Pull 失敗: ${e.message}`);
        }
        await this.refreshStatus();
    }

    async forceSync() {
        try {
            new Notice('🔄 強制同期中...');
            await this.apiPost('/api/sync/force');
            new Notice('✅ 同期が完了しました');
        } catch (e) {
            new Notice(`❌ 同期失敗: ${e.message}`);
        }
        await this.refreshStatus();
    }

    async updateRemoteSettings() {
        if (!this.remoteSettings) return;
        try {
            await this.apiPost('/api/settings', this.remoteSettings);
            new Notice('✅ 設定を保存しました');
        } catch (e) {
            new Notice(`❌ 設定保存失敗: ${e.message}`);
        }
    }

    // ─── UI 描画 ──────────────────────────────────────────

    async display(): Promise<void> {
        const { containerEl } = this;
        containerEl.empty();

        // ── 接続設定 ──────────────────────────────────────
        containerEl.createEl('h2', { text: '🔌 サーバー接続' });

        new Setting(containerEl)
            .setName('Server URL')
            .setDesc('同期サーバーの URL')
            .addText(text => text
                .setPlaceholder('http://localhost:8000')
                .setValue(this.plugin.settings.serverUrl)
                .onChange(async (value) => {
                    this.plugin.settings.serverUrl = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('API Key')
            .setDesc('サーバーの認証キー')
            .addText(text => text
                .setPlaceholder('default-secret-key')
                .setValue(this.plugin.settings.apiKey)
                .onChange(async (value) => {
                    this.plugin.settings.apiKey = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('接続')
            .setDesc(this.remoteSettings ? '✅ 接続済み' : '未接続')
            .addButton(btn => btn
                .setButtonText('Connect & Load')
                .setCta()
                .onClick(() => this.fetchAll()));

        // ─── コールドスタート待機中 ────────────────────────────
        if (this.isInitializing) {
            const box = containerEl.createEl('div', { cls: 'sync-initializing-box' });
            box.createEl('p', { text: '⏳ サーバー起動中...' });
            box.createEl('p', { text: `フェーズ: ${this.initPhase}`, cls: 'sync-status-message' });
            box.createEl('p', { text: '3 秒後に自動で再接続します', cls: 'sync-status-message' });
            if (this.initLog.length > 0) {
                const details = box.createEl('details');
                details.createEl('summary', { text: `🪵 起動ログ (${this.initLog.length} 件)` });
                details.createEl('pre', { cls: 'sync-startup-log', text: this.initLog.join('\n') });
            }
            new Setting(containerEl)
                .addButton(btn => btn
                    .setButtonText('キャンセル')
                    .onClick(() => {
                        this.stopRetry();
                        this.isInitializing = false;
                        this.display();
                    }));
            return;
        }

        if (!this.remoteSettings) return;

        // ── Sync ステータス ────────────────────────────────
        containerEl.createEl('h2', { text: '📊 同期ステータス' });

        if (this.syncStatus) {
            const s = this.syncStatus;
            const resultEmoji = s.last_sync_result === 'success' ? '✅'
                : s.last_sync_result === 'failed' ? '❌'
                : s.last_sync_result === 'skipped' ? '⏭️' : '—';
            const lastAt = s.last_sync_at
                ? new Date(s.last_sync_at).toLocaleString('ja-JP')
                : 'まだ実行されていません';

            const info = containerEl.createEl('div', { cls: 'sync-status-info' });
            info.createEl('p', { text: `${resultEmoji} 最終同期: ${lastAt}` });
            if (s.last_sync_message) {
                info.createEl('p', { text: `メッセージ: ${s.last_sync_message}`, cls: 'sync-status-message' });
            }
            info.createEl('p', { text: `Vault: ${s.is_vault_ready ? '✅ 準備完了' : '❌ 未準備'}` });

            // Obsidian 認証状態
            if (!s.ob_auth_configured) {
                const warn = info.createEl('div', { cls: 'sync-status-warning' });
                warn.createEl('p', { text: '⚠️ Obsidian 認証未設定' });
                warn.createEl('p', { text: 'setup-obsidian-auth.sh を実行して OBSIDIAN_AUTH_TOKEN を登録してください。', cls: 'sync-status-message' });
            }

            // スタートアップログ（折りたたみ）
            if (s.startup_log && s.startup_log.length > 0) {
                const details = info.createEl('details');
                details.createEl('summary', { text: `🪵 サーバー起動ログ (${s.startup_log.length} 件)` });
                const pre = details.createEl('pre', { cls: 'sync-startup-log' });
                pre.setText(s.startup_log.join('\n'));
            }
        }

        new Setting(containerEl)
            .setName('ステータス更新')
            .setDesc('サーバーの最新状態を取得して表示を更新します')
            .addButton(btn => btn
                .setButtonText('🔄 更新')
                .onClick(() => this.refreshStatus()));

        new Setting(containerEl)
            .setName('Github Sync 強制実行')
            .setDesc('今すぐサーバーで ob sync を実行します')
            .addButton(btn => btn
                .setButtonText('Force Sync')
                .setWarning()
                .onClick(() => this.forceSync()));

        // ── Github Sync 設定 ────────────────────────────
        containerEl.createEl('h2', { text: '⚙️ Sync 設定' });

        new Setting(containerEl)
            .setName('自動同期の間隔（分）')
            .setDesc('サーバーが ob sync を実行する頻度')
            .addText(text => text
                .setValue(this.remoteSettings!.auto_sync_interval.toString())
                .onChange(async (value) => {
                    const num = parseInt(value, 10);
                    if (!isNaN(num) && num > 0) {
                        this.remoteSettings!.auto_sync_interval = num;
                        await this.updateRemoteSettings();
                    }
                }));

        // ── Git 操作 ──────────────────────────────────────
        containerEl.createEl('h2', { text: '🌿 Git 操作' });

        if (this.gitStatus && this.gitBranches) {
            const gs = this.gitStatus;
            const gb = this.gitBranches;

            // ブランチ情報
            const branchInfo = containerEl.createEl('div', { cls: 'git-branch-info' });
            branchInfo.createEl('p', { text: `現在のブランチ: 🌿 ${gs.branch}` });
            branchInfo.createEl('p', {
                text: gs.is_clean
                    ? '✅ 変更なし（クリーン）'
                    : `📝 ${gs.changed_files.length} ファイルに変更あり`,
            });

            // ブランチ切り替え
            // github_branch_patterns でフィルタ（空なら全表示）
            const patterns = this.remoteSettings!.github_branch_patterns;
            const filteredBranches = patterns.length > 0
                ? gb.branches.filter(b => patterns.some(p =>
                    p.endsWith('*') ? b.startsWith(p.slice(0, -1)) : b === p
                ))
                : gb.branches;

            new Setting(containerEl)
                .setName('ブランチ切り替え')
                .setDesc('切り替え後は自動で git pull が実行されます')
                .addDropdown(drop => {
                    filteredBranches.forEach(b => drop.addOption(b, b));
                    drop.setValue(gs.branch);
                    drop.onChange(async (value) => {
                        if (value !== gs.branch) {
                            await this.checkoutBranch(value);
                        }
                    });
                });

            // コミット
            containerEl.createEl('h3', { text: 'コミット & Push' });

            new Setting(containerEl)
                .setName('コミットメッセージ')
                .addText(text => text
                    .setPlaceholder('コミットメッセージを入力...')
                    .setValue(this.commitMessage)
                    .onChange((value) => { this.commitMessage = value; }));

            new Setting(containerEl)
                .setName('Git 操作')
                .addButton(btn => btn
                    .setButtonText('📝 Commit')
                    .onClick(() => this.commitChanges()))
                .addButton(btn => btn
                    .setButtonText('⬆️ Push')
                    .onClick(() => this.pushChanges()))
                .addButton(btn => btn
                    .setButtonText('⬇️ Pull')
                    .onClick(() => this.pullChanges()));

            // 変更ファイル一覧（変更がある場合のみ）
            if (!gs.is_clean) {
                const changedEl = containerEl.createEl('details');
                changedEl.createEl('summary', { text: `変更ファイル (${gs.changed_files.length})` });
                const ul = changedEl.createEl('ul', { cls: 'git-changed-files' });
                gs.changed_files.forEach(f => ul.createEl('li', { text: f }));
            }
        }
    }
}
