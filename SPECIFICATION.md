# Obsidian 3-Way Sync システム仕様書

## システム概要

iPhone / デスクトップの Obsidian ↔ **サーバー** ↔ GitHub を繋ぐ 3-Way Sync システム。

```
[iPhone]                           [Desktop]
  Obsidian アプリ                    Obsidian アプリ
       │                                  │
       │  Obsidian Sync (自動・双方向)    │  Obsidian Sync (自動・双方向)
       └──────────────┬───────────────────┘
                      ▼
                  [サーバー]
                   vault/          ← ob sync で Obsidian Sync クラウドと同期
                   .git/           ← git で GitHub と同期
                      │
          ┌───────────┴───────────┐
          │ モバイルから           │ デスクトップから
          │ プラグイン/API 経由    │ git コマンドを直接実行
          ▼                       ▼
       [GitHub]               [GitHub]
```

### 操作主体とアクセス方法

| 操作 | モバイル（iPhone） | デスクトップ |
|---|---|---|
| ノートの作成・編集 | Obsidian アプリ | Obsidian アプリ or エディタ |
| Obsidian Sync | 自動（Obsidian Sync） | 自動（Obsidian Sync） |
| ブランチ切り替え | **サーバーAPI / プラグイン UI** | `git checkout` を直接実行 |
| コミット & Push | **サーバーAPI / プラグイン UI** | `git commit && git push` を直接実行 |
| Pull | **サーバーAPI / プラグイン UI** | `git pull` を直接実行 |

> **設計方針**: サーバーの Git API はモバイルから git 操作を行うための橋渡しが主目的。  
> デスクトップでは git コマンドを直接使えばよく、サーバーの Git API を使う必要はない。

### 3つのレイヤー

| レイヤー | 役割 | 同期方法 | タイミング |
|---|---|---|---|
| Obsidian Sync | iPhone/Desktop ↔ vault/ | `ob sync` | 自動（定期） |
| Git | vault/ ↔ GitHub | `git commit` / `git push` / `git pull` | **手動トリガー** |
| ブランチ切り替え | vault/ の内容切り替え | `git checkout` | **手動トリガー** |

---

## ユースケース別フロー

### 1. モバイルで新しいメモを追加した時

```
iPhone Obsidian → [Obsidian Sync 自動] → vault/ → (必要なら手動) → git commit + push → GitHub
```

1. iPhone の Obsidian でメモを作成
2. Obsidian Sync が自動でサーバーの `vault/` に反映（`ob sync` 定期実行）
3. （任意）プラグインの「Commit & Push」ボタンでメモを GitHub にも保存

---

### 2. 外部ツールで更新したブランチをデスクトップで続ける時

```
GitHub (外部で更新済み) → [ブランチ切り替え] → vault/ → [Obsidian Sync 自動] → Desktop Obsidian
```

1. Web管理画面 or プラグインからブランチを選択（`git checkout <branch>`）
2. `vault/` の内容が切り替わる
3. Obsidian Sync がサーバーの `vault/` をクラウドへ push
4. デスクトップ Obsidian が Obsidian Sync からファイルを pull → 作業開始

---

### 3. 外部ツールで更新したブランチをモバイルで続ける時

```
GitHub (外部で更新済み) → [ブランチ切り替え] → vault/ → [Obsidian Sync 自動] → iPhone Obsidian
```

フロー は ユースケース2 と同じ。最終的な受け取り先が iPhone になる。

---

### 4. デスクトップで作ったドキュメントをモバイルで修正する時

```
Desktop Obsidian → [Obsidian Sync 自動] → vault/ → [Obsidian Sync 自動] → iPhone Obsidian
```

1. デスクトップの Obsidian でドキュメントを作成・編集
2. Obsidian Sync が自動でサーバーの `vault/` に同期
3. `ob sync` がクラウドに反映
4. iPhone の Obsidian が Obsidian Sync からファイルを受け取る → 修正開始

---

### 5. モバイルで作ったメモをデスクトップで修正する時

```
iPhone Obsidian → [Obsidian Sync 自動] → vault/ → [Obsidian Sync 自動] → Desktop Obsidian
```

フローは ユースケース4 の逆方向。

---

## API 仕様

### 既存エンドポイント

| エンドポイント | メソッド | 説明 |
|---|---|---|
| `/api/settings` | GET | サーバー設定を取得 |
| `/api/settings` | POST | サーバー設定を更新 |
| `/api/sync/force` | POST | Obsidian Sync を強制実行 |
| `/api/sync/status` | GET | 最終 sync 時刻・結果・Vault 状態 |

### 追加予定：Git 操作エンドポイント

| エンドポイント | メソッド | 説明 |
|---|---|---|
| `/api/git/status` | GET | 現在のブランチ・変更ファイル一覧 |
| `/api/git/branches` | GET | ブランチ一覧（local + remote） |
| `/api/git/checkout` | POST | ブランチの切り替え |
| `/api/git/commit` | POST | 変更をコミット（コミットメッセージを受け取る） |
| `/api/git/push` | POST | リモートへ push |
| `/api/git/pull` | POST | リモートから pull |

---

## サーバー設定項目

### 既存

| 項目 | 型 | 説明 |
|---|---|---|
| `sync_obsidian_config` | bool | `.obsidian` フォルダを同期対象に含めるか |
| `auto_sync_interval` | int | Obsidian Sync の自動実行サイクル（分） |
| `github_branch_patterns` | array | 表示・操作を許可するブランチのパターン |

### 追加予定（環境変数で設定）

| 環境変数 | 説明 |
|---|---|
| `GITHUB_REPO_URL` | SSH形式のリポジトリURL（例: `git@github.com:user/notes.git`） |
| `GIT_SSH_KEY_PATH` | SSH秘密鍵のパス（デフォルト: `~/.ssh/id_rsa`） |
| `VAULT_DIR` | vault のローカルパス |
| `API_KEY` | API認証キー |
| `OB_CMD` | ob コマンドの絶対パス |

---

## プラグイン（Obsidian Sync Bridge）設定画面

### 既存 UI

- **Server URL** / **API Key** / **Connect & Load** ボタン
- **Sync .obsidian folder** トグル
- **Sync Interval** 数値入力
- **Force Full Sync** ボタン（Obsidian Sync 向け）

### 追加予定 UI

- **Sync Status** セクション：最終 sync 時刻・成功/失敗表示
- **Git** セクション：
  - 現在のブランチ表示
  - ブランチ切り替えドロップダウン（`github_branch_patterns` でフィルタ）
  - コミットメッセージ入力 + **Commit** ボタン
  - **Push** ボタン
  - **Pull** ボタン

---

## Web 管理画面（ブラウザ向け）

Obsidian を開いていない状態でもブラウザからサーバーを操作できる画面。
プラグインと同じ API を利用する。

- 現在の同期ステータス表示
- git ステータス表示（現在のブランチ・変更ファイル数）
- ブランチ切り替え
- Commit & Push 操作
- Force Sync（Obsidian Sync 向け）

---

## 技術的な注意事項

### GitHub SSH 認証

- SSH 秘密鍵を `GIT_SSH_KEY_PATH` 環境変数で指定
- `git` コマンド実行時に `GIT_SSH_COMMAND` を設定して使用

### ブランチ切り替え時の注意

- `git checkout` 前に未コミットの変更がある場合はエラーを返す（自動コミットはしない）
- 切り替え後、Obsidian Sync が次のサイクルで自動的に新しい内容をクラウドに反映する

### git と Obsidian Sync の競合について

- `ob sync` と `git` 操作は同時に実行しない（ロック機構が必要）
- `git checkout` 中は `ob sync` をスキップする
