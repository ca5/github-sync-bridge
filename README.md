# Obsidian 3-Way Sync システム

このリポジトリは、ObsidianのVaultを動的に同期するためのシステムです。FastAPIを使用したサーバーサイドアプリケーションと、Obsidianからサーバー設定を制御するための自作プラグインが含まれています。

システムの詳細な仕様については、[SPECIFICATION.md](./SPECIFICATION.md) を参照してください。

---

## 🚀 起動手順クイックリファレンス

### 初回のみ

```bash
# 1. 依存関係インストール
cd server && uv venv && uv pip install -r requirements.txt && cd ..
pnpm install

# 2. Obsidianアカウントにログイン
pnpm exec ob login

# 3. リモートVault名/IDを確認
pnpm exec ob sync-list-remote

# 4. vault/ を作成して同期設定（Obsidianアプリを閉じてから実行）
mkdir -p vault
pnpm exec ob sync-setup --vault <vault名またはID> --path ./vault

# 5. ノートをダウンロード（⚠️ サーバー起動前に必ず実行）
pnpm exec ob sync --path ./vault

# 6. ノートが入っていることを確認
ls vault/
```

### 2回目以降

```bash
cd server
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> APIドキュメント: http://localhost:8000/docs

---

## ⚠️ 重要: ob sync の注意事項

`ob sync` は**双方向同期**です。ローカルの `vault/` が空の状態で実行すると、**リモートのノートが全削除される危険があります。**

このため、サーバーには以下の安全チェックが組み込まれています：
- `vault/` が空または存在しない場合、自動同期を**実行しない**

**初回セットアップは必ず下記の手順通りに行ってください。**

---

## サーバーのセットアップ (初回)

### 1. ツールのインストール

まだ `uv` と `pnpm` をインストールしていない場合は、以下のコマンド等でインストールします。

**uv のインストール:**
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**pnpm のインストール:**
```bash
npm install -g pnpm
```

### 2. Python依存関係のインストール

`server` ディレクトリに移動し、仮想環境を作成してパッケージをインストールします。

```bash
cd server
uv venv
uv pip install -r requirements.txt
```

### 3. Node.js依存関係のインストール

プロジェクトのルートディレクトリで実行します。

```bash
cd ..   # プロジェクトルートへ
pnpm install
```

### 4. Obsidianアカウントへのログイン

```bash
pnpm exec ob login
```

### 5. リモートVaultの確認

```bash
pnpm exec ob sync-list-remote
# 例: f07b4604471f0341c0ea90e8fd86be27  "myvault"  (North America)
```

### 6. vault/ の初期化とノートのダウンロード

> **⚠️ 重要:** この手順を先に完了してからサーバーを起動してください。  
> サーバーを先に起動すると、空の `vault/` に対して sync が実行されリモートのノートが消える危険があります。

```bash
# vault/ ディレクトリを作成
mkdir -p vault

# 同期設定（Obsidianを閉じた状態で実行）
pnpm exec ob sync-setup --vault <vault名またはID> --path ./vault

# 初回ダウンロード（Obsidianを閉じた状態で実行）
pnpm exec ob sync --path ./vault
```

ダウンロードが完了したら、`vault/` にノートが入っていることを確認します。

```bash
ls vault/
```

### 7. サーバーの起動

`vault/` にノートが存在することを確認してから起動します。

```bash
cd server
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

サーバーは `http://localhost:8000` で起動し、`http://localhost:8000/docs` からSwagger UI（APIドキュメント）にアクセスできます。

---

## サーバーの2回目以降の起動

```bash
cd server
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **Note:** `vault/` に既にノートがあれば自動的に定期同期が動作します。

---

## Dockerを使用したセットアップ

DockerおよびDocker Composeを使用する場合も、**コンテナ起動前に手順6を完了してください。**

```bash
cd server
docker-compose up -d
```

---

## Obsidian プラグインのセットアップ

プラグインは `plugin` ディレクトリにあります。

### 1. 依存関係のインストール

```bash
pnpm install
```

### 2. ビルドして vault/ に配置（デスクトップ動作確認）

```bash
pnpm run deploy:plugin
```

`plugin/main.js` と `plugin/manifest.json` がビルドされ、
`vault/.obsidian/plugins/github-sync-bridge/` に自動コピーされます。

その後 Obsidian でそのVaultを開き、**設定 → コミュニティプラグイン** から有効化してください。

### 3. モバイルへ届ける（Obsidian Sync 経由）

```bash
pnpm run deploy:plugin:sync
```

上記コマンドは「ビルド → vault/ にコピー → ob sync でクラウドへ push」を一括実行します。
モバイルの Obsidian が次回起動 / 同期時にプラグインを受け取ります。

> **注意:** サーバーが ob sync を実行中の場合はロックエラーになることがあります。  
> その場合はサーバーを一時停止するか、少し待ってから再実行してください。

### 4. プラグインの設定

1. Obsidian の設定 → **github-sync-bridge** を開く
2. **Server URL** を入力（例: `http://10.16.125.9:8000`、モバイルの場合はMacのIPアドレス）
3. **API Key** を入力（デフォルト: `default-secret-key`）
4. **「Connect & Load」** をタップ

### スクリプト一覧

| コマンド | 内容 |
|---|---|
| `pnpm run build:plugin` | TypeScript をビルドするだけ |
| `pnpm run deploy:plugin` | ビルド + `vault/.obsidian/plugins/` にコピー |
| `pnpm run deploy:plugin:sync` | deploy:plugin + ob sync でモバイルへ配信 |

---

## テスト

```bash
cd server
source .venv/bin/activate
pytest tests/ -v
```
