# 実装チェックリスト

## ✅ サーバー（FastAPI）

### 設定 API
- [x] `GET /api/settings` - 設定取得
- [x] `POST /api/settings` - 設定更新
- [x] `POST /api/sync/force` - 強制同期実行
- [x] `config.json` による設定の永続化
- [x] API Key 認証

### 同期ロジック
- [x] `ob sync-config` による `.obsidian` 同期の動的切り替え
- [x] バックグラウンドワーカー（定期自動同期）
- [x] `auto_sync_interval` の反映
- [x] `ob` コマンドの絶対パス解決（PATH依存なし）
- [ ] `ob sync --continuous` を使った継続的同期（現状は毎回 `ob sync` を起動）
- [ ] `OBSIDIAN_AUTH_TOKEN` 環境変数による非対話的認証（Docker運用に不可欠）
- [ ] `OBSIDIAN_E2E_PASSWORD` 環境変数対応（E2E暗号化Vault対応）
- [ ] `github_branch_patterns` の実際の利用（フィールド定義はあるが未使用）

---

## ❌ GitHub連携（**3-Way Syncの3本目**、サーバーGit API）

> モバイルは git を直接触れないため、サーバーの Git API 経由で操作する。
> デスクトップは `git` コマンドを直接使うため、サーバーGit APIは不要（任意で使用可）。
>
> **確定済み方針:**
> - コミット・Push は **手動トリガー**（プラグインのボタン）
> - SSH 鍵認証（`GIT_SSH_KEY_PATH` 環境変数）
> - リポジトリは `GITHUB_REPO_URL` 環境変数で指定
> - 未コミット変更がある状態でのブランチ切り替えは **エラーを返す**

### サーバーGit APIエンドポイント
- [ ] `GET /api/git/status` - 現在のブランチ・変更ファイル一覧
- [ ] `GET /api/git/branches` - ブランチ一覧（local + remote）
- [ ] `POST /api/git/checkout` - ブランチ切り替え（未コミット変更があればエラー）
- [ ] `POST /api/git/commit` - コミット（コミットメッセージを指定）
- [ ] `POST /api/git/push` - リモートへ push（SSH認証）
- [ ] `POST /api/git/pull` - リモートから pull

### プラグイン Git UI（モバイル向け）
- [ ] 現在のブランチ表示
- [ ] ブランチ切り替えドロップダウン（`github_branch_patterns` でフィルタ）
- [ ] コミットメッセージ入力 + **Commit** ボタン
- [ ] **Push** / **Pull** ボタン

### 安全対策（仕様外で追加）
- [x] 空Vaultに対するsyncをブロックする安全チェック
- [x] sync.lock の自動解放（起動時・各sync前）

### テスト
- [x] pytest によるAPIテスト（7ケース）
- [ ] sync_worker のテスト
- [ ] check_vault_safety / clear_sync_lock のユニットテスト

---

## ✅ Obsidianプラグイン（TypeScript）

- [x] Server URL 設定
- [x] API Key 設定
- [x] Connect & Load ボタン（サーバーから設定取得）
- [x] Sync .obsidian folder トグル（変更時にサーバーへ即時反映）
- [x] Sync Interval 数値入力（変更時にサーバーへ即時反映）
- [x] Force Full Sync ボタン
- [ ] 同期ステータスの表示（最終sync時刻、成功/失敗）
- [ ] サーバーへの接続状態インジケーター（常時表示）

---

## ❌ Web管理画面（仕様 §4 に記載）

> ブラウザから同期ステータスを確認・操作するためのUI

- [ ] 管理画面のHTML/CSS/JS実装
- [ ] 現在の同期ステータス表示
- [ ] 設定の読み書きUI
- [ ] Force Sync ボタン

---

## ❌ インフラ・運用

- [ ] Docker / docker-compose による本番運用の検証
- [ ] `server/data/` の Volume マウント確認
- [x] `/api/sync/status` エンドポイント（ステータス取得API）
- [ ] ログの永続化

---

## 📋 実装優先順位（提案）

1. ~~**`/api/sync/status` エンドポイント**~~ ✅ 完了
2. **GitHub連携（git pull/push）**（← 3-Way Syncの柱なのに完全未実装）
3. **`OBSIDIAN_AUTH_TOKEN` 対応**（Dockerで動かすのに必須）
4. **Web管理画面**（仕様 §4）
5. **プラグインのステータス表示**
6. **`ob sync --continuous` への移行**
7. **追加テスト**
