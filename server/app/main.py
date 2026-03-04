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
    return {
        **_sync_status,
        "is_vault_ready": safe,
        "vault_dir": VAULT_DIR,
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
    Obsidianが異常終了した際や、ローカルObsidianを閉じた後にロックが残る場合に尀う。
    """
    sync_lock = os.path.join(VAULT_DIR, ".obsidian", ".sync.lock")
    if os.path.isdir(sync_lock):
        try:
            os.rmdir(sync_lock)
            print(f"Removed stale sync lock: {sync_lock}")
        except OSError as e:
            print(f"Warning: Could not remove sync lock: {e}")


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
        config_result = subprocess.run(config_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
        sync_result = subprocess.run(sync_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
        output = config_result.stdout + "\n" + sync_result.stdout
        return {"status": "success", "message": "Force sync triggered successfully.", "output": output}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {e.stderr}")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="obsidian-headless (ob) is not installed or not in PATH.")

# -------------------------------------------------------------------
# Git API
# -------------------------------------------------------------------

# SSH 認証用の環境変数を組み立てる
_GIT_SSH_KEY = os.getenv("GIT_SSH_KEY_PATH", os.path.expanduser("~/.ssh/id_rsa"))

def _git_env() -> dict:
    """git コマンド実行時の環境変数（SSH 認証を含む）"""
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = f"ssh -i {_GIT_SSH_KEY} -o StrictHostKeyChecking=no"
    return env

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

        # sync前にロックを解放（Obsidianが終了してロックが残っている場合に対応）
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
            msg = e.stderr.strip()
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
    # 初回起動時に設定ファイルがなければ作成
    if not os.path.exists(CONFIG_FILE):
        save_settings(load_settings())

    # 前回の異常終了 (--reload 等) で残ったロックを削除
    clear_sync_lock()

    # バックグラウンドワーカー起動
    thread = threading.Thread(target=sync_worker, daemon=True)
    thread.start()
