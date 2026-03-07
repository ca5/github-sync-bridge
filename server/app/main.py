from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone

app = FastAPI(title="Obsidian Sync Server API")

# Startup completion flag - Returns 503 while False (initializing)
_startup_complete: bool = False
_startup_phase: str = "Initializing..."

@app.middleware("http")
async def startup_guard(request: Request, call_next):
    """
    Returns 503 for all endpoints except /api/health before startup is complete.
    This allows the plugin to wait for git clone etc. to finish during cold start
    when Cloud Run has min-instances=0.
    """
    if not _startup_complete:
        allow_paths = {"/api/health", "/docs", "/openapi.json", "/redoc"}
        if request.url.path not in allow_paths:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "initializing",
                    "phase": _startup_phase,
                    "message": f"Server starting: {_startup_phase}",
                    "startup_log": _startup_log[-10:],
                }
            )
    return await call_next(request)

# Manage sync status in memory
_sync_status = {
    "last_sync_at": None,       # Last sync time (ISO8601)
    "last_sync_result": None,   # "success" | "failed" | "skipped"
    "last_sync_message": "",    # Error message etc.
    "is_vault_ready": False,    # Whether the vault is ready to sync
}

# Startup logs (last 50) - accessible from /api/sync/status
_startup_log: list[str] = []

def _log(msg: str) -> None:
    """Record startup messages to both stdout and memory"""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    _startup_log.append(line)
    if len(_startup_log) > 50:
        _startup_log.pop(0)

CONFIG_FILE = os.getenv("CONFIG_FILE", "./data/config.json")
API_KEY = os.getenv("API_KEY", "default-secret-key")
# Vault directory where ob sync-setup was executed
# Default: project_root/vault (already setup with --path ./vault)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
VAULT_DIR = os.getenv("VAULT_DIR", os.path.join(_PROJECT_ROOT, "vault"))
# Absolute path to the 'ob' command (resolved directly to avoid PATH dependency)
OB_CMD = os.getenv("OB_CMD", os.path.join(_PROJECT_ROOT, "node_modules/.bin/ob"))
# Path to the SSH private key (may be updated by setup_ssh_key())
_GIT_SSH_KEY = os.getenv("GIT_SSH_KEY_PATH", os.path.expanduser("~/.ssh/id_rsa"))

class Settings(BaseModel):
    auto_sync_interval: int
    github_branch_patterns: List[str]

def load_settings() -> Settings:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            # Load settings, excluding old 'sync_obsidian_config'
            if "sync_obsidian_config" in data:
                del data["sync_obsidian_config"]
            return Settings(**data)
    else:
        # Default settings
        return Settings(
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

@app.get("/api/health")
def health_check():
    """Health check endpoint. Used by plugin to confirm server is ready."""
    return {
        "status": "ready" if _startup_complete else "initializing",
        "phase": _startup_phase,
        "startup_log": _startup_log[-10:],
    }

@app.get("/api/settings", response_model=Settings)
def get_settings(x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    return load_settings()

@app.get("/api/sync/status")
def get_sync_status(x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    safe, reason = check_vault_safety()
    ob_sync_conf = os.path.exists(os.path.join(VAULT_DIR, ".obsidian", "sync.json"))
    ob_auth_conf = _is_ob_auth_configured()
    return {
        **_sync_status,
        "is_vault_ready": safe,
        "vault_dir": VAULT_DIR,
        "ob_sync_configured": ob_sync_conf,
        "ob_auth_configured": ob_auth_conf,
        "github_repo_url": os.getenv("GITHUB_REPO_URL", ""),
        "startup_log": _startup_log[-20:],   # 最新20件
    }

@app.post("/api/settings", response_model=Settings)
def update_settings(settings: Settings, x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    save_settings(settings)
    return settings

def check_vault_safety() -> tuple[bool, str]:
    """Check if vault is not empty.
    Syncing an empty vault could delete all remote notes.
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

def clear_sync_lock() -> None:
    """
    Remove all stale ob sync locks.
    Targets:
      1. vault/.obsidian/.sync.lock
      2. ~/.obsidian-headless/sync/ *.lock
    """
    # 1. vault 内の .sync.lock
    sync_lock = os.path.join(VAULT_DIR, ".obsidian", ".sync.lock")
    if os.path.isdir(sync_lock):
        try:
            shutil.rmtree(sync_lock)
            _log(f"Removed stale vault sync lock: {sync_lock}")
        except OSError as e:
            _log(f"Warning: Could not remove vault sync lock: {e}")

    # 2. ~/.obsidian-headless/sync/ 配下の *.lock
    obs_sync_dir = os.path.expanduser("~/.obsidian-headless/sync")
    if os.path.isdir(obs_sync_dir):
        import glob
        for lock_path in glob.glob(os.path.join(obs_sync_dir, "**", "*.lock"), recursive=True):
            try:
                if os.path.isdir(lock_path):
                    shutil.rmtree(lock_path)
                else:
                    os.remove(lock_path)
                _log(f"Removed stale obsidian-headless lock: {lock_path}")
            except OSError as e:
                _log(f"Warning: Could not remove lock {lock_path}: {e}")

# ob sync の同時実行を防ぐロック（force_sync ↔ sync_worker の競合防止）
_ob_sync_lock = threading.Lock()


@app.post("/api/sync/force")
def force_sync(x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    settings = load_settings()

    # 安全チェック: Vaultが空Forはsyncを拒否
    safe, reason = check_vault_safety()
    if not safe:
        raise HTTPException(status_code=500, detail=f"Sync aborted: {reason}")

    # 同期実行ロジック (obsidian-headless版)
    print(f"Executing force sync...")

    # Executing sync
    sync_command = [OB_CMD, "sync", "--path", VAULT_DIR]

    try:
        with _ob_sync_lock:
            clear_sync_lock()
            sync_result = subprocess.run(sync_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
        output = sync_result.stdout
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
    ob sync / git Trim error messages for readability.
    Node.js Minified code / Handle file paths in stderr.
    優先度: Error: を含む行 > ファイルパス以外の行 > First line
    """
    import re
    if not stderr:
        return "(no error message)"
    lines = [l for l in stderr.strip().splitlines() if l.strip()]
    if not lines:
        return stderr.strip()[:max_len]

    def _is_js_path(line: str) -> bool:
        # ".js:7" や ".ts:12" などファイルパスとみなせる行
        return bool(re.search(r'\.(js|ts):\d+', line))

    def _is_minified(line: str) -> bool:
        # 80 Long line with many semicolons = ミニファイコード
        return len(line) > 80 and line.count(';') > 5

    # Error: を含む行を優先
    error_lines = [l for l in lines if 'Error' in l or 'error:' in l.lower()]
    if error_lines:
        best = error_lines[0]
    else:
        # JSファイルパスとミニファイ行を除いたFirst line
        readable = [l for l in lines if not _is_js_path(l) and not _is_minified(l)]
        best = readable[0] if readable else lines[0]

    return best[:max_len] + ("..." if len(best) > max_len else "")


def _is_ob_auth_configured() -> bool:
    """~/.obsidian-headless/auth_token が存在し有容頭かを確認"""
    auth_file = os.path.expanduser("~/.obsidian-headless/auth_token")
    return os.path.isfile(auth_file) and os.path.getsize(auth_file) > 0

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
    # How to handle uncommitted changes
    # - "stash"       : stash and carry over to new branch
    # - "commit_push" : Commit and push before switching
    # - "discard"     : Discard changes before switching
    mode: str = "stash"        # デフォルト: stash
    commit_message: str = ""   # mode=commit_push Commit message to use for

@app.get("/api/git/status")
def git_status(x_api_key: Optional[str] = Header(None)):
    """Return current branch and changed files"""
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
    """ローカル + Return list of remote branches"""
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
    """
    ブランチを切り替える。切り替え後に git pull を実行。
    mode Choose how to handle uncommitted changes.
    未追跡ファイルも checkout をブロックする場合existsため、全変更をチェックする。
    """
    verify_api_key(x_api_key)
    try:
        status_lines = _git(["status", "--short"]).stdout.strip().splitlines()
        # 全変更（追跡済み＋未追跡どちらも checkout をブロックしうる）
        all_changes    = [line for line in status_lines if line]
        tracked_changes = [line for line in all_changes if not line.startswith("??")]

        note = ""

        if all_changes:
            if req.mode == "stash":
                # --include-untracked: Stash both tracked and untracked files
                _git(["stash", "push", "--include-untracked",
                      "-m", f"auto-stash before checkout {req.branch}"])
                note = "__stash_pop__"

            elif req.mode == "commit_push":
                # git add -A Stage including untracked files → commit → push
                msg = req.commit_message.strip() or f"auto-commit before checkout {req.branch}"
                _git(["add", "-A"])
                _git(["commit", "-m", msg])
                current_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
                _git(["push", "origin", current_branch])
                note = f"別ブランチ ({current_branch}) にコミット・ Push しました"

            elif req.mode == "discard":
                # Discard tracked changes + Delete untracked files
                _git(["checkout", "--", "."])
                _git(["clean", "-fd"])
                note = "未コミットの変更を破棄しました"

            else:
                raise HTTPException(status_code=400, detail=f"Unknown mode: {req.mode}")

        # Checkout branch (auto track if remote only)
        _git(["checkout", "-B", req.branch, f"origin/{req.branch}"])
        # git pull
        pull_result = _git(["pull", "origin", req.branch])

        # stash pop（mode=stash For）
        if note == "__stash_pop__":
            try:
                _git(["stash", "pop"])
                note = "変更を新しいブランチに引き継ぎました"
            except subprocess.CalledProcessError:
                note = "変更を stash しました（'git stash pop' で後で復元できます）"

        return {
            "status": "success",
            "branch": req.branch,
            "pull_output": pull_result.stdout.strip(),
            "note": note,
        }
    except HTTPException:
        raise
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"git checkout failed: {_trim_error(e.stderr)}")

@app.post("/api/git/commit")
def git_commit(req: CommitRequest, x_api_key: Optional[str] = Header(None)):
    """Stage all changes and commit with message"""
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
    """Pull current branch from remote"""
    verify_api_key(x_api_key)
    try:
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        result = _git(["pull", "origin", branch])
        return {"status": "success", "branch": branch, "output": result.stdout.strip()}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"git pull failed: {e.stderr}")


# Periodic sync worker
def sync_worker():
    while True:
        settings = load_settings()
        interval = settings.auto_sync_interval

        print(f"Background worker running... Interval: {interval} min")

        # 安全チェック: Vaultが空Forはsyncをスキップ
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

        # Auth check: トークン未設定Forは ob sync をスキップ
        if not _is_ob_auth_configured():
            msg = (
                "Obsidian Auth not configured: ~/.obsidian-headless/auth_token missing."
                "Run setup-obsidian-auth.sh to register OBSIDIAN_AUTH_TOKEN."
            )
            print(f"Background sync skipped: {msg}")
            _sync_status.update({
                "last_sync_at": datetime.now(timezone.utc).isoformat(),
                "last_sync_result": "skipped",
                "last_sync_message": msg,
            })
            time.sleep(interval * 60)
            continue

        # sync前にロックを解放してから実行（_ob_sync_lock で同時実行も防止）
        with _ob_sync_lock:
            clear_sync_lock()

            # Executing sync
            sync_command = [OB_CMD, "sync", "--path", VAULT_DIR]

            try:
                subprocess.run(sync_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
                print("Background sync successful.")
                _sync_status.update({
                    "last_sync_at": datetime.now(timezone.utc).isoformat(),
                    "last_sync_result": "success",
                    "last_sync_message": "",
                })
            except subprocess.CalledProcessError as e:
                stderr = e.stderr or ""
                # "Another sync instance" Transient state - clearing lock and skipping
                if "another sync instance" in stderr.lower() or "already running" in stderr.lower():
                    print("Background sync: another instance detected, clearing lock and retrying next interval.")
                    clear_sync_lock()
                    _sync_status.update({
                        "last_sync_at": datetime.now(timezone.utc).isoformat(),
                        "last_sync_result": "skipped",
                        "last_sync_message": "Skipped because another sync was running. Lock cleared.",
                    })
                else:
                    msg = _trim_error(stderr)
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

        # Wait for next interval
        time.sleep(interval * 60)

@app.on_event("startup")
def startup_event():
    global _startup_complete, _startup_phase

    _startup_phase = "Configuring SSH key"
    _log("▶ Phase 1/5: Setup SSH key")
    setup_ssh_key()

    _startup_phase = "Configuring Obsidian auth token"
    _log("▶ Phase 2/5: Setup Obsidian Auth Token")
    setup_obsidian_auth()

    _startup_phase = "Fetching Vault from GitHub"
    _log("▶ Phase 3/5: Clone or Update Vault from GitHub")
    init_vault_from_github()

    _startup_phase = "Setting up Obsidian Sync"
    _log("▶ Phase 4/5: ob sync-setup")
    setup_obsidian_vault()

    # ob sync-setup Clear lock again as sync-setup might create one
    clear_sync_lock()

    # Create settings file if missing on first boot
    if not os.path.exists(CONFIG_FILE):
        save_settings(load_settings())

    # Clear locks left by previous abnormal exit
    clear_sync_lock()

    _startup_phase = "Complete"
    _log("▶ Phase 5/5: Launch background worker")
    thread = threading.Thread(target=sync_worker, daemon=True)
    thread.start()

    _startup_complete = True
    _log("✅ Server startup complete")


def setup_ssh_key() -> None:
    """
    GIT_SSH_KEY 環境変数（PEM PEM formatted private key string）から
    一時ファイルを作成し、_GIT_SSH_KEY グローバル変数を更新する。
    Cloud Run Use value injected from Secret Manager in Cloud Run.
    """
    global _GIT_SSH_KEY
    git_ssh_key_content = os.getenv("GIT_SSH_KEY", "")
    if not git_ssh_key_content:
        # Environment variable not set: GIT_SSH_KEY_PATH Use existing file
        _log(f"GIT_SSH_KEY not set. Using key file: {_GIT_SSH_KEY}")
        return

    key_path = "/tmp/obsidian_sync_deploy_key"
    with open(key_path, "w") as f:
        # PEM Repair newlines turned into spaces（Cloud Run due to env var issues）
        content = git_ssh_key_content.replace("\\n", "\n")
        if not content.endswith("\n"):
            content += "\n"
        f.write(content)
    os.chmod(key_path, 0o600)
    _GIT_SSH_KEY = key_path
    _log(f"SSH key written to {key_path}")


def init_vault_from_github() -> None:
    """
    起動時に GITHUB_REPO_URL If set,
    vault/ initialize from GitHub repo.
    - vault/.git missing → git clone
    - vault/.git exists → git pull(updating)
    """
    github_repo = os.getenv("GITHUB_REPO_URL", "")
    if not github_repo:
        _log("GITHUB_REPO_URL not set. Skipping vault initialization from GitHub.")
        return

    # git User config (customizable via env var)
    git_name = os.getenv("GIT_USER_NAME", "Obsidian Sync Bot")
    git_email = os.getenv("GIT_USER_EMAIL", "obsidian-sync-bot@server")
    subprocess.run(["git", "config", "--global", "user.name", git_name], check=False)
    subprocess.run(["git", "config", "--global", "user.email", git_email], check=False)

    git_dir = os.path.join(VAULT_DIR, ".git")

    if os.path.isdir(git_dir):
        # Already initialized -> git pull
        _log(f"Vault already initialized at {VAULT_DIR}. Running git pull...")
        try:
            result = subprocess.run(
                ["git", "pull"],
                capture_output=True, text=True, check=True,
                cwd=VAULT_DIR, env=_git_env()
            )
            _log(f"git pull successful: {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            _log(f"Warning: git pull failed (continuing): {e.stderr.strip()}")
    else:
        # Not initialized -> git clone
        _log(f"Initializing vault from {github_repo} into {VAULT_DIR} ...")
        os.makedirs(VAULT_DIR, exist_ok=True)
        parent_dir = os.path.dirname(VAULT_DIR)
        vault_name = os.path.basename(VAULT_DIR)
        try:
            result = subprocess.run(
                ["git", "clone", github_repo, vault_name],
                capture_output=True, text=True, check=True,
                cwd=parent_dir, env=_git_env()
            )
            _log(f"git clone successful: {result.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            _log(f"git clone failed: {e.stderr.strip()}")
            _log("Vault initialization from GitHub failed. Server will start without vault.")


def setup_obsidian_auth() -> None:
    """
    OBSIDIAN_AUTH_TOKEN Restoring Obsidian Auth Token from env var.
    obsidian-headless Reads ~/.obsidian-headless/auth_token.
    Cloud Run Injected via Secret Manager in Cloud Run.

    Ref: https://forum.obsidian.md/t/headless-sync-how-to-get-obsidian-auth-token-variable/111740/2
    """
    token = os.getenv("OBSIDIAN_AUTH_TOKEN", "")
    if not token:
        _log("OBSIDIAN_AUTH_TOKEN not set. Obsidian Sync may not work without authentication.")
        return

    # obsidian-headless Path where token is read
    # Ref: https://forum.obsidian.md/t/headless-sync-how-to-get-obsidian-auth-token-variable/111740/
    auth_dir = os.path.expanduser("~/.obsidian-headless")
    os.makedirs(auth_dir, exist_ok=True)
    auth_file = os.path.join(auth_dir, "auth_token")

    with open(auth_file, "w") as f:
        f.write(token.strip())
    os.chmod(auth_file, 0o600)
    _log(f"Obsidian auth token written to: {auth_file}")


def setup_obsidian_vault() -> None:
    """
    OBSIDIAN_VAULT_ID If set and sync is not configured,
    ob sync-setup run for initial sync setup.

    ob sync-setup Safe to run multiple times with same vault ID.
    """
    vault_id = os.getenv("OBSIDIAN_VAULT_ID", "")
    if not vault_id:
        _log("OBSIDIAN_VAULT_ID not set. Skipping ob sync-setup.")
        return

    _log(f"Running ob sync-setup for vault: {vault_id} -> {VAULT_DIR}")
    try:
        result = subprocess.run(
            [OB_CMD, "sync-setup", "--vault", vault_id, "--path", VAULT_DIR],
            capture_output=True, text=True, check=True,
            cwd=VAULT_DIR
        )
        _log(f"ob sync-setup successful: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        _log(f"ob sync-setup failed: {_trim_error(e.stderr)}")
        _log("Obsidian Sync may not work. Check OBSIDIAN_VAULT_ID and OBSIDIAN_AUTH_TOKEN.")
    except FileNotFoundError:
        _log(f"ob command not found at: {OB_CMD}")
