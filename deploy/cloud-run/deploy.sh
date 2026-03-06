#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Obsidian Sync Server を Google Cloud Run にデプロイする
#
# 使い方:
#   bash deploy/cloud-run/deploy.sh
#
# 前提:
#   - gcloud auth login 済み
#   - gcloud config set project YOUR_PROJECT_ID 済み
#   - Docker が起動中
#   - setup-secrets.sh を一度実行済み（Secret Manager にシークレット登録済み）
# =============================================================================
set -euo pipefail

# ─── 設定（必要に応じて変更してください）───────────────────────────────────
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-obsidian-sync-server}"
REPO="${REPO:-obsidian-sync}"                        # Artifact Registry リポジトリ名
GITHUB_REPO_URL="${GITHUB_REPO_URL:-}"               # 例: git@github.com:ca5/obsidian.git
OBSIDIAN_VAULT_ID="${OBSIDIAN_VAULT_ID:-}"           # ob sync-list-remote で確認した Vault ID

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE_NAME}"

# ─── バリデーション ───────────────────────────────────────────────────────
if [[ -z "$PROJECT_ID" ]]; then
    echo "❌ PROJECT_ID が未設定です"
    echo "   gcloud config set project YOUR_PROJECT_ID を実行してください"
    exit 1
fi

if [[ -z "$GITHUB_REPO_URL" ]]; then
    echo "❌ GITHUB_REPO_URL が未設定です"
    echo "   例: GITHUB_REPO_URL=git@github.com:ca5/obsidian.git bash deploy/cloud-run/deploy.sh"
    exit 1
fi

# スクリプトはプロジェクトルートから実行されることを想定
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "========================================"
echo " Obsidian Sync Server — Cloud Run Deploy"
echo "========================================"
echo " Project:  $PROJECT_ID"
echo " Region:   $REGION"
echo " Service:  $SERVICE_NAME"
echo " Image:    $IMAGE:latest"
echo " GitHub:   $GITHUB_REPO_URL"
echo "========================================"
echo ""

# ─── Step 1: Artifact Registry の認証設定 ────────────────────────────────
echo "▶ Step 1/4  Artifact Registry の認証設定"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Artifact Registry リポジトリが存在しない場合は作成
if ! gcloud artifacts repositories describe "$REPO" \
    --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    echo "  リポジトリ '$REPO' を作成中..."
    gcloud artifacts repositories create "$REPO" \
        --repository-format=docker \
        --location="$REGION" \
        --project="$PROJECT_ID" \
        --description="Obsidian Sync Server"
fi
echo "  ✅ 完了"

# ─── Step 2: Docker イメージのビルド ─────────────────────────────────────
echo ""
echo "▶ Step 2/4  Docker イメージをビルド"
docker build \
    --platform linux/amd64 \
    -t "${IMAGE}:latest" \
    "$PROJECT_ROOT"
echo "  ✅ 完了"

# ─── Step 3: Artifact Registry へ push ───────────────────────────────────
echo ""
echo "▶ Step 3/4  Artifact Registry へ push"
docker push "${IMAGE}:latest"
echo "  ✅ 完了"

# ─── Step 4: Cloud Run へデプロイ ────────────────────────────────────────
echo ""
echo "▶ Step 4/4  Cloud Run へデプロイ"
gcloud run deploy "$SERVICE_NAME" \
    --image="${IMAGE}:latest" \
    --region="$REGION" \
    --platform=managed \
    --allow-unauthenticated \
    --min-instances=0 \
    --max-instances=1 \
    --memory=512Mi \
    --cpu=1 \
    --port=8080 \
    --set-env-vars="VAULT_DIR=/vault" \
    --set-env-vars="OB_CMD=/app/node_modules/.bin/ob" \
    --set-env-vars="CONFIG_FILE=/app/server/data/config.json" \
    --set-env-vars="GITHUB_REPO_URL=${GITHUB_REPO_URL}" \
    --set-env-vars="OBSIDIAN_VAULT_ID=${OBSIDIAN_VAULT_ID}" \
    --update-secrets="API_KEY=obsidian-sync-api-key:latest" \
    --update-secrets="GIT_SSH_KEY=obsidian-sync-git-ssh-key:latest" \
    --update-secrets="OBSIDIAN_AUTH_TOKEN=obsidian-sync-auth-token:latest" \
    --project="$PROJECT_ID" \
    --quiet
echo "  ✅ 完了"

# ─── 結果表示 ────────────────────────────────────────────────────────────
echo ""
URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format='value(status.url)' 2>/dev/null || echo "(URL 取得失敗)")

echo "========================================"
echo " ✅ デプロイ完了!"
echo ""
echo " Service URL: $URL"
echo " API Docs:    $URL/docs"
echo ""
echo " 動作確認:"
echo "   curl -H 'X-API-Key: YOUR_API_KEY' $URL/api/sync/status"
echo "========================================"
