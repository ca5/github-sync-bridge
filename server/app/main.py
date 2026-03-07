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

# 起動完了フラグ — False の間は初期化中なので 503 を返す
_startup_complete: bool = False
_startup_phase: str = "初期化中..."

@app.middleware("http")
async def startup_guard(request: Request, call_next):
    """
    起動完了前は /api/health 以外すべてのエンドポイントに 503 を返す。
    Cloud Run で min-instances=0 の場合、コールドスタート時に git clone 等が
    完了するまでプラグインを待機させるため。
    """
    if not _startup_complete:
        allow_paths = {"/api/health", "/docs", "/openapi.json", "/redoc"}
        if request.url.path not in allow_paths:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "initializing",
                    "phase": _startup_phase,
                    "message": f"サーバー起動中: {_startup_phase}",
                    "startup_log": _startup_log[-10:],
                }
            )
    return await call_next(request)

# 同期ステータスをメモリで管理
_sync_status = {
    "last_sync_at": None,       # 最終sync実行時刻 (ISO8601)
    "last_sync_result": None,   # "success" | "failed" | "skipped"
    "last_sync_message": "",    # エラーメッセージなど
    "is_vault_ready": False,    # Vaultが同期可能な状態か
}

# 起動時のログ（最新 50 件）— プラグイン側から /api/sync/status で参照可能
_startup_log: list[str] = []

def _log(msg: str) -> None:
    """startup中のメッセージを標準出力とメモリ両方に記録する"""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    _startup_log.append(line)
    if len(_startup_log) > 50:
        _startup_log.pop(0)

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

@app.get("/api/health")
def health_check():
    """認証不要・常に応答するヘルスチェック。プラグインが起動完了を確認するのに使う。"""
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

def clear_sync_lock() -> None:
    """
    ob sync のステールロックをすべて削除する。

    削除対象:
      1. vault/.obsidian/.sync.lock  (obsidian-headless が使う vault 内ロック)
      2. ~/.obsidian-headless/sync/ 配下の *.lock ファイル

    注意: os.rmdir() は空でないディレクトリを削除できないため
          shutil.rmtree() を使用する。
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
    Node.js のミニファイコード / ファイルパスが stderr に入り込む場合に対応。
    優先度: Error: を含む行 > ファイルパス以外の行 > 最初の行
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
        # 80 文字以上かつセミコロンが多い行 = ミニファイコード
        return len(line) > 80 and line.count(';') > 5

    # Error: を含む行を優先
    error_lines = [l for l in lines if 'Error' in l or 'error:' in l.lower()]
    if error_lines:
        best = error_lines[0]
    else:
        # JSファイルパスとミニファイ行を除いた最初の行
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
    # 未コミット変更がある場合の処理方法
    # - "stash"       : stash して新ブランチに引き継ぐ
    # - "commit_push" : コミットして push してから切り替える
    # - "discard"     : 変更を捨ててから切り替える
    mode: str = "stash"        # デフォルト: stash
    commit_message: str = ""   # mode=commit_push の場合に使うコミットメッセージ

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
    """
    ブランチを切り替える。切り替え後に git pull を実行。
    mode によって未コミット変更の処理方法を選択できる。
    """
    verify_api_key(x_api_key)
    try:
        # 未コミット変更チェック（未追跡ファイル「??」は git checkout をブロックしないため除外）
        status_lines = _git(["status", "--short"]).stdout.strip().splitlines()
        tracked_changes = [line for line in status_lines if line and not line.startswith("??")]

        note = ""

        if tracked_changes:
            if req.mode == "stash":
                # 変更を stash して新ブランチに引き継ぐ
                _git(["stash", "push", "-m", f"auto-stash before checkout {req.branch}"])
                # checkout 後に pop——後ステップで実行
                note = "__stash_pop__"  # 後フラグ

            elif req.mode == "commit_push":
                # コミットメッセージが空の場合は自動生成
                msg = req.commit_message.strip() or f"auto-commit before checkout {req.branch}"
                _git(["add", "-A"])
                _git(["commit", "-m", msg])
                current_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
                _git(["push", "origin", current_branch])
                note = f"\u5225ブランチ ({current_branch}) にコミット・ Push しました"

            elif req.mode == "discard":
                # 追跡済み変更を廣棄（untracked は clean -fd で別途対処）
                _git(["checkout", "--", "."])
                _git(["clean", "-fd"])
                note = "未コミットの変更を破棄しました"

            else:
                raise HTTPException(status_code=400, detail=f"Unknown mode: {req.mode}")

        # ブランチ切り替え（リモートにしかない場合は自動でトラッキング）
        _git(["checkout", "-B", req.branch, f"origin/{req.branch}"])
        # git pull
        pull_result = _git(["pull", "origin", req.branch])

        # stash pop（mode=stash の場合）
        if note == "__stash_pop__":
            try:
                _git(["stash", "pop"])
                note = "変更を新ブランチに引き継ぎました"
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

        # 認証チェック: トークン未設定の場合は ob sync をスキップ
        if not _is_ob_auth_configured():
            msg = (
                "Obsidian 認証未設定: ~/.obsidian-headless/auth_token がありません。"
                "setup-obsidian-auth.sh を実行して OBSIDIAN_AUTH_TOKEN を登録してください。"
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
                stderr = e.stderr or ""
                # "Another sync instance" は一時的な状態なのでロック削除してスキップ扱いにする
                if "another sync instance" in stderr.lower() or "already running" in stderr.lower():
                    print("Background sync: another instance detected, clearing lock and retrying next interval.")
                    clear_sync_lock()
                    _sync_status.update({
                        "last_sync_at": datetime.now(timezone.utc).isoformat(),
                        "last_sync_result": "skipped",
                        "last_sync_message": "別の同期プロセスが実行中だったため、ロックを解除しました。次回のインターバルで再同期します。",
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

        # 次のインターバルまで待機
        time.sleep(interval * 60)

@app.on_event("startup")
def startup_event():
    global _startup_complete, _startup_phase

    _startup_phase = "SSH 鍵の設定中"
    _log("▶ 起動フェーズ 1/5: SSH 鍵の設定")
    setup_ssh_key()

    _startup_phase = "Obsidian 認証トークンの設定中"
    _log("▶ 起動フェーズ 2/5: Obsidian 認証トークンの設定")
    setup_obsidian_auth()

    _startup_phase = "Vault を GitHub から取得中"
    _log("▶ 起動フェーズ 3/5: vault の変更定込または clone")
    init_vault_from_github()

    _startup_phase = "Obsidian Sync のセットアップ中"
    _log("▶ 起動フェーズ 4/5: ob sync-setup")
    setup_obsidian_vault()

    # ob sync-setup が内部でロックを作る場合があるため、再度クリアする
    clear_sync_lock()

    # 初回起動時に設定ファイルがなければ作成
    if not os.path.exists(CONFIG_FILE):
        save_settings(load_settings())

    # 前回の異常終了 (--reload 等) で残ったロックを削除
    clear_sync_lock()

    _startup_phase = "完了"
    _log("▶ 起動フェーズ 5/5: バックグラウンドワーカー起動")
    thread = threading.Thread(target=sync_worker, daemon=True)
    thread.start()

    _startup_complete = True
    _log("✅ サーバー起動完了")


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
        _log(f"GIT_SSH_KEY not set. Using key file: {_GIT_SSH_KEY}")
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
    _log(f"SSH key written to {key_path}")


def init_vault_from_github() -> None:
    """
    起動時に GITHUB_REPO_URL が設定されている場合、
    vault/ を GitHub リポジトリから自動初期化する。
    - vault/.git がない → git clone
    - vault/.git がある → git pull（最新化）
    """
    github_repo = os.getenv("GITHUB_REPO_URL", "")
    if not github_repo:
        _log("GITHUB_REPO_URL not set. Skipping vault initialization from GitHub.")
        return

    # git ユーザー設定（環境変数でカスタマイズ可）
    git_name = os.getenv("GIT_USER_NAME", "Obsidian Sync Bot")
    git_email = os.getenv("GIT_USER_EMAIL", "obsidian-sync-bot@server")
    subprocess.run(["git", "config", "--global", "user.name", git_name], check=False)
    subprocess.run(["git", "config", "--global", "user.email", git_email], check=False)

    git_dir = os.path.join(VAULT_DIR, ".git")

    if os.path.isdir(git_dir):
        # 既に初期化済み→ pull して最新化
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
        # 未初期化 → git clone
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
    OBSIDIAN_AUTH_TOKEN 環境変数から Obsidian の認証トークンを復元する。
    obsidian-headless は ~/.config/obsidian-headless/auth_token を読む。
    Cloud Run では Secret Manager 経由でこの env var に注入する。

    参考: https://forum.obsidian.md/t/headless-sync-how-to-get-obsidian-auth-token-variable/111740/2
    """
    token = os.getenv("OBSIDIAN_AUTH_TOKEN", "")
    if not token:
        _log("OBSIDIAN_AUTH_TOKEN not set. Obsidian Sync may not work without authentication.")
        return

    # obsidian-headless がトークンを読むパス
    # 参考: https://forum.obsidian.md/t/headless-sync-how-to-get-obsidian-auth-token-variable/111740/
    auth_dir = os.path.expanduser("~/.obsidian-headless")
    os.makedirs(auth_dir, exist_ok=True)
    auth_file = os.path.join(auth_dir, "auth_token")

    with open(auth_file, "w") as f:
        f.write(token.strip())
    os.chmod(auth_file, 0o600)
    _log(f"Obsidian auth token written to: {auth_file}")


def setup_obsidian_vault() -> None:
    """
    OBSIDIAN_VAULT_ID が設定されていて、かつ vault の sync 設定がされていない場合に
    ob sync-setup を実行して Obsidian Sync を使えるようにする。

    ob sync-setup は同じ vault ID + path の組み合わせで何度実行しても安全。
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
