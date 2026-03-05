# Google Cloud Run デプロイガイド

## 概要

このサーバーを Cloud Run 上で動かすための手順です。  
コンテナ起動時に `GITHUB_REPO_URL` で指定したリポジトリから vault を自動セットアップします。

---

## アーキテクチャ

```
[Cloud Run (コンテナ)]
  ├── FastAPI サーバー (port 8080)
  ├── バックグラウンドワーカー (ob sync 定期実行)
  └── /vault/  ← 起動時に GitHub から git clone

[Secret Manager]
  ├── obsidian-sync-api-key     → API_KEY
  └── obsidian-sync-git-ssh-key → SSH 秘密鍵 (GitHub アクセス用)
```

### Cloud Run での注意点

- **min-instances=1 必須**: バックグラウンドワーカーを常時稼働させるため
- **max-instances=1 必須**: `/vault/` はインスタンス間で共有されないため
- **vault は起動時にクローン**: コンテナ再起動ごとに GitHub から最新を取得
- **設定ファイル (`config.json`) は揮発**: デプロイ時に環境変数で初期値を設定推奨

---

## 事前準備

### 必要なツール

```bash
# Google Cloud SDK
brew install google-cloud-sdk

# ログイン
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### Artifact Registry リポジトリの作成

```bash
gcloud artifacts repositories create obsidian-sync \
  --repository-format=docker \
  --location=asia-northeast1 \
  --description="Obsidian Sync Server"
```

### GitHub SSH 鍵の準備

サーバーがリポジトリに `git push` できる権限を持つ SSH 鍵が必要です。

```bash
# 専用鍵ペアの生成（既存の鍵を使う場合はスキップ）
ssh-keygen -t ed25519 -C "obsidian-sync-cloud-run" -f ~/.ssh/obsidian_sync_deploy

# 公開鍵を GitHub リポジトリの Deploy Keys に登録（Read/Write アクセス）
cat ~/.ssh/obsidian_sync_deploy.pub
# → GitHub リポジトリ → Settings → Deploy keys → Add deploy key
```

---

## デプロイ手順

### ステップ 1: Secret Manager にシークレットを登録

```bash
cd path/to/obsidian-github-remote

# SSH 鍵のパスを指定して実行
SSH_KEY_PATH=~/.ssh/obsidian_sync_deploy bash deploy/cloud-run/setup-secrets.sh
```

### ステップ 2: Cloud Build でビルド & デプロイ

```bash
gcloud builds submit . \
  --config=deploy/cloud-run/cloudbuild.yaml \
  --substitutions=_GITHUB_REPO_URL=git@github.com:YOUR_USER/YOUR_REPO.git
```

> `_GITHUB_REPO_URL` は SSH 形式で指定してください（例: `git@github.com:ca5/obsidian.git`）

### ステップ 3: 動作確認

```bash
# サービス URL を取得
URL=$(gcloud run services describe obsidian-sync-server \
  --region=asia-northeast1 --format='value(status.url)')

# ヘルスチェック
curl -H "X-API-Key: YOUR_API_KEY" ${URL}/api/settings

# vault 初期化ステータス
curl -H "X-API-Key: YOUR_API_KEY" ${URL}/api/sync/status
```

---

## 環境変数一覧

| 変数名 | 設定方法 | 説明 |
|---|---|---|
| `API_KEY` | Secret Manager | API 認証キー |
| `GIT_SSH_KEY` | Secret Manager | SSH 秘密鍵の内容（PEM形式） |
| `GITHUB_REPO_URL` | Cloud Run env var | vault の GitHub リポジトリ（SSH形式） |
| `VAULT_DIR` | Cloud Run env var | vault のパス（デフォルト: `/vault`） |
| `OB_CMD` | Cloud Run env var | ob コマンドのパス |
| `CONFIG_FILE` | Cloud Run env var | 設定ファイルのパス |
| `GIT_USER_NAME` | Cloud Run env var | git コミット時のユーザー名（省略時: "Obsidian Sync Bot"） |
| `GIT_USER_EMAIL` | Cloud Run env var | git コミット時のメールアドレス |

---

## 初回起動の自動セットアップシーケンス

コンテナ起動時に以下が自動実行されます：

```
1. GIT_SSH_KEY 環境変数から SSH 鍵ファイルを /tmp/deploy_key に書き出す
2. GITHUB_REPO_URL が設定されている場合:
   a. vault/.git が存在しない → git clone GITHUB_REPO_URL VAULT_DIR
   b. vault/.git が存在する   → git pull（最新を取得）
3. 設定ファイル (config.json) が存在しない場合はデフォルトで作成
4. 残留ロックの解除
5. バックグラウンド ob sync ワーカーの起動
```

---

## 手動デプロイ（Cloud Build を使わない場合）

```bash
PROJECT_ID=$(gcloud config get-value project)
REGION=asia-northeast1
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/obsidian-sync/obsidian-sync-server:latest"

# ビルド
docker build -t "$IMAGE" .

# プッシュ
docker push "$IMAGE"

# デプロイ
gcloud run deploy obsidian-sync-server \
  --image="$IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=1 \
  --max-instances=1 \
  --memory=512Mi \
  --cpu=1 \
  --port=8080 \
  --set-env-vars="VAULT_DIR=/vault,OB_CMD=/app/node_modules/.bin/ob" \
  --set-env-vars="GITHUB_REPO_URL=git@github.com:YOUR_USER/YOUR_REPO.git" \
  --update-secrets="API_KEY=obsidian-sync-api-key:latest" \
  --update-secrets="GIT_SSH_KEY=obsidian-sync-git-ssh-key:latest"
```

---

## トラブルシューティング

### vault のクローンに失敗する

Cloud Run のログを確認：

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=obsidian-sync-server" \
  --limit=50 --format="value(textPayload)"
```

よくある原因：
- SSH 鍵の権限が GitHub Deploy Keys に設定されていない
- `GITHUB_REPO_URL` が HTTPS 形式になっている（SSH 形式 `git@github.com:...` で指定すること）

### config.json が起動ごとにリセットされる

Cloud Run はステートレスのため、コンテナ再起動で `/app/server/data/config.json` が消えます。  
設定の永続化には Cloud Storage Volume Mount または Cloud SQL の利用を検討してください（v0.0.3 以降の課題）。
