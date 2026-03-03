# Obsidian 3-Way Sync システム仕様書

## システム概要

iPhone / デスクトップの Obsidian ↔ **サーバー** ↔ GitHub を繋ぐ 3-Way Sync システム。

```
[iPhone]                           [Desktop]
  Obsidian アプリ                    Obsidian アプリ / エディタ
       │                                  │
       │ Obsidian Sync (自動・双方向)     │ Obsidian Sync (自動・双方向)
       └──────────────┬───────────────────┘
                      ▼
                  [サーバー]
                   vault/    ←→  ob sync  ←→  Obsidian Sync クラウド
                   .git/     ←→  git API  ←→  GitHub
                                    ↑
                    ┌───────────────┤
                    │ モバイルから   │ デスクトップから
                    │ プラグイン経由 │ git コマンド直接 or プラグイン経由
                    └───────────────┘
```

### 操作主体とアクセス方法

| 操作 | モバイル（iPhone） | デスクトップ |
|---|---|---|
| ノートの作成・編集 | Obsidian アプリ | Obsidian アプリ or エディタ |
| Obsidian Sync | 自動（Obsidian Sync） | 自動（Obsidian Sync） |
| コミット & Push | **プラグイン → サーバーGit API** | `git` 直接 or サーバーGit API |
| ブランチ切り替え | **プラグイン → サーバーGit API** | `git checkout` 直接 |
| Pull | **プラグイン → サーバーGit API** | `git pull` 直接 |

> **サーバーの Git API はモバイルが主な利用者。**
> デスクトップは git コマンドを直接実行できるため、サーバーを経由する必要はない（するのも可）。

---

## ユースケース別フロー

### 1. モバイルで新しいメモを追加した時

```
iPhone で編集
    ↓ Obsidian Sync（自動）
vault/ に反映
    ↓ プラグインから「Commit & Push」ボタンをタップ（手動）
git commit + git push
    ↓
GitHub に保存
```

### 2. 外部ツールで更新したブランチをデスクトップで続ける時

```
GitHub に外部ブランチが存在
    ↓ デスクトップで git checkout <branch> + git pull（直接）
vault/ の内容が切り替わる
    ↓ ob sync（自動）で Obsidian Sync クラウドに反映
    ↓ Desktop Obsidian が受け取る
デスクトップで作業開始
```

### 3. 外部ツールで更新したブランチをモバイルで続ける時

```
GitHub に外部ブランチが存在
    ↓ デスクトップで git checkout <branch> + git pull（直接）
   または
    ↓ プラグイン → サーバーGit API で checkout + pull（手動）
vault/ の内容が切り替わる
    ↓ ob sync（自動）で Obsidian Sync クラウドに反映
    ↓ iPhone Obsidian が受け取る
モバイルで作業開始
```

### 4. デスクトップで作ったドキュメントをモバイルで修正する時

```
Desktop Obsidian で編集
    ↓ Obsidian Sync（自動）
vault/ に反映 → ob sync でクラウドへ
    ↓ iPhone Obsidian が受け取る
iPhone で修正
```

### 5. モバイルで作ったメモをデスクトップで修正する時

```
iPhone Obsidian で編集
    ↓ Obsidian Sync（自動）
vault/ に反映 → ob sync でクラウドへ
    ↓ Desktop Obsidian が受け取る
デスクトップで修正
```

---

## API 仕様

### Obsidian Sync 系（実装済み）

| エンドポイント | メソッド | 説明 |
|---|---|---|
| `/api/settings` | GET | サーバー設定を取得 |
| `/api/settings` | POST | サーバー設定を更新 |
| `/api/sync/force` | POST | Obsidian Sync を強制実行 |
| `/api/sync/status` | GET | 最終 sync 時刻・結果・Vault 状態 |

### Git 操作系（追加予定）

| エンドポイント | メソッド | 説明 |
|---|---|---|
| `/api/git/status` | GET | 現在のブランチ・変更ファイル一覧 |
| `/api/git/branches` | GET | ブランチ一覧（local + remote） |
| `/api/git/checkout` | POST | ブランチ切り替え（未コミット変更があればエラー） |
| `/api/git/commit` | POST | 変更をコミット（コミットメッセージを指定） |
| `/api/git/push` | POST | リモートへ push |
| `/api/git/pull` | POST | リモートから pull |

---

## サーバー設定項目

### config.json（API 経由で変更可能）

| 項目 | 型 | 説明 |
|---|---|---|
| `sync_obsidian_config` | bool | `.obsidian` フォルダを同期対象に含めるか |
| `auto_sync_interval` | int | Obsidian Sync の自動実行サイクル（分） |
| `github_branch_patterns` | array | プラグインに表示するブランチのフィルタパターン |

### 環境変数

| 環境変数 | 必須 | 説明 |
|---|---|---|
| `VAULT_DIR` | - | vault のローカルパス（デフォルト: `../vault`） |
| `API_KEY` | - | API 認証キー（デフォルト: `default-secret-key`） |
| `OB_CMD` | - | ob コマンドの絶対パス |
| `GITHUB_REPO_URL` | Git API 使用時 | SSH 形式のリポジトリ URL（例: `git@github.com:user/notes.git`） |
| `GIT_SSH_KEY_PATH` | Git API 使用時 | SSH 秘密鍵のパス（デフォルト: `~/.ssh/id_rsa`） |

---

## プラグイン（Obsidian Sync Bridge）設定画面

### 既存 UI（実装済み）

- **Server URL** / **API Key** / **Connect & Load** ボタン
- **Sync .obsidian folder** トグル
- **Sync Interval** 数値入力
- **Force Full Sync** ボタン

### 追加予定 UI

- **Sync Status** セクション：最終 sync 時刻・成功/失敗表示
- **Git** セクション（主にモバイルでの利用を想定）：
  - 現在のブランチ表示
  - ブランチ切り替えドロップダウン（`github_branch_patterns` でフィルタ）
  - コミットメッセージ入力 + **Commit** ボタン
  - **Push** ボタン
  - **Pull** ボタン

---

## Web 管理画面（ブラウザ向け）

Obsidian を開いていない状態でもブラウザからサーバーを操作できる画面。
プラグインと同じ API を使用。

- 現在の Obsidian Sync ステータス
- git ステータス（現在のブランチ・未コミット変更数）
- ブランチ切り替え・Commit & Push 操作
- Force Sync ボタン

---

## 技術的な注意事項

### GitHub SSH 認証

- SSH 秘密鍵を `GIT_SSH_KEY_PATH` で指定
- `git` コマンド実行時に環境変数 `GIT_SSH_COMMAND` を設定して使用

### ブランチ切り替え時のルール

- `git checkout` 前に未コミットの変更がある場合は**エラーを返す**（自動コミットはしない）
- 切り替え後、Obsidian Sync が次のサイクルで自動的に新しい内容をクラウドに反映する

### ob sync と git の競合防止

- `ob sync` 実行中に git 操作が行われないようにロック制御が必要（今後実装）
