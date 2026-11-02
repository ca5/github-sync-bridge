# ── ステージ1: Node.js (obsidian-headless のインストール) ──────────────
FROM node:22-slim AS node-deps

WORKDIR /app

# ネイティブアドオン (better-sqlite3) のコンパイルに必要なパッケージ
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# pnpm のインストール
RUN npm install -g pnpm

# 依存関係ファイルをコピー（pluginのpackage.jsonも必要: workspaceの解決）
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc* ./
COPY plugin/package.json ./plugin/
COPY scripts/ ./scripts/

# 本番依存インストール（ignore-scriptsでインストール後にbetter-sqlite3を明示的にrebuild）
RUN pnpm install --frozen-lockfile --prod --ignore-scripts
RUN pnpm rebuild better-sqlite3
RUN node scripts/patch-obsidian-headless.js

# better-sqlite3 のネイティブバインディングが正しく動作することをビルド時に検証
RUN node -e "require('better-sqlite3'); console.log('better-sqlite3 loaded successfully in stage 1')"

# ── ステージ2: アプリケーション本体 ────────────────────────────────────
FROM python:3.11-slim

# システム依存パッケージ
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Node.js ランタイム（ob コマンド実行に必要）
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# SSH: 既知ホストの確認をスキップ（Cloud Run で初回接続時に詰まらないよう）
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh \
    && echo "StrictHostKeyChecking no\nUserKnownHostsFile /dev/null" > /root/.ssh/config

# git グローバル設定（コミット時に必要）
RUN git config --global user.email "obsidian-sync-bot@server" \
    && git config --global user.name "Obsidian Sync Bot" \
    && git config --global core.longpaths true

WORKDIR /app

# Node modules（ステージ1からコピー）
COPY --from=node-deps /app/node_modules ./node_modules
COPY package.json ./

# better-sqlite3 および ob コマンドが実行可能かを検証
RUN node -e "require('better-sqlite3'); console.log('better-sqlite3 loaded successfully in stage 2')" \
    && ./node_modules/.bin/ob --help > /dev/null

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
