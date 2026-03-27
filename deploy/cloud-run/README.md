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
  ├── obsidian-sync-git-ssh-key → SSH 秘密鍵 (GitHub アクセス用)
  └── obsidian-sync-auth-token  → OBSIDIAN_AUTH_TOKEN (Obsidian Sync 認証)
```

### Cloud Run での注意点

- **min-instances=1 必須**: バックグラウンドワーカーを常時稼働させるため
- **max-instances=1 必須**: `/vault/` はインスタンス間で共有されないため
- **vault は起動時にクローン**: コンテナ再起動ごとに GitHub から最新を取得
- **設定ファイル (`config.json`) は揮発**: デプロイ時に環境変数で初期値を設定推奨

---

## 事前準備（初回のみ）

### ①  必要なツール

```bash
# Google Cloud SDK
brew install google-cloud-sdk

# ログイン & プロジェクト設定
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### ② GitHub SSH 鍵の準備

サーバーがリポジトリに `git push` できる SSH 鍵が必要です。

```bash
# 専用鍵ペアの生成（既存の鍵を使う場合はスキップ）
ssh-keygen -t ed25519 -C "obsidian-sync-cloud-run" -f ~/.ssh/obsidian_sync_deploy

# 公開鍵を GitHub リポジトリの Deploy Keys に登録（Read/Write アクセス）
cat ~/.ssh/obsidian_sync_deploy.pub
# → GitHub リポジトリ → Settings → Deploy keys → Add deploy key
```

### ③  GCP シークレット（API Key・SSH 鍵）を登録

```bash
SSH_KEY_PATH=~/.ssh/obsidian_sync_deploy \
  bash deploy/cloud-run/setup-secrets.sh
```

### ④  Obsidian Sync 認証トークンを取得・登録

Obsidian Sync を Cloud Run で使うには、ローカルで `ob login` を実行してトークンを取得し、Secret Manager に登録する必要があります。

```bash
bash deploy/cloud-run/setup-obsidian-auth.sh
```

このスクリプトが行うこと：
1. `ob login` をインタラクティブに実行（メールアドレス・パスワード・MFA を入力）
2. `~/.obsidian-headless/auth_token` からトークンを取得
3. Secret Manager の `obsidian-sync-auth-token` に登録
4. `ob sync-list-remote` で Vault ID を表示（次のステップで使用）

> ⚠️ `ob logout` を実行するとトークンが無効になります。その場合はこのスクリプトを再実行してください。

---

## デプロイ手順（スクリプト一発）

```bash
GITHUB_REPO_URL=git@github.com:YOUR_USER/YOUR_REPO.git \
OBSIDIAN_VAULT_ID=<setup-obsidian-auth.sh で表示された Vault ID> \
  bash deploy/cloud-run/deploy.sh
```

以上です。次のような出力とともに Service URL が表示されます：

```
========================================
 ✅ デプロイ完了!

 Service URL: https://obsidian-sync-server-xxx.run.app
 API Docs:    https://obsidian-sync-server-xxx.run.app/docs
========================================
```

### 動作確認

```bash
URL=https://obsidian-sync-server-xxx.run.app  # 上記 URL に置き換え

# ヘルスチェック
curl -H "X-API-Key: YOUR_API_KEY" $URL/api/sync/status

# Git ステータス確認（vault が clone されているか）
curl -H "X-API-Key: YOUR_API_KEY" $URL/api/git/status
```

---

## deploy.sh が行っていること

```
Step 1/4  Artifact Registry の認証設定（リポジトリがなければ自動作成）
Step 2/4  docker build --platform linux/amd64 でイメージをビルド
Step 3/4  Artifact Registry へ push
Step 4/4  Cloud Run へデプロイ（Secret は Secret Manager から自動注入）
```

---

## 環境変数・シークレット一覧

| 変数名 | 設定方法 | 説明 |
|---|---|---|
| `API_KEY` | **Secret Manager** (`obsidian-sync-api-key`) | API 認証キー |
| `GIT_SSH_KEY` | **Secret Manager** (`obsidian-sync-git-ssh-key`) | SSH 秘密鍵の内容（PEM 形式） |
| `OBSIDIAN_AUTH_TOKEN` | **Secret Manager** (`obsidian-sync-auth-token`) | Obsidian Sync 認証トークン |
| `GITHUB_REPO_URL` | deploy.sh の引数 | vault の GitHub リポジトリ (SSH 形式) |
| `OBSIDIAN_VAULT_ID` | deploy.sh の引数 | Obsidian Sync の Vault ID |
| `VAULT_DIR` | deploy.sh 内に設定 | vault のパス（デフォルト: `/vault`） |
| `OB_CMD` | deploy.sh 内に設定 | ob コマンドのパス |
| `GIT_USER_NAME` | 必要に応じて追加 | git コミット時のユーザー名 |
| `GIT_USER_EMAIL` | 必要に応じて追加 | git コミット時のメールアドレス |
| `GCS_BUCKET_NAME` | deploy.sh の引数 | (必須) Cloud Runがゼロスケールする際にデータを退避させる先のGCSバケット名 |

### deploy.sh の設定項目（変更する場合）

```bash
# deploy/cloud-run/deploy.sh の先頭部分
PROJECT_ID="your-gcp-project"     # GCP プロジェクト ID
REGION="asia-northeast1"           # リージョン（東京）
SERVICE_NAME="obsidian-sync-server"
REPO="obsidian-sync"               # Artifact Registry リポジトリ名
```

---

## 起動時の自動セットアップシーケンス

コンテナ起動時に以下が自動実行されます：

```
1. GIT_SSH_KEY 環境変数から SSH 鍵ファイルを /tmp/ に書き出す
2. OBSIDIAN_AUTH_TOKEN 環境変数から ~/.obsidian-headless/auth_token に書き出す
3. GITHUB_REPO_URL が設定されている場合:
   a. vault/.git が存在しない → git clone GITHUB_REPO_URL VAULT_DIR
   b. vault/.git が存在する   → git pull（最新を取得）
4. OBSIDIAN_VAULT_ID が設定されている場合 → ob sync-setup を実行
5. 設定ファイル (config.json) が存在しない場合はデフォルトで作成
6. 残留ロックの解除
7. バックグラウンド ob sync ワーカー起動
```

---

## CI/CD が必要な場合（上級者向け）

コードを頻繁に変更する場合は Cloud Build を組み合わせた自動デプロイも使えます：

```bash
gcloud builds submit . \
  --config=deploy/cloud-run/cloudbuild.yaml \
  --substitutions=_GITHUB_REPO_URL=git@github.com:YOUR_USER/YOUR_REPO.git
```

---

## トラブルシューティング

### ❌ Secret Manager API has not been used … or it is disabled

```
ERROR: Secret Manager API has not been used in project ... before or it is disabled.
```

**原因**: プロジェクトで Secret Manager API が有効化されていない。

**対処**: `setup-secrets.sh` を実行すると自動で有効化されます。手動で有効化する場合：

```bash
gcloud services enable secretmanager.googleapis.com --project=YOUR_PROJECT_ID
```

---

### ❌ Permission denied on secret ... for Revision service account PROJECT_NUMBER-compute@developer.gserviceaccount.com

```
ERROR: Permission denied on secret: ... for Revision service account
1087279555743-compute@developer.gserviceaccount.com
```

**原因**:  
Cloud Run はデフォルトで **Compute Engine デフォルト SA**（`PROJECT_NUMBER-compute@developer.gserviceaccount.com`）を使いますが、`setup-secrets.sh` の旧バージョンでは **App Engine SA**（`PROJECT_ID@appspot.gserviceaccount.com`）にしか権限を付与していませんでした。

**対処**: `setup-secrets.sh` の最新版を実行すると、両方の SA に自動で権限を付与します。

```bash
bash deploy/cloud-run/setup-secrets.sh
```

手動で付与する場合：

```bash
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret in obsidian-sync-api-key obsidian-sync-git-ssh-key; do
    gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:$SA" \
        --role="roles/secretmanager.secretAccessor"
done
```

---

### vault の clone に失敗する

Cloud Run のログを確認：

```bash
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=obsidian-sync-server" \
  --limit=50 --format="value(textPayload)"
```

よくある原因：
- SSH 鍵が GitHub Deploy Keys に登録されていない（Read/Write 権限を要確認）
- `GITHUB_REPO_URL` が HTTPS 形式になっている → SSH 形式 `git@github.com:...` で指定

---

### コンテナ再起動時のデータの永続化について

Cloud Run はステートレスでゼロスケールするため、通常は再起動で `/app/server/data/config.json` や `/vault` ディレクトリ内の未pushの変更が失われます。
本リポジトリではこの対策として、コンテナのシャットダウン処理（SIGTERM受信時）に `GCS_BUCKET_NAME` で指定されたGCSバケットに対して、対象ディレクトリを圧縮してバックアップし、次回の起動時に復元する仕組みを組み込んでいます。
これにより、ゼロスケールによるデータの消失を防いでいます。

---

### M1/M2 Mac でビルドしたイメージが動かない

deploy.sh では `--platform linux/amd64` を指定しているため、arm64 の問題は発生しないはずです。  
ビルドが遅い場合は `docker buildx` の設定を確認してください。
