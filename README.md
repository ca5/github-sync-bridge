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

### 1. 依存関係のインストールとビルド

```bash
# プロジェクトのルートディレクトリで実行
pnpm install
pnpm run build:plugin
```

### 2. Obsidianへのインストール

1. `plugin` ディレクトリ内にある以下のファイルを、ObsidianのVault内の `.obsidian/plugins/obsidian-sync-bridge/` ディレクトリにコピーします。
   * `main.js` (ビルドされたファイル)
   * `manifest.json`
2. Obsidianの設定 > コミュニティプラグイン から「セーフモード」をオフにし、インストールしたプラグインを有効化します。
3. プラグインの設定画面を開き、Server URL (`http://localhost:8000` など) と API Key (`default-secret-key`) を入力して「Connect & Load」をクリックします。

---

## テスト

```bash
cd server
source .venv/bin/activate
pytest tests/ -v
```
