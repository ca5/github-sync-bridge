# Obsidian 3-Way Sync システム

このリポジトリは、ObsidianのVaultを動的に同期するためのシステムです。FastAPIを使用したサーバーサイドアプリケーションと、Obsidianからサーバー設定を制御するための自作プラグインが含まれています。

システムの詳細な仕様については、[SPECIFICATION.md](./SPECIFICATION.md) を参照してください。

## サーバーのセットアップ (uv + requirements.txt)

サーバーはPythonの高速なパッケージマネージャーである `uv` を使用して依存関係を管理し、仮想環境を構築します。

### 1. uv のインストール

まだ `uv` をインストールしていない場合は、以下のコマンドでインストールします。

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. 仮想環境の作成とパッケージのインストール

`server` ディレクトリに移動し、`requirements.txt` を用いて仮想環境 (`.venv`) を作成し、パッケージをインストールします。

```bash
cd server
uv venv
uv pip install -r requirements.txt
```

### 3. サーバーの起動

仮想環境を有効化して、Uvicornでサーバーを起動します。

```bash
# 仮想環境の有効化 (macOS/Linuxの場合)
source .venv/bin/activate

# 仮想環境の有効化 (Windowsの場合)
# .venv\Scripts\activate

# サーバーの起動
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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

Node.js (npm) を使用してプラグインをビルドします。

```bash
cd plugin
npm install
npm run build
```

### 2. Obsidianへのインストール

1. `plugin` ディレクトリ内にある以下のファイルを、ObsidianのVault内の `.obsidian/plugins/obsidian-sync-plugin/` ディレクトリにコピーします。
   * `main.js` (ビルドされたファイル)
   * `manifest.json`
2. Obsidianの設定 > コミュニティプラグイン から「セーフモード」をオフにし、インストールしたプラグインを有効化します。
3. プラグインの設定画面を開き、Server URL (`http://localhost:8000` など) と API Key (`default-secret-key`) を入力して「Connect & Load」をクリックします。
