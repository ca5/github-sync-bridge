#!/usr/bin/env bash
# =============================================================================
# Secret Manager セットアップスクリプト
# Cloud Run デプロイ前に一度だけ実行してください
# =============================================================================
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# 設定（環境に合わせて変更してください）
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${REGION:-asia-northeast1}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_rsa}"  # GitHub SSH 秘密鍵のパス

echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "SSH key: $SSH_KEY_PATH"
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# Secret 1: API_KEY
# ──────────────────────────────────────────────────────────────────────────────
echo "=== obsidian-sync-api-key ==="
if gcloud secrets describe obsidian-sync-api-key --project="$PROJECT_ID" &>/dev/null; then
    echo "  既存のシークレットを更新します"
    echo -n "新しい API Key を入力 (Enter でスキップ): "
    read -r api_key
    if [[ -n "$api_key" ]]; then
        echo -n "$api_key" | gcloud secrets versions add obsidian-sync-api-key \
            --data-file=- --project="$PROJECT_ID"
        echo "  ✅ 更新完了"
    fi
else
    echo "  新規作成します"
    echo -n "API Key を入力: "
    read -r api_key
    echo -n "$api_key" | gcloud secrets create obsidian-sync-api-key \
        --data-file=- --project="$PROJECT_ID" --replication-policy=automatic
    echo "  ✅ 作成完了"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Secret 2: GIT_SSH_KEY (SSH 秘密鍵の内容をそのまま格納)
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "=== obsidian-sync-git-ssh-key ==="
if [[ ! -f "$SSH_KEY_PATH" ]]; then
    echo "  ❌ SSH 鍵が見つかりません: $SSH_KEY_PATH"
    echo "     SSH_KEY_PATH 環境変数で指定してから再実行してください"
    exit 1
fi

if gcloud secrets describe obsidian-sync-git-ssh-key --project="$PROJECT_ID" &>/dev/null; then
    echo "  既存のシークレットを更新します"
    gcloud secrets versions add obsidian-sync-git-ssh-key \
        --data-file="$SSH_KEY_PATH" --project="$PROJECT_ID"
    echo "  ✅ 更新完了"
else
    echo "  新規作成します: $SSH_KEY_PATH"
    gcloud secrets create obsidian-sync-git-ssh-key \
        --data-file="$SSH_KEY_PATH" --project="$PROJECT_ID" \
        --replication-policy=automatic
    echo "  ✅ 作成完了"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Cloud Run サービスアカウントへのアクセス権付与
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "=== Cloud Run サービスアカウントへの権限付与 ==="

# Cloud Run のデフォルトサービスアカウント
SA="${PROJECT_ID}@appspot.gserviceaccount.com"
# または compute エンジンのデフォルト SA を使う場合:
# SA="$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com"

for secret in obsidian-sync-api-key obsidian-sync-git-ssh-key; do
    gcloud secrets add-iam-policy-binding "$secret" \
        --member="serviceAccount:$SA" \
        --role="roles/secretmanager.secretAccessor" \
        --project="$PROJECT_ID" \
        --quiet
    echo "  ✅ $secret → $SA にアクセス権付与"
done

echo ""
echo "=== 完了 ==="
echo "次のコマンドでデプロイを実行してください:"
echo ""
echo "  gcloud builds submit . \\"
echo "    --config=deploy/cloud-run/cloudbuild.yaml \\"
echo "    --substitutions=_GITHUB_REPO_URL=git@github.com:YOUR/REPO.git"
