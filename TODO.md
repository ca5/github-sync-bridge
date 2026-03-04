# 実装チェックリスト

最終更新: 2026-03-04

---

## ✅ サーバー（FastAPI）― Obsidian Sync 系

- [x] `GET /api/settings` — 設定取得
- [x] `POST /api/settings` — 設定更新
- [x] `POST /api/sync/force` — Obsidian Sync 強制実行
- [x] `GET /api/sync/status` — 最終 sync 時刻・結果・Vault 状態
- [x] `config.json` による設定の永続化
- [x] API Key 認証
- [x] `ob sync-config` による `.obsidian` 同期の動的切り替え
- [x] バックグラウンドワーカー（定期自動 ob sync）
- [x] `auto_sync_interval` の反映
- [x] `ob` コマンドの絶対パス解決（PATH 非依存）
- [x] 空 Vault に対する sync をブロックする安全チェック
- [x] `.sync.lock` の自動解放（起動時・各 sync 前）
- [x] sync 結果（成功/失敗/スキップ）を `_sync_status` に記録

---

## ❌ サーバー（FastAPI）― Git API 系

> **前提作業**: `vault/` を git リポジトリとして初期化する必要がある

- [x] **[前提] `vault/` を git init またはリモートから clone する**
      - `git@github.com:ca5/obsidian.git` を origin として設定
      - `main` ブランチでトラッキング開始
- [ ] `GET /api/git/status` — 現在のブランチ・変更ファイル一覧
- [ ] `GET /api/git/branches` — ブランチ一覧（local + remote）
- [ ] `POST /api/git/checkout` — ブランチ切り替え + git pull（未コミット変更があればエラー）
- [ ] `POST /api/git/commit` — コミット（コミットメッセージを本文で受け取る）
- [ ] `POST /api/git/push` — リモートへ push（SSH 認証）
- [ ] `POST /api/git/pull` — リモートから pull
- [ ] SSH 認証設定（`GIT_SSH_COMMAND` 環境変数経由）
- [ ] ob sync 実行中の git 操作をブロックするロック制御

---

## ✅ Obsidian プラグイン（TypeScript）― 既存

- [x] Server URL 設定
- [x] API Key 設定
- [x] Connect & Load ボタン（サーバーから設定取得）
- [x] Sync .obsidian folder トグル（変更時にサーバーへ即時反映）
- [x] Sync Interval 数値入力（変更時にサーバーへ即時反映）
- [x] Force Full Sync ボタン

---

## ❌ Obsidian プラグイン（TypeScript）― 追加予定

### 同期ステータス表示
- [ ] 最終 sync 時刻・成功/失敗の表示（`GET /api/sync/status` を利用）
- [ ] サーバー接続状態インジケーター

### Git 操作 UI（モバイルからサーバーを操作）
- [ ] 現在のブランチ表示
- [ ] ブランチ切り替えドロップダウン（`github_branch_patterns` でフィルタ）
- [ ] コミットメッセージ入力 + **Commit** ボタン
- [ ] **Push** ボタン
- [ ] **Pull** ボタン

---

## ❌ Web 管理画面（ブラウザ向け UI）

> 仕様 §Web管理画面 に記載。プラグインと同じ API を使用。

- [ ] 管理画面の HTML/CSS/JS 実装（`server/static/` に配置）
- [ ] 現在の Obsidian Sync ステータス表示
- [ ] git ステータス（ブランチ・未コミット変更数）表示
- [ ] ブランチ切り替え UI
- [ ] Commit & Push 操作 UI
- [ ] Force Sync ボタン

---

## ❌ インフラ・運用

- [ ] Docker / docker-compose 動作確認
- [ ] `server/data/` の Volume マウント確認（コンテナ再起動後も設定が消えないこと）
- [ ] `OBSIDIAN_AUTH_TOKEN` 環境変数対応（非対話環境での ob login 代替）
- [ ] ログの永続化

---

## ❌ テスト追加

- [ ] `GET /api/sync/status` のテスト
- [ ] `check_vault_safety` / `clear_sync_lock` のユニットテスト
- [ ] Git API エンドポイントのテスト（subprocess をモック）

---

## 📋 実装優先順位

1. **[前提] `vault/` を git リポジトリとして初期化**
2. **サーバー Git API 実装**（status → branches → checkout → commit → push → pull の順）
3. **プラグイン: 同期ステータス表示**
4. **プラグイン: Git 操作 UI**
5. **Web 管理画面**
6. **インフラ（Docker）**
7. **テスト追加**
