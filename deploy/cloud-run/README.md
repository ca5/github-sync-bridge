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

### ③  Secret Manager にシークレットを登録

```bash
# SSH 鍵のパスを環境変数で指定して実行
SSH_KEY_PATH=~/.ssh/obsidian_sync_deploy \
  bash deploy/cloud-run/setup-secrets.sh
```

---

## デプロイ手順（スクリプト一発）

```bash
GITHUB_REPO_URL=git@github.com:YOUR_USER/YOUR_REPO.git \
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
| `API_KEY` | **Secret Manager** | API 認証キー |
| `GIT_SSH_KEY` | **Secret Manager** | SSH 秘密鍵の内容（PEM 形式） |
| `GITHUB_REPO_URL` | deploy.sh の引数 | vault の GitHub リポジトリ (SSH 形式) |
| `VAULT_DIR` | deploy.sh 内に設定 | vault のパス（デフォルト: `/vault`） |
| `OB_CMD` | deploy.sh 内に設定 | ob コマンドのパス |
| `GIT_USER_NAME` | 必要に応じて追加 | git コミット時のユーザー名 |
| `GIT_USER_EMAIL` | 必要に応じて追加 | git コミット時のメールアドレス |

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
2. GITHUB_REPO_URL が設定されている場合:
   a. vault/.git が存在しない → git clone GITHUB_REPO_URL VAULT_DIR
   b. vault/.git が存在する   → git pull（最新を取得）
3. 設定ファイル (config.json) が存在しない場合はデフォルトで作成
4. 残留ロックの解除
5. バックグラウンド ob sync ワーカーの起動
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

### config.json が再起動のたびにリセットされる

Cloud Run はステートレスのため、コンテナ再起動で `/app/server/data/config.json` が消えます。  
設定の永続化には Cloud Storage Volume Mount の利用を検討してください（将来の課題）。

### M1/M2 Mac でビルドしたイメージが動かない

deploy.sh では `--platform linux/amd64` を指定しているため、arm64 の問題は発生しないはずです。  
ビルドが遅い場合は `docker buildx` の設定を確認してください。
