# ── ステージ1: Node.js (obsidian-headless のインストール) ──────────────
FROM node:20-slim AS node-deps

WORKDIR /app

# pnpm のインストール
RUN npm install -g pnpm

# 依存関係ファイルをコピー（pluginのpackage.jsonも必要: workspaceの解決）
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY plugin/package.json ./plugin/

# 本番依存のみインストール（plugin devDeps を除く）
RUN pnpm install --frozen-lockfile --prod

# ── ステージ2: アプリケーション本体 ────────────────────────────────────
FROM python:3.11-slim

# システム依存パッケージ
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Node.js ランタイム（ob コマンド実行に必要）
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# SSH: 既知ホストの確認をスキップ（Cloud Run で初回接続時に詰まらないよう）
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh \
    && echo "StrictHostKeyChecking no\nUserKnownHostsFile /dev/null" > /root/.ssh/config

# git グローバル設定（コミット時に必要）
RUN git config --global user.email "obsidian-sync-bot@server" \
    && git config --global user.name "Obsidian Sync Bot"

WORKDIR /app

# Node modules（ステージ1からコピー）
COPY --from=node-deps /app/node_modules ./node_modules
COPY package.json ./

# Python 依存のインストール
COPY server/requirements.txt ./server/
RUN pip install --no-cache-dir -r ./server/requirements.txt

# アプリケーションコード
COPY server/ ./server/

# データディレクトリ
RUN mkdir -p /app/server/data /vault

# 環境変数デフォルト
ENV VAULT_DIR=/vault \
    OB_CMD=/app/node_modules/.bin/ob \
    CONFIG_FILE=/app/server/data/config.json \
    PORT=8080

EXPOSE 8080

WORKDIR /app/server
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
