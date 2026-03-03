from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import subprocess
import threading
import time

app = FastAPI(title="Obsidian Sync Server API")

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
            github_branch_patterns=["main", "master"]
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
            # バックグラウンド実行時はエラーを出力して次のループへ
            subprocess.run(config_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
            subprocess.run(sync_command, capture_output=True, text=True, check=True, cwd=VAULT_DIR)
            print("Background sync successful.")
        except subprocess.CalledProcessError as e:
            print(f"Background sync failed: {e.stderr}")
        except FileNotFoundError:
             print("obsidian-headless (ob) is not installed or not in PATH.")

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
