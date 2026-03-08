import { App, Modal, Notice, Plugin, PluginSettingTab, Setting, SuggestModal, requestUrl, moment } from 'obsidian';

// ─── i18n ────────────────────────────────────────────────
const STRINGS = {
    en: {
        cmdConnect: "Connect server / Fetch status",
        cmdRefresh: "Refresh status",
        cmdForceSync: "Github Sync: Force Sync",
        cmdGitPush: "Git: Push",
        cmdGitPull: "Git: Pull",
        cmdGitCommit: "Git: Commit",
        cmdGitCheckout: "Git: Checkout branch",
        connectFirst: "Please connect to the server first",
        commitMessageTitle: "Commit message",
        commitMessagePlaceholder: "Enter commit message...",
        btnCommit: "📝 Commit",
        btnCancel: "Cancel",
        commitEmpty: "Please enter a commit message",
        strCurrentBranch: "Current branch: 🌿 ",
        strSelectBranch: " | Select branch to checkout...",
        strCurrent: " (Current)",
        checkoutModalTitle: "Uncommitted changes on checkout",
        checkoutModalDesc1: "Uncommitted changes exist on branch 🌿 ",
        strChangedFiles: "Changed files (",
        strCountSuffix: " files)",
        optStash: "📦 Stash and carry over",
        optStashDesc: "Stash changes temporarily and checkout",
        optCommitPush: "📤 Commit & Push and checkout",
        optCommitPushDesc: "Commit current changes and push to remote",
        optDiscard: "🗑️ Discard and checkout",
        optDiscardDesc: "Discard all uncommitted changes and checkout (irreversible)",
        lblCheckoutBranch: "🔀 Checkout branch: ",
        checkoutConflictDesc: "Uncommitted changes exist. How would you like to proceed?",
        lblCommitMsgOpt: "📝 Commit & Push message (optional)",
        descCommitMsgOpt: "Auto-generated if empty",
        placeholderCommitMsg: "Commit message...",
        btnForceSync: "Force Sync",
        btnStash: "Stash",
        btnCommitPush: "Commit & Push",
        btnDiscard: "Discard & Switch",
        msgConnected: "✅ Connected to server",
        msgConnFailed: "❌ Connection failed: ",
        msgForceSyncing: "🔄 Force syncing...",
        msgSyncDone: "✅ Sync completed",
        msgSyncFailed: "❌ Sync failed: ",
        msgCheckingOut: "🔀 Checking out ",
        msgCheckedOut: "✅ Checked out ",
        msgCommitting: "📝 Committing changes...",
        msgCommitted: "✅ Committed: ",
        msgCommitFailed: "❌ Commit failed: ",
        msgPushing: "⬆️ Pushing...",
        msgPushDone: "✅ Push completed",
        msgPushFailed: "❌ Push failed: ",
        msgPulling: "⬇️ Pulling...",
        msgPullDone: "✅ Pull completed",
        msgPullFailed: "❌ Pull failed: ",
        cmdGitReset: "Git: Reset to remote",
        btnReset: "⚠️ Reset to remote",
        msgResetting: "⚠️ Resetting to remote...",
        msgResetDone: "✅ Reset completed",
        msgResetFailed: "❌ Reset failed: ",
        descReset: "Discard all local changes and reset to match the remote branch (irreversible)",
        msgSettingsSaved: "✅ Settings saved",
        msgSettingsFailed: "❌ Failed to save settings: ",
        msgRefreshFailed: "❌ Failed to refresh status: ",
        msgCheckoutFailed: "❌ Checkout failed: ",
        secServerConn: "🔌 Server Connection",
        lblServerUrl: "Server URL",
        descServerUrl: "URL of the sync server",
        lblApiKey: "API Key",
        descApiKey: "Authentication key for the server",
        lblConnStatus: "Connection",
        valConnected: "✅ Connected",
        valNotConnected: "Not connected",
        btnConnectLoad: "Connect & Load",
        boxStarting: "⏳ Starting server...",
        boxPhase: "Phase: ",
        boxReconnecting: "Reconnecting automatically in 3 seconds",
        boxStartupLog: "🪵 Startup log (",
        secSyncStatus: "📊 Sync Status",
        lblLastSync: "Last sync: ",
        valNotExecuted: "Not executed yet",
        lblMessage: "Message: ",
        lblVaultReady: "Vault: ",
        valReady: "✅ Ready",
        valNotReady: "❌ Not ready",
        warnAuthMissing: "⚠️ Obsidian auth missing",
        warnAuthDesc: "Run setup-obsidian-auth.sh to set OBSIDIAN_AUTH_TOKEN.",
        lblRefresh: "Refresh status",
        descRefresh: "Fetch latest server status and update display",
        btnRefresh: "🔄 Refresh",
        lblForceSync: "Force Github Sync",
        descForceSync: "Execute ob sync on the server immediately",
        secSyncSettings: "⚙️ Sync Settings",
        lblAutoSync: "Auto-sync interval (min)",
        descAutoSync: "Frequency of server running ob sync",
        secGitOps: "🌿 Git Operations",
        valClean: "✅ Clean",
        lblFilesChanged: " files changed",
        lblCheckout: "Checkout branch",
        descCheckout: "Auto git pull will run after checkout",
        lblCommitPush: "Commit & Push",
        btnPush: "⬆️ Push",
        btnPull: "⬇️ Pull",
        valUnknown: "Unknown"
    },
    ja: {
        cmdConnect: "サーバーに接続 / ステータス取得",
        cmdRefresh: "ステータス更新",
        cmdForceSync: "Github Sync: 強制同期",
        cmdGitPush: "Git: Push",
        cmdGitPull: "Git: Pull",
        cmdGitCommit: "Git: コミット",
        cmdGitCheckout: "Git: ブランチ切り替え",
        connectFirst: "先にサーバーに接続してください",
        commitMessageTitle: "コミットメッセージ",
        commitMessagePlaceholder: "コミットメッセージを入力...",
        btnCommit: "📝 コミット",
        btnCancel: "キャンセル",
        commitEmpty: "コミットメッセージを入力してください",
        strCurrentBranch: "現在のブランチ: 🌿 ",
        strSelectBranch: " | 切り替えるブランチを選択...",
        strCurrent: " (現在)",
        checkoutModalTitle: "ブランチ切り替え時の未コミット変更",
        checkoutModalDesc1: "現在のブランチ 🌿 ",
        strChangedFiles: "変更ファイル (",
        strCountSuffix: " 件)",
        optStash: "📦 Stash して引き継ぐ",
        optStashDesc: "変更を一時的に退避(stash)してから切り替えます",
        optCommitPush: "📤 Commit & Push して切り替える",
        optCommitPushDesc: "現在の変更をコミットしてリモートに保存します",
        optDiscard: "🗑️ 破棄して切り替える",
        optDiscardDesc: "未コミットの変更をすべて破棄しクリーンな状態にします（※元に戻せません）",
        msgConnected: "✅ サーバーに接続しました",
        msgConnFailed: "❌ 接続失敗: ",
        msgForceSyncing: "🔄 強制同期中...",
        msgSyncDone: "✅ 同期が完了しました",
        msgSyncFailed: "❌ 同期失敗: ",
        msgCheckingOut: "🔀 切り替え中: ",
        msgCheckedOut: "✅ 切り替えました: ",
        msgCommitting: "📝 変更をコミット中...",
        msgCommitted: "✅ コミットしました: ",
        msgCommitFailed: "❌ コミット失敗: ",
        msgPushing: "⬆️ Push中...",
        msgPushDone: "✅ Push 完了",
        msgPushFailed: "❌ Push 失敗: ",
        msgPulling: "⬇️ Pull中...",
        msgPullDone: "✅ Pull 完了",
        msgPullFailed: "❌ Pull 失敗: ",
        cmdGitReset: "Git: リモートの状態にリセット",
        btnReset: "⚠️ リセット",
        msgResetting: "⚠️ リモートの状態にリセット中...",
        msgResetDone: "✅ リセット完了",
        msgResetFailed: "❌ リセット失敗: ",
        descReset: "ローカルの全ての変更を破棄し、リモートブランチと同じクリーンな状態に戻します（元に戻せません）",
        msgSettingsSaved: "✅ 設定を保存しました",
        msgSettingsFailed: "❌ 設定保存失敗: ",
        msgRefreshFailed: "❌ ステータス更新失敗: ",
        msgCheckoutFailed: "❌ 切り替え失敗: ",
        secServerConn: "🔌 サーバー接続",
        lblServerUrl: "Server URL",
        descServerUrl: "同期サーバーの URL",
        lblApiKey: "API Key",
        descApiKey: "サーバーの認証キー",
        lblConnStatus: "接続",
        valConnected: "✅ 接続済み",
        valNotConnected: "未接続",
        btnConnectLoad: "Connect & Load",
        boxStarting: "⏳ サーバー起動中...",
        boxPhase: "フェーズ: ",
        boxReconnecting: "3 秒後に自動で再接続します",
        boxStartupLog: "🪵 起動ログ (",
        secSyncStatus: "📊 同期ステータス",
        lblLastSync: "最終同期: ",
        valNotExecuted: "まだ実行されていません",
        lblMessage: "メッセージ: ",
        lblVaultReady: "Vault: ",
        valReady: "✅ 準備完了",
        valNotReady: "❌ 未準備",
        warnAuthMissing: "⚠️ Obsidian 認証未設定",
        warnAuthDesc: "setup-obsidian-auth.sh を実行して OBSIDIAN_AUTH_TOKEN を登録してください。",
        lblRefresh: "ステータス更新",
        descRefresh: "サーバーの最新状態を取得して表示を更新します",
        btnRefresh: "🔄 更新",
        lblForceSync: "Github Sync 強制実行",
        descForceSync: "今すぐサーバーで ob sync を実行します",
        secSyncSettings: "⚙️ Sync 設定",
        lblAutoSync: "自動同期の間隔（分）",
        descAutoSync: "サーバーが ob sync を実行する頻度",
        secGitOps: "🌿 Git 操作",
        valClean: "✅ 変更なし（クリーン）",
        lblFilesChanged: " ファイルに変更あり",
        lblCheckout: "ブランチ切り替え",
        descCheckout: "切り替え後は自動で git pull が実行されます",
        lblCommitPush: "コミット & Push",
        btnPush: "⬆️ Push",
        btnPull: "⬇️ Pull",
        lblCheckoutBranch: "🔀 ブランチ切り替え: ",
        checkoutConflictDesc: "未コミットの変更があります。どのように処理しますか？",
        lblCommitMsgOpt: "📝 コミット & Push のメッセージ（省略可）",
        descCommitMsgOpt: "空欄の場合は自動生成されます",
        placeholderCommitMsg: "コミットメッセージ...",
        btnForceSync: "強制同期",
        btnStash: "Stash",
        btnCommitPush: "コミット & Push",
        btnDiscard: "破棄して切り替え",
        valUnknown: "不明"
    }
};

function t(key: keyof typeof STRINGS.en): string {
    // Obsidian's setting language is stored in localStorage.
    // Use it as primary source, falling back to moment.locale() (system/app locale).
    const rawLang = window.localStorage.getItem('language') || moment.locale() || 'en';
    const lang = rawLang.toLowerCase().startsWith('ja') ? 'ja' : 'en';
    return STRINGS[lang]?.[key] || STRINGS.en[key];
}
// ─────────────────────────────────────────────────────────



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

        // 起動時に自動でサーバーに接続（バックグラウンドでテストするため、一旦通知ありに）
        this.app.workspace.onLayoutReady(() => {
            this.settingTab?.fetchAll();
        });

        // ─── コマンドパレット ─────────────────────────────

        this.addCommand({
            id: 'connect-server',
            name: t('cmdConnect'),
            callback: () => this.settingTab?.fetchAll(),
        });

        this.addCommand({
            id: 'refresh-status',
            name: t('cmdRefresh'),
            callback: () => this.settingTab?.refreshStatus(),
        });

        this.addCommand({
            id: 'force-sync',
            name: t('cmdForceSync'),
            callback: () => this.settingTab?.forceSync(),
        });

        this.addCommand({
            id: 'git-push',
            name: t('cmdGitPush'),
            callback: () => this.settingTab?.pushChanges(),
        });

        this.addCommand({
            id: 'git-pull',
            name: t('cmdGitPull'),
            callback: () => this.settingTab?.pullChanges(),
        });

        this.addCommand({
            id: 'git-reset',
            name: t('cmdGitReset'),
            callback: () => this.settingTab?.resetChanges(),
        });

        this.addCommand({
            id: 'git-commit',
            name: t('cmdGitCommit'),
            callback: () => {
                new GitSyncCommitModal(this.app, async (message) => {
                    if (!this.settingTab) return;
                    this.settingTab.commitMessage = message;
                    await this.settingTab.commitChanges();
                }).open();
            },
        });

        this.addCommand({
            id: 'git-checkout',
            name: t('cmdGitCheckout'),
            callback: async () => {
                const tab = this.settingTab;
                if (!tab?.gitBranches) {
                    new Notice(t('connectFirst'));
                    return;
                }
                new GitSyncBranchModal(this.app, tab.gitBranches.branches, tab.gitStatus?.branch ?? t('valUnknown'), async (branch) => {
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
class GitSyncCommitModal extends Modal {
    private onSubmit: (message: string) => void;
    private input = '';

    constructor(app: App, onSubmit: (message: string) => void) {
        super(app);
        this.onSubmit = onSubmit;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.createEl('h3', { text: t('cmdGitCommit') });

        new Setting(contentEl)
            .setName(t('commitMessageTitle'))
            .addText(text => text
                .setPlaceholder(t('commitMessagePlaceholder'))
                .onChange(v => { this.input = v; })
                .inputEl.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') this.submit();
                }));

        new Setting(contentEl)
            .addButton(btn => btn
                .setButtonText(t('btnCommit'))
                .setCta()
                .onClick(() => this.submit()))
            .addButton(btn => btn
                .setButtonText(t('btnCancel'))
                .onClick(() => this.close()));
    }

    private submit() {
        if (!this.input.trim()) {
            new Notice(t('commitEmpty'));
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
class GitSyncBranchModal extends SuggestModal<string> {
    private branches: string[];
    private currentBranch: string;
    private onChoose: (branch: string) => void;

    constructor(app: App, branches: string[], currentBranch: string, onChoose: (branch: string) => void) {
        super(app);
        this.branches = branches;
        this.currentBranch = currentBranch;
        this.onChoose = onChoose;
        this.setPlaceholder(`${t('strCurrentBranch')}${currentBranch}${t('strSelectBranch')}`);
    }

    getSuggestions(query: string): string[] {
        return this.branches.filter(b => b.toLowerCase().includes(query.toLowerCase()));
    }

    renderSuggestion(branch: string, el: HTMLElement) {
        if (branch === this.currentBranch) {
            el.createEl('div', { text: `🌿 ${branch}${t('strCurrent')}` });
            el.style.opacity = '0.5';
        } else {
            el.createEl('div', { text: `🌿 ${branch}` });
        }
    }

    onChooseSuggestion(branch: string) {
        // 現在のブランチと同じなら何もしない
        if (branch === this.currentBranch) return;
        this.onChoose(branch);
    }
}

/** ブランチ切り替え時の未コミット変更処理方法を選ぶモーダル */
class GitSyncCheckoutConflictModal extends Modal {
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
        contentEl.createEl('h3', { text: `${t('lblCheckoutBranch')}${this.branch}` });
        contentEl.createEl('p', {
            text: t('checkoutConflictDesc'),
        });

        // 変更ファイル一覧（折りたたみ）
        if (this.changedFiles.length > 0) {
            const details = contentEl.createEl('details');
            details.createEl('summary', { text: `${t('strChangedFiles')}${this.changedFiles.length}${t('strCountSuffix')}` });
            const ul = details.createEl('ul', { cls: 'git-changed-files' });
            this.changedFiles.forEach(f => ul.createEl('li', { text: f }));
        }

        contentEl.createEl('hr');

        // コミットメッセージ欄（commit_push 用）
        const commitMsgSetting = new Setting(contentEl)
            .setName(t('lblCommitMsgOpt'))
            .setDesc(t('descCommitMsgOpt'))
            .addText(text => text
                .setPlaceholder(t('placeholderCommitMsg'))
                .onChange(v => { this.commitMessage = v; }));

        // ── 3択ボタン ─────────────────────────────────────

        new Setting(contentEl)
            .setName(t('optStash'))
            .setDesc(t('optStashDesc'))
            .addButton(btn => btn
                .setButtonText(t('btnStash'))
                .setCta()
                .onClick(() => { this.close(); this.onChoose('stash'); }));

        new Setting(contentEl)
            .setName(t('optCommitPush'))
            .setDesc(t('optCommitPushDesc'))
            .addButton(btn => btn
                .setButtonText(t('btnCommitPush'))
                .onClick(() => { this.close(); this.onChoose('commit_push', this.commitMessage); }));

        new Setting(contentEl)
            .setName(t('optDiscard'))
            .setDesc(t('optDiscardDesc'))
            .addButton(btn => btn
                .setButtonText(t('btnDiscard'))
                .setWarning()
                .onClick(() => { this.close(); this.onChoose('discard'); }));

        new Setting(contentEl)
            .addButton(btn => btn
                .setButtonText(t('btnCancel'))
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

    async fetchAll(silent: boolean = false) {
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
            if (!silent) new Notice(t('msgConnected'));
        } catch (e: any) {
            if (e.isInitializing) {
                this.isInitializing = true;
                this.initPhase = e.phase;
                this.initLog = e.log;
                this.scheduleRetry();
            } else {
                if (!silent) new Notice(`${t('msgConnFailed')}${e.message}`);
                // エラー時は状態をクリア
                this.syncStatus = null;
                this.gitStatus = null;
                this.gitBranches = null;
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
                new Notice(`${t('msgRefreshFailed')}${e.message}`);
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
                new Notice(`${t('msgCheckingOut')}${branch}...`);
                const result = await this.apiPost<{ branch: string; note: string }>(
                    '/api/git/checkout',
                    { branch, mode, commit_message: commitMessage ?? '' }
                );
                const noteText = result.note ? ` (${result.note})` : '';
                new Notice(`${t('msgCheckedOut')}${branch}${noteText}`);
                await this.refreshStatus();
                // ブランチ切り替え後は強制同期も実行してiPhone等にすぐ反映させる
                await this.forceSync();
            };

            if (!hasDirty) {
                await doCheckout('stash');
            } else {
                new GitSyncCheckoutConflictModal(
                    this.app,
                    branch,
                    status.changed_files,
                    async (mode, commitMessage) => {
                        try {
                            await doCheckout(mode, commitMessage);
                        } catch (e: any) {
                            new Notice(`${t('msgCheckoutFailed')}${e.message}`);
                        }
                    }
                ).open();
            }
        } catch (e: any) {
            new Notice(`${t('msgCheckoutFailed')}${e.message}`);
        }
    }

    async commitChanges() {
        if (!this.commitMessage.trim()) {
            new Notice(t('commitEmpty'));
            return;
        }
        try {
            new Notice(t('msgCommitting'));
            await this.apiPost('/api/git/commit', { message: this.commitMessage });
            new Notice(t('msgCommitted'));
            this.commitMessage = '';
        } catch (e: any) {
            new Notice(`${t('msgCommitFailed')}${e.message}`);
        }
        await this.refreshStatus();
    }

    async pushChanges() {
        try {
            new Notice(t('msgPushing'));
            const result = await this.apiPost<{ branch: string }>('/api/git/push');
            new Notice(`${t('msgPushDone')} (${result.branch})`);
        } catch (e: any) {
            new Notice(`${t('msgPushFailed')}${e.message}`);
        }
        await this.refreshStatus();
    }

    async pullChanges() {
        try {
            new Notice(t('msgPulling'));
            const result = await this.apiPost<{ branch: string; output: string }>('/api/git/pull');
            new Notice(`${t('msgPullDone')} (${result.branch})`);
        } catch (e: any) {
            new Notice(`${t('msgPullFailed')}${e.message}`);
        }
        await this.refreshStatus();
    }

    async resetChanges() {
        try {
            new Notice(t('msgResetting'));
            const result = await this.apiPost<{ branch: string; output: string }>('/api/git/reset');
            new Notice(`${t('msgResetDone')} (${result.branch})`);
        } catch (e: any) {
            new Notice(`${t('msgResetFailed')}${e.message}`);
        }
        await this.refreshStatus();
    }

    async forceSync() {
        try {
            new Notice(t('msgForceSyncing'));
            await this.apiPost('/api/sync/force');
            new Notice(t('msgSyncDone'));
        } catch (e) {
            new Notice(`${t('msgSyncFailed')}${e.message}`);
        }
        await this.refreshStatus();
    }

    async updateRemoteSettings() {
        if (!this.remoteSettings) return;
        try {
            await this.apiPost('/api/settings', this.remoteSettings);
            new Notice(t('msgSettingsSaved'));
        } catch (e) {
            new Notice(`${t('msgSettingsFailed')}${e.message}`);
        }
    }

    // ─── UI 描画 ──────────────────────────────────────────

    async display(): Promise<void> {
        const { containerEl } = this;
        containerEl.empty();

        // ── 接続設定 ──────────────────────────────────────
        containerEl.createEl('h2', { text: t('secServerConn') });

        new Setting(containerEl)
            .setName(t('lblServerUrl'))
            .setDesc(t('descServerUrl'))
            .addText(text => text
                .setPlaceholder('http://localhost:8000')
                .setValue(this.plugin.settings.serverUrl)
                .onChange(async (value) => {
                    this.plugin.settings.serverUrl = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName(t('lblApiKey'))
            .setDesc(t('descApiKey'))
            .addText(text => text
                .setPlaceholder('default-secret-key')
                .setValue(this.plugin.settings.apiKey)
                .onChange(async (value) => {
                    this.plugin.settings.apiKey = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName(t('lblConnStatus'))
            .setDesc(this.remoteSettings ? `${t('valConnected')} (${t('strCurrentBranch')}${this.gitStatus?.branch ?? 'unknown'})` : t('valNotConnected'))
            .addButton(btn => btn
                .setButtonText(t('btnConnectLoad'))
                .setCta()
                .onClick(() => this.fetchAll()));

        // ─── コールドスタート待機中 ────────────────────────────
        if (this.isInitializing) {
            const box = containerEl.createEl('div', { cls: 'sync-initializing-box' });
            box.createEl('p', { text: t('boxStarting') });
            box.createEl('p', { text: `${t('boxPhase')}${this.initPhase}`, cls: 'sync-status-message' });
            box.createEl('p', { text: t('boxReconnecting'), cls: 'sync-status-message' });
            if (this.initLog.length > 0) {
                const details = box.createEl('details');
                details.createEl('summary', { text: `${t('boxStartupLog')}${this.initLog.length}${t('strCountSuffix')}` });
                details.createEl('pre', { cls: 'sync-startup-log', text: this.initLog.join('\n') });
            }
            new Setting(containerEl)
                .addButton(btn => btn
                    .setButtonText(t('btnCancel'))
                    .onClick(() => {
                        this.stopRetry();
                        this.isInitializing = false;
                        this.display();
                    }));
            return;
        }

        if (!this.remoteSettings) return;

        // ── Sync ステータス ────────────────────────────────
        containerEl.createEl('h2', { text: t('secSyncStatus') });

        if (this.syncStatus) {
            const s = this.syncStatus;
            const resultEmoji = s.last_sync_result === 'success' ? '✅'
                : s.last_sync_result === 'failed' ? '❌'
                : s.last_sync_result === 'skipped' ? '⏭️' : '—';
            const lastAt = s.last_sync_at
                ? new Date(s.last_sync_at).toLocaleString('ja-JP')
                : t('valNotExecuted');

            const info = containerEl.createEl('div', { cls: 'sync-status-info' });
            info.createEl('p', { text: `${resultEmoji} ${t('lblLastSync')}${lastAt}` });
            if (s.last_sync_message) {
                info.createEl('p', { text: `${t('lblMessage')}${s.last_sync_message}`, cls: 'sync-status-message' });
            }
            info.createEl('p', { text: `${t('lblVaultReady')} ${s.is_vault_ready ? t('valReady') : t('valNotReady')}` });

            // Obsidian 認証状態
            if (!s.ob_auth_configured) {
                const warn = info.createEl('div', { cls: 'sync-status-warning' });
                warn.createEl('p', { text: t('warnAuthMissing') });
                warn.createEl('p', { text: t('warnAuthDesc'), cls: 'sync-status-message' });
            }

            // スタートアップログ（折りたたみ）
            if (s.startup_log && s.startup_log.length > 0) {
                const details = info.createEl('details');
                details.createEl('summary', { text: `${t('boxStartupLog')}${s.startup_log.length}${t('strCountSuffix')}` });
                const pre = details.createEl('pre', { cls: 'sync-startup-log' });
                pre.setText(s.startup_log.join('\n'));
            }
        }

        new Setting(containerEl)
            .setName(t('cmdRefresh'))
            .setDesc(t('descRefresh'))
            .addButton(btn => btn
                .setButtonText(t('btnRefresh'))
                .onClick(() => this.refreshStatus()));

        new Setting(containerEl)
            .setName(t('lblForceSync'))
            .setDesc(t('descForceSync'))
            .addButton(btn => btn
                .setButtonText(t('btnForceSync'))
                .setWarning()
                .onClick(() => this.forceSync()));

        // ── Github Sync 設定 ────────────────────────────
        containerEl.createEl('h2', { text: t('secSyncSettings') });

        new Setting(containerEl)
            .setName(t('lblAutoSync'))
            .setDesc(t('descAutoSync'))
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
        containerEl.createEl('h2', { text: t('secGitOps') });

        if (this.gitStatus && this.gitBranches) {
            const gs = this.gitStatus;
            const gb = this.gitBranches;

            // ブランチ情報
            const branchInfo = containerEl.createEl('div', { cls: 'git-branch-info' });
            branchInfo.createEl('p', { text: `${t('strCurrentBranch')}${gs.branch}` });
            branchInfo.createEl('p', {
                text: gs.is_clean
                    ? t('valClean')
                    : `📝 ${gs.changed_files.length}${t('lblFilesChanged')}`,
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
                .setName(t('lblCheckout'))
                .setDesc(t('descCheckout'))
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
            containerEl.createEl('h3', { text: t('lblCommitPush') });

            new Setting(containerEl)
                .setName(t('commitMessageTitle'))
                .addText(text => text
                    .setPlaceholder(t('commitMessagePlaceholder'))
                    .setValue(this.commitMessage)
                    .onChange((value) => { this.commitMessage = value; }));

            new Setting(containerEl)
                .setName(t('secGitOps'))
                .addButton(btn => btn
                    .setButtonText(t('btnCommit'))
                    .onClick(() => this.commitChanges()))
                .addButton(btn => btn
                    .setButtonText(t('btnPush'))
                    .onClick(() => this.pushChanges()))
                .addButton(btn => btn
                    .setButtonText(t('btnPull'))
                    .onClick(() => this.pullChanges()));

            if (!gs.is_clean) {
                new Setting(containerEl)
                    .setName(t('cmdGitReset'))
                    .setDesc(t('descReset'))
                    .addButton(btn => btn
                        .setButtonText(t('btnReset'))
                        .setWarning()
                        .onClick(async () => {
                            await this.resetChanges();
                        }));
            }

            // 変更ファイル一覧（変更がある場合のみ）
            if (!gs.is_clean) {
                const changedEl = containerEl.createEl('details');
                changedEl.createEl('summary', { text: `${t('strChangedFiles')}${gs.changed_files.length})` });
                const ul = changedEl.createEl('ul', { cls: 'git-changed-files' });
                gs.changed_files.forEach(f => ul.createEl('li', { text: f }));
            }
        }
    }
}
