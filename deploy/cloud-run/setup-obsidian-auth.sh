#!/usr/bin/env bash
# =============================================================================
# setup-obsidian-auth.sh — Obsidian Sync の認証トークンを取得して
#                           Secret Manager に登録するスクリプト
#
# 実行場所: ローカル Mac（Cloud Run ではなく手元のマシンで実行）
# 実行タイミング: 初回セットアップ時、またはトークンを更新するとき
#
# 参考: https://forum.obsidian.md/t/headless-sync-how-to-get-obsidian-auth-token-variable/111740/2
# =============================================================================
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"

# obsidian-headless がトークンを保存するパス
# 参考: https://forum.obsidian.md/t/headless-sync-how-to-get-obsidian-auth-token-variable/111740/
# ~/.obsidian-headless/auth_token （バージョンによって ~/.config/obsidian-headless/ の場合もある）
DEFAULT_TOKEN_PATH="$HOME/.obsidian-headless/auth_token"

echo "========================================"
echo " Obsidian Sync 認証トークン セットアップ"
echo " Project: $PROJECT_ID"
echo "========================================"
echo ""

# ─── Step 1: ob login ────────────────────────────────────────────────────────
echo "▶ Step 1/4  Obsidian にログイン"
echo "  メールアドレス・パスワード・MFA を入力してください"
echo ""

# ob の場所を特定
OB_CMD="${OB_CMD:-$(pwd)/node_modules/.bin/ob}"
if [[ ! -x "$OB_CMD" ]]; then
    OB_CMD="$(command -v ob 2>/dev/null || echo '')"
fi
if [[ -z "$OB_CMD" ]]; then
    echo "❌ ob コマンドが見つかりません"
    echo "   プロジェクトルートで pnpm install を実行してから再試行してください"
    exit 1
fi

"$OB_CMD" login
echo "  ✅ ログイン完了"

# ─── Step 2: トークンファイルを探す ─────────────────────────────────────────
echo ""
echo "▶ Step 2/4  認証トークンを取得"

TOKEN_FILE=""

# 1. デフォルトパスを确認（フォーラム記載の ~/.config/obsidian-headless/auth_token）
if [[ -f "$DEFAULT_TOKEN_PATH" ]]; then
    TOKEN_FILE="$DEFAULT_TOKEN_PATH"
else
    # 2. find で検索（場合によって場所が异なる可能性がある）
    echo "  デフォルトパスに見つかりません。find で検索中..."
    FOUND=$(find ~ -path "*obsidian-headless*auth_token" 2>/dev/null | head -1)
    if [[ -n "$FOUND" ]]; then
        TOKEN_FILE="$FOUND"
    fi
fi

if [[ -z "$TOKEN_FILE" ]]; then
    echo "  ❌ トークンファイルが見つかりません"
    echo "  以下のパスを確認してください:"
    echo "    $DEFAULT_TOKEN_PATH"
    echo "  または: find ~ -path '*obsidian-headless*' 2>/dev/null"
    exit 1
fi

TOKEN=$(cat "$TOKEN_FILE")
echo "  ✅ トークン取得完了: ${TOKEN_FILE}"
echo "  (トークン先頭8文字: ${TOKEN:0:8}...)"

# ─── Step 3: トークンを Secret Manager に登録 ────────────────────────────────
echo ""
echo "▶ Step 3/4  Secret Manager に登録"

gcloud services enable secretmanager.googleapis.com --project="$PROJECT_ID" --quiet

if gcloud secrets describe obsidian-sync-auth-token --project="$PROJECT_ID" &>/dev/null; then
    echo -n "$TOKEN" | gcloud secrets versions add obsidian-sync-auth-token \
        --data-file=- --project="$PROJECT_ID"
    echo "  ✅ obsidian-sync-auth-token を更新しました"
else
    echo -n "$TOKEN" | gcloud secrets create obsidian-sync-auth-token \
        --data-file=- --project="$PROJECT_ID" --replication-policy=automatic
    echo "  ✅ obsidian-sync-auth-token を新規作成しました"
fi

# Cloud Run サービスアカウントへのアクセス権付与
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SERVICE_ACCOUNTS=(
    "${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
    "${PROJECT_ID}@appspot.gserviceaccount.com"
)
for sa in "${SERVICE_ACCOUNTS[@]}"; do
    if gcloud iam service-accounts describe "$sa" --project="$PROJECT_ID" &>/dev/null; then
        gcloud secrets add-iam-policy-binding obsidian-sync-auth-token \
            --member="serviceAccount:$sa" \
            --role="roles/secretmanager.secretAccessor" \
            --project="$PROJECT_ID" --quiet
        echo "  ✅ アクセス権付与: $sa"
    fi
done

# ─── Step 4: Vault ID の確認 ─────────────────────────────────────────────────
echo ""
echo "▶ Step 4/4  Obsidian Sync Vault ID の確認"
echo ""
"$OB_CMD" sync-list-remote 2>/dev/null || echo "  (vault 一覧の取得に失敗しました)"
echo ""
echo "========================================"
echo " ✅ 完了！"
echo ""
echo " 次に deploy.sh を実行する際、以下を設定してください:"
echo ""
echo "   GITHUB_REPO_URL=git@github.com:YOUR/REPO.git \\"
echo "   OBSIDIAN_VAULT_ID=<上記リストの Vault ID> \\"
echo "   bash deploy/cloud-run/deploy.sh"
echo ""
echo " ⚠️  注意: ob logout を実行するとトークンが無効になります。"
echo "         その場合はこのスクリプトを再実行してください。"
echo "========================================"
