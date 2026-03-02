import pytest
from fastapi.testclient import TestClient
import os
import json

# テスト前に環境変数を設定してテスト用の一時ファイルを使用する
TEST_CONFIG_FILE = "./data/test_config.json"
os.environ["CONFIG_FILE"] = TEST_CONFIG_FILE
os.environ["API_KEY"] = "test-secret-key"

from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # 各テストの前にファイルを削除しておく
    if os.path.exists(TEST_CONFIG_FILE):
        os.remove(TEST_CONFIG_FILE)

    # app.on_event("startup") を手動で呼び出す（TestClientの起動イベントと重複しないように注意）
    # 今回のアプリでは startup_event() がスレッドを起動するため、
    # 影響を避けるため設定ファイルの作成だけをモック的に行うこともできますが、
    # 簡単のためにまずはファイルなしの状態から始めます。

    yield

    # テスト後にファイルを削除
    if os.path.exists(TEST_CONFIG_FILE):
        os.remove(TEST_CONFIG_FILE)

def test_get_settings_without_api_key():
    response = client.get("/api/settings")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API Key"}

def test_get_settings_with_invalid_api_key():
    response = client.get("/api/settings", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API Key"}

def test_get_settings_default():
    # デフォルトの設定が返ってくるか
    response = client.get("/api/settings", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["sync_obsidian_config"] == False
    assert data["auto_sync_interval"] == 60
    assert data["github_branch_patterns"] == ["main", "master"]

def test_update_settings():
    new_settings = {
        "sync_obsidian_config": True,
        "auto_sync_interval": 30,
        "github_branch_patterns": ["main", "dev"]
    }
    response = client.post(
        "/api/settings",
        headers={"X-API-Key": "test-secret-key"},
        json=new_settings
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sync_obsidian_config"] == True
    assert data["auto_sync_interval"] == 30

    # 更新された設定が正しく取得できるか確認
    response_get = client.get("/api/settings", headers={"X-API-Key": "test-secret-key"})
    data_get = response_get.json()
    assert data_get["sync_obsidian_config"] == True
    assert data_get["auto_sync_interval"] == 30

def test_force_sync_without_api_key():
    response = client.post("/api/sync/force")
    assert response.status_code == 401

from unittest.mock import patch, MagicMock

@patch("subprocess.run")
def test_force_sync_execution(mock_run):
    # subprocess.runをモック化
    mock_result = MagicMock()
    mock_result.stdout = "Mocked Output"
    mock_run.return_value = mock_result

    # 同期実行のテスト
    response = client.post("/api/sync/force", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    # モックの出力が含まれているか
    assert "Mocked Output" in data["output"]

    # コマンドの引数チェック
    calls = mock_run.call_args_list
    assert len(calls) == 2
    # デフォルト設定(False)では config を空にしているはず
    assert calls[0][0][0] == ["ob", "sync-config", "--configs", ""]
    assert calls[1][0][0] == ["ob", "sync"]

@patch("subprocess.run")
def test_force_sync_execution_with_obsidian_sync(mock_run):
    # subprocess.runをモック化
    mock_result = MagicMock()
    mock_result.stdout = "Mocked Output"
    mock_run.return_value = mock_result

    # 設定を変更して .obsidian を同期対象にする
    new_settings = {
        "sync_obsidian_config": True,
        "auto_sync_interval": 60,
        "github_branch_patterns": ["main"]
    }
    client.post("/api/settings", headers={"X-API-Key": "test-secret-key"}, json=new_settings)

    # 同期実行
    response = client.post("/api/sync/force", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # コマンドの引数チェック
    calls = mock_run.call_args_list
    assert len(calls) == 2
    # True の場合は全 config を指定しているはず
    assert calls[0][0][0] == ["ob", "sync-config", "--configs", "app,appearance,appearance-data,hotkey,core-plugin,core-plugin-data,community-plugin,community-plugin-data"]
    assert calls[1][0][0] == ["ob", "sync"]
