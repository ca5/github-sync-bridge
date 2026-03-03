# Obsidian 3-Way Sync システム

このリポジトリは、ObsidianのVaultを動的に同期するためのシステムです。FastAPIを使用したサーバーサイドアプリケーションと、Obsidianからサーバー設定を制御するための自作プラグインが含まれています。

システムの詳細な仕様については、[SPECIFICATION.md](./SPECIFICATION.md) を参照してください。

## サーバーのセットアップ (uv + requirements.txt)

サーバーはPythonの高速なパッケージマネージャーである `uv` を使用して依存関係を管理し、仮想環境を構築します。また同期の実行のために `obsidian-headless` (Node.js) を必要とします。

### 1. ツールのインストール

まだ `uv` と `pnpm` をインストールしていない場合は、以下のコマンド等でインストールします。

**uv のインストール:**
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**pnpm のインストール:**
```bash
npm install -g pnpm
```

### 2. 仮想環境の作成とパッケージのインストール (Python)

`server` ディレクトリに移動し、`requirements.txt` を用いて仮想環境 (`.venv`) を作成し、パッケージをインストールします。

```bash
cd server
uv venv
uv pip install -r requirements.txt
```

### 3. Obsidian Headlessのセットアップ (Node)

プロジェクトのルートディレクトリで `pnpm install` を実行し、同期コマンドとして必要な `obsidian-headless` をインストールします。

```bash
cd ..
pnpm install
```

### 4. サーバーの起動

仮想環境を有効化して、Uvicornでサーバーを起動します。
ローカルの `node_modules/.bin` にインストールされた `ob` コマンドが実行できるよう、PATHを通した状態で起動するのが確実です。

```bash
cd server

# 仮想環境の有効化 (macOS/Linuxの場合)
source .venv/bin/activate

# PATHにプロジェクトルートの node_modules を追加して起動
PATH="../node_modules/.bin:$PATH" uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

サーバーは `http://localhost:8000` で起動し、`http://localhost:8000/docs` からSwagger UI（APIドキュメント）にアクセスできます。

## Dockerを使用したサーバーのセットアップ

DockerおよびDocker Composeを使用して、設定ファイルを永続化（Volumeマウント）しつつサーバーを立ち上げることも可能です。

```bash
cd server
docker-compose up -d
```

## Obsidian プラグインのセットアップ

プラグインは `plugin` ディレクトリにあります。

### 1. 依存関係のインストールとビルド

このリポジトリは `pnpm` ワークスペースとして管理されています。ルートディレクトリで依存関係をインストールし、プラグインをビルドできます。

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
