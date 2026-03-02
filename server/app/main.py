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

@app.post("/api/sync/force")
def force_sync(x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    settings = load_settings()

    # 同期実行ロジック (obsidian-headless版)
    print(f"Executing force sync... sync_obsidian_config: {settings.sync_obsidian_config}")

    # 1. 構成設定の更新
    if settings.sync_obsidian_config:
        config_command = ["ob", "sync-config", "--configs", "app,appearance,appearance-data,hotkey,core-plugin,core-plugin-data,community-plugin,community-plugin-data"]
    else:
        config_command = ["ob", "sync-config", "--configs", ""]

    # 2. 同期の実行
    sync_command = ["ob", "sync"]

    try:
        config_result = subprocess.run(config_command, capture_output=True, text=True, check=True)
        sync_result = subprocess.run(sync_command, capture_output=True, text=True, check=True)
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

        # 1. 構成設定の更新
        if settings.sync_obsidian_config:
            config_command = ["ob", "sync-config", "--configs", "app,appearance,appearance-data,hotkey,core-plugin,core-plugin-data,community-plugin,community-plugin-data"]
        else:
            config_command = ["ob", "sync-config", "--configs", ""]

        # 2. 同期の実行
        sync_command = ["ob", "sync"]

        try:
            # バックグラウンド実行時はエラーを出力して次のループへ
            subprocess.run(config_command, capture_output=True, text=True, check=True)
            subprocess.run(sync_command, capture_output=True, text=True, check=True)
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

    # バックグラウンドワーカー起動
    thread = threading.Thread(target=sync_worker, daemon=True)
    thread.start()
