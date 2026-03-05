from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone

app = FastAPI(title="Obsidian Sync Server API")

# 同期ステータスをメモリで管理
_sync_status = {
    "last_sync_at": None,       # 最終sync実行時刻 (ISO8601)
    "last_sync_result": None,   # "success" | "failed" | "skipped"
    "last_sync_message": "",    # エラーメッセージなど
    "is_vault_ready": False,    # Vaultが同期可能な状態か
}

CONFIG_FILE = os.getenv("CONFIG_FILE", "./data/config.json")
API_KEY = os.getenv("API_KEY", "default-secret-key")
# ob sync-setup を実行したVaultのディレクトリ
# デフォルト: プロジェクトルート/vault（--path ./vault で setup 済み）
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
VAULT_DIR = os.getenv("VAULT_DIR", os.path.join(_PROJECT_ROOT, "vault"))
# ob コマンドの絶対パス（PATH に依存しないよう直接解決）
OB_CMD = os.getenv("OB_CMD", os.path.join(_PROJECT_ROOT, "node_modules/.bin/ob"))
# SSH 秘密鍵のパス（setup_ssh_key() で更新される場合がある）
_GIT_SSH_KEY = os.getenv("GIT_SSH_KEY_PATH", os.path.expanduser("~/.ssh/id_rsa"))

class Settings(BaseModel):
    sync_obsidian_config: bool
    auto_sync_interval: int
    github_branch_patterns: List[str]

def load_settings() -> Settings:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return Settings(**data)
    else:
        # Default settings
        return Settings(
            sync_obsidian_config=False,
            auto_sync_interval=60,
            github_branch_patterns=[]
        )

def save_settings(settings: Settings):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        f.write(settings.model_dump_json(indent=2))

def verify_api_key(api_key: str):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@app.get("/api/settings", response_model=Settings)
def get_settings(x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    return load_settings()

@app.get("/api/sync/status")
def get_sync_status(x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    safe, reason = check_vault_safety()
    # Obsidian Sync が設定済みか（ob sync-setup 済みなら .obsidian/.sync.lock が作られた実績がある）
    # 簡易判定: vault/.obsidian/sync.json の存在で確認
    ob_sync_conf = os.path.exists(os.path.join(VAULT_DIR, ".obsidian", "sync.json"))
    return {
        **_sync_status,
        "is_vault_ready": safe,
        "vault_dir": VAULT_DIR,
        "ob_sync_configured": ob_sync_conf,
        "github_repo_url": os.getenv("GITHUB_REPO_URL", ""),
    }

@app.post("/api/settings", response_model=Settings)
def update_settings(settings: Settings, x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    save_settings(settings)
    return settings

def check_vault_safety() -> tuple[bool, str]:
    """Vaultが空でないことを確認する安全チェック。
    空のVaultでob syncを実行するとリモートのノートが全削除される危険がある。
    """
    if not os.path.isdir(VAULT_DIR):
        return False, f"Vault directory does not exist: {VAULT_DIR}"
    md_files = [
        f for f in os.listdir(VAULT_DIR)
        if not f.startswith('.')
    ]
    if not md_files:
        return False, (
            f"Vault directory is empty: {VAULT_DIR}. "
            "Refusing to sync to prevent accidental deletion of remote notes. "
            "Please run 'ob sync-setup' and ensure local notes exist first."
        )
    return True, ""

def clear_sync_lock():
    """sync.lockディレクトリを削除する。
    Obsidianが異常終了した際や、ローカルObsidianを閉じた後にロックが残る場合に使う。
    """
    sync_lock = os.path.join(VAULT_DIR, ".obsidian", ".sync.lock")
    if os.path.isdir(sync_lock):
        try:
            os.rmdir(sync_lock)
            print(f"Removed stale sync lock: {sync_lock}")
        except OSError as e:
            print(f"Warning: Could not remove sync lock: {e}")

# ob sync の同時実行を防ぐロック（force_sync ↔ sync_worker の競合防止）
_ob_sync_lock = threading.Lock()


@app.post("/api/sync/force")
def force_sync(x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    settings = load_settings()

    # 安全チェック: Vaultが空の場合はsyncを拒否
    safe, reason = check_vault_safety()
    if not safe:
        raise HTTPException(status_code=500, detail=f"Sync aborted: {reason}")

    # 同期実行ロジック (obsidian-headless版)
    print(f"Executing force sync... sync_obsidian_config: {settings.sync_obsidian_config}")

    # 1. 構成設定の更新
    if settings.sync_obsidian_config:
        config_command = [OB_CMD, "sync-config", "--configs", "app,appearance,appearance-data,hotkey,core-plugin,core-plugin-data,community-plugin,community-plugin-data"]
    else:
        config_command = [OB_CMD, "sync-config", "--configs", ""]

    # 2. 同期の実行
    sync_command = [OB_CMD, "sync"]

    try:
        with _ob_sync_lock:
            clear_sync_lock()
            config_result = subprocess.run(config_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
            sync_result = subprocess.run(sync_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
        output = config_result.stdout + "\n" + sync_result.stdout
        return {"status": "success", "message": "Force sync triggered successfully.", "output": output}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {_trim_error(e.stderr)}")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="obsidian-headless (ob) is not installed or not in PATH.")

# -------------------------------------------------------------------
# Git API
# -------------------------------------------------------------------

def _git_env() -> dict:
    """git コマンド実行時の環境変数（SSH 認証を含む）"""
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = f"ssh -i {_GIT_SSH_KEY} -o StrictHostKeyChecking=no"
    return env

def _trim_error(stderr: str, max_len: int = 200) -> str:
    """
    ob sync / git のエラーメッセージを読みやすく切り詰める。
    Node.js のミニファイコードが stderr に入り込む場合に対応。
    - 最初の意味のある行（スペース・空行ではない行）だけを返す
    - max_len 文字を超えた場合は切り捨てる
    """
    if not stderr:
        return "(no error message)"
    # 意味のある行（空でない行）だけを抽出
    meaningful = [line for line in stderr.strip().splitlines() if line.strip()]
    first_line = meaningful[0] if meaningful else stderr.strip()
    return first_line[:max_len] + ("..." if len(first_line) > max_len else "")

def _git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """vault/ ディレクトリで git コマンドを実行する"""
    return subprocess.run(
        ["git"] + args,
        capture_output=True, text=True,
        check=check, cwd=VAULT_DIR,
        env=_git_env()
    )

class CommitRequest(BaseModel):
    message: str

class CheckoutRequest(BaseModel):
    branch: str

@app.get("/api/git/status")
def git_status(x_api_key: Optional[str] = Header(None)):
    """現在のブランチ・変更ファイル一覧を返す"""
    verify_api_key(x_api_key)
    try:
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        status = _git(["status", "--short"]).stdout.strip()
        changed_files = [line for line in status.splitlines() if line]
        return {
            "branch": branch,
            "changed_files": changed_files,
            "is_clean": len(changed_files) == 0,
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"git status failed: {e.stderr}")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="git is not installed.")

@app.get("/api/git/branches")
def git_branches(x_api_key: Optional[str] = Header(None)):
    """ローカル + リモートのブランチ一覧を返す"""
    verify_api_key(x_api_key)
    try:
        current = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        local_raw = _git(["branch", "--format=%(refname:short)"]).stdout.strip()
        remote_raw = _git(["branch", "-r", "--format=%(refname:short)"]).stdout.strip()
        local = [b for b in local_raw.splitlines() if b]
        remote = [b.replace("origin/", "") for b in remote_raw.splitlines()
                  if b and "HEAD" not in b]
        all_branches = sorted(set(local + remote))
        return {
            "current": current,
            "branches": all_branches,
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"git branch failed: {e.stderr}")

@app.post("/api/git/checkout")
def git_checkout(req: CheckoutRequest, x_api_key: Optional[str] = Header(None)):
    """ブランチを切り替える。追跡済みファイルに未コミット変更があればエラー。切り替え後に git pull を実行。"""
    verify_api_key(x_api_key)
    try:
        # 未コミット変更チェック（未追跡ファイル「??」は git checkout をブロックしないため除外）
        status_lines = _git(["status", "--short"]).stdout.strip().splitlines()
        tracked_changes = [line for line in status_lines if line and not line.startswith("??")]
        if tracked_changes:
            raise HTTPException(
                status_code=409,
                detail=(
                    "未コミットの変更があるためブランチを切り替えられません。"
                    "先にコミットしてください。\n"
                    + "\n".join(tracked_changes)
                )
            )
        # ブランチ切り替え（リモートにしかない場合は自動でトラッキング）
        _git(["checkout", "-B", req.branch, f"origin/{req.branch}"])
        # git pull
        pull_result = _git(["pull", "origin", req.branch])
        return {
            "status": "success",
            "branch": req.branch,
            "pull_output": pull_result.stdout.strip(),
        }
    except HTTPException:
        raise
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"git checkout failed: {e.stderr}")

@app.post("/api/git/commit")
def git_commit(req: CommitRequest, x_api_key: Optional[str] = Header(None)):
    """すべての変更をステージして指定メッセージでコミットする"""
    verify_api_key(x_api_key)
    try:
        _git(["add", "-A"])
        result = _git(["commit", "-m", req.message])
        return {"status": "success", "output": result.stdout.strip()}
    except subprocess.CalledProcessError as e:
        detail = e.stderr.strip() or e.stdout.strip()
        raise HTTPException(status_code=500, detail=f"git commit failed: {detail}")

@app.post("/api/git/push")
def git_push(x_api_key: Optional[str] = Header(None)):
    """現在のブランチをリモートへ push する（SSH認証）"""
    verify_api_key(x_api_key)
    try:
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        result = _git(["push", "origin", branch])
        return {"status": "success", "branch": branch, "output": result.stdout.strip()}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"git push failed: {e.stderr}")

@app.post("/api/git/pull")
def git_pull(x_api_key: Optional[str] = Header(None)):
    """現在のブランチをリモートから pull する"""
    verify_api_key(x_api_key)
    try:
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        result = _git(["pull", "origin", branch])
        return {"status": "success", "branch": branch, "output": result.stdout.strip()}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"git pull failed: {e.stderr}")


# 定期実行ワーカー
def sync_worker():
    while True:
        settings = load_settings()
        interval = settings.auto_sync_interval

        print(f"Background worker running... Interval: {interval} min, sync_obsidian_config: {settings.sync_obsidian_config}")

        # 安全チェック: Vaultが空の場合はsyncをスキップ
        safe, reason = check_vault_safety()
        if not safe:
            print(f"Background sync skipped: {reason}")
            _sync_status.update({
                "last_sync_at": datetime.now(timezone.utc).isoformat(),
                "last_sync_result": "skipped",
                "last_sync_message": reason,
            })
            time.sleep(interval * 60)
            continue

        # sync前にロックを解放してから実行（_ob_sync_lock で同時実行も防止）
        with _ob_sync_lock:
            clear_sync_lock()

            # 1. 構成設定の更新
            if settings.sync_obsidian_config:
                config_command = [OB_CMD, "sync-config", "--configs", "app,appearance,appearance-data,hotkey,core-plugin,core-plugin-data,community-plugin,community-plugin-data"]
            else:
                config_command = [OB_CMD, "sync-config", "--configs", ""]

            # 2. 同期の実行
            sync_command = [OB_CMD, "sync"]

            try:
                subprocess.run(config_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
                subprocess.run(sync_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
                print("Background sync successful.")
                _sync_status.update({
                    "last_sync_at": datetime.now(timezone.utc).isoformat(),
                    "last_sync_result": "success",
                    "last_sync_message": "",
                })
            except subprocess.CalledProcessError as e:
                msg = _trim_error(e.stderr)
                print(f"Background sync failed: {msg}")
                _sync_status.update({
                    "last_sync_at": datetime.now(timezone.utc).isoformat(),
                    "last_sync_result": "failed",
                    "last_sync_message": msg,
                })
            except FileNotFoundError:
                msg = "obsidian-headless (ob) is not installed or not in PATH."
                print(msg)
                _sync_status.update({
                    "last_sync_at": datetime.now(timezone.utc).isoformat(),
                    "last_sync_result": "failed",
                    "last_sync_message": msg,
                })

        # 次のインターバルまで待機
        time.sleep(interval * 60)

@app.on_event("startup")
def startup_event():
    # SSH 鍵のセットアップ（GIT_SSH_KEY 環境変数からファイルを作成）
    setup_ssh_key()

    # Obsidian 認証トークンの復元（OBSIDIAN_AUTH_TOKEN 環境変数から）
    setup_obsidian_auth()

    # GitHub から vault を初期化（GITHUB_REPO_URL が設定されている場合）
    init_vault_from_github()

    # Obsidian Sync の vault セットアップ（OBSIDIAN_VAULT_ID が設定されている場合）
    setup_obsidian_vault()

    # 初回起動時に設定ファイルがなければ作成
    if not os.path.exists(CONFIG_FILE):
        save_settings(load_settings())

    # 前回の異常終了 (--reload 等) で残ったロックを削除
    clear_sync_lock()

    # バックグラウンドワーカー起動
    thread = threading.Thread(target=sync_worker, daemon=True)
    thread.start()


def setup_ssh_key() -> None:
    """
    GIT_SSH_KEY 環境変数（PEM 形式の秘密鍵文字列）から
    一時ファイルを作成し、_GIT_SSH_KEY グローバル変数を更新する。
    Cloud Run では Secret Manager から env var に注入された値を利用する。
    """
    global _GIT_SSH_KEY
    git_ssh_key_content = os.getenv("GIT_SSH_KEY", "")
    if not git_ssh_key_content:
        # 環境変数未設定: GIT_SSH_KEY_PATH のファイルをそのまま使用
        print(f"GIT_SSH_KEY not set. Using key file: {_GIT_SSH_KEY}")
        return

    key_path = "/tmp/obsidian_sync_deploy_key"
    with open(key_path, "w") as f:
        # PEM 形式の改行が スペースに変わっている場合の修復（Cloud Run の env var 起因）
        content = git_ssh_key_content.replace("\\n", "\n")
        if not content.endswith("\n"):
            content += "\n"
        f.write(content)
    os.chmod(key_path, 0o600)
    _GIT_SSH_KEY = key_path
    print(f"SSH key written to {key_path}")


def init_vault_from_github() -> None:
    """
    起動時に GITHUB_REPO_URL が設定されている場合、
    vault/ を GitHub リポジトリから自動初期化する。
    - vault/.git がない → git clone
    - vault/.git がある → git pull（最新化）
    """
    github_repo = os.getenv("GITHUB_REPO_URL", "")
    if not github_repo:
        print("GITHUB_REPO_URL not set. Skipping vault initialization from GitHub.")
        return

    # git ユーザー設定（環境変数でカスタマイズ可）
    git_name = os.getenv("GIT_USER_NAME", "Obsidian Sync Bot")
    git_email = os.getenv("GIT_USER_EMAIL", "obsidian-sync-bot@server")
    subprocess.run(["git", "config", "--global", "user.name", git_name], check=False)
    subprocess.run(["git", "config", "--global", "user.email", git_email], check=False)

    git_dir = os.path.join(VAULT_DIR, ".git")

    if os.path.isdir(git_dir):
        # 既に初期化済み→ pull して最新化
        print(f"Vault already initialized at {VAULT_DIR}. Running git pull...")
        try:
            result = subprocess.run(
                ["git", "pull"],
                capture_output=True, text=True, check=True,
                cwd=VAULT_DIR, env=_git_env()
            )
            print(f"git pull successful: {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            print(f"Warning: git pull failed (continuing): {e.stderr.strip()}")
    else:
        # 未初期化 → git clone
        print(f"Initializing vault from {github_repo} into {VAULT_DIR} ...")
        os.makedirs(VAULT_DIR, exist_ok=True)
        parent_dir = os.path.dirname(VAULT_DIR)
        vault_name = os.path.basename(VAULT_DIR)
        try:
            result = subprocess.run(
                ["git", "clone", github_repo, vault_name],
                capture_output=True, text=True, check=True,
                cwd=parent_dir, env=_git_env()
            )
            print(f"git clone successful: {result.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            print(f"git clone failed: {e.stderr.strip()}")
            print("Vault initialization from GitHub failed. Server will start without vault.")


def setup_obsidian_auth() -> None:
    """
    OBSIDIAN_AUTH_TOKEN 環境変数から Obsidian の認証トークンを復元する。
    obsidian-headless は ~/.config/obsidian-headless/auth_token を読む。
    Cloud Run では Secret Manager 経由でこの env var に注入する。

    参考: https://forum.obsidian.md/t/headless-sync-how-to-get-obsidian-auth-token-variable/111740/2
    """
    token = os.getenv("OBSIDIAN_AUTH_TOKEN", "")
    if not token:
        print("OBSIDIAN_AUTH_TOKEN not set. Obsidian Sync may not work without authentication.")
        return

    # obsidian-headless がトークンを読むパス（Linux / Cloud Run）
    auth_dir = os.path.expanduser("~/.config/obsidian-headless")
    os.makedirs(auth_dir, exist_ok=True)
    auth_file = os.path.join(auth_dir, "auth_token")

    with open(auth_file, "w") as f:
        f.write(token.strip())
    os.chmod(auth_file, 0o600)
    print(f"Obsidian auth token written to: {auth_file}")


def setup_obsidian_vault() -> None:
    """
    OBSIDIAN_VAULT_ID が設定されていて、かつ vault の sync 設定がされていない場合に
    ob sync-setup を実行して Obsidian Sync を使えるようにする。

    ob sync-setup は同じ vault ID + path の組み合わせで何度実行しても安全。
    """
    vault_id = os.getenv("OBSIDIAN_VAULT_ID", "")
    if not vault_id:
        print("OBSIDIAN_VAULT_ID not set. Skipping ob sync-setup.")
        return

    print(f"Running ob sync-setup for vault: {vault_id} -> {VAULT_DIR}")
    try:
        result = subprocess.run(
            [OB_CMD, "sync-setup", "--vault", vault_id, "--path", VAULT_DIR],
            capture_output=True, text=True, check=True,
            cwd=VAULT_DIR
        )
        print(f"ob sync-setup successful: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"ob sync-setup failed: {_trim_error(e.stderr)}")
        print("Obsidian Sync may not work. Check OBSIDIAN_VAULT_ID and OBSIDIAN_AUTH_TOKEN.")
    except FileNotFoundError:
        print(f"ob command not found at: {OB_CMD}")
