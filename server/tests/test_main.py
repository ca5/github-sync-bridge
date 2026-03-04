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
    yield
    if os.path.exists(TEST_CONFIG_FILE):
        os.remove(TEST_CONFIG_FILE)

# =========================================================
# 既存: Settings API
# =========================================================

def test_get_settings_without_api_key():
    response = client.get("/api/settings")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API Key"}

def test_get_settings_with_invalid_api_key():
    response = client.get("/api/settings", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API Key"}

def test_get_settings_default():
    response = client.get("/api/settings", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["sync_obsidian_config"] == False
    assert data["auto_sync_interval"] == 60
    assert data["github_branch_patterns"] == []

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

    response_get = client.get("/api/settings", headers={"X-API-Key": "test-secret-key"})
    data_get = response_get.json()
    assert data_get["sync_obsidian_config"] == True
    assert data_get["auto_sync_interval"] == 30

def test_force_sync_without_api_key():
    response = client.post("/api/sync/force")
    assert response.status_code == 401

from unittest.mock import patch, MagicMock, call
import subprocess

def _make_proc(stdout="", returncode=0):
    """subprocess.CompletedProcess のモックを作成するヘルパー"""
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m

@patch("subprocess.run")
def test_force_sync_execution(mock_run):
    mock_result = MagicMock()
    mock_result.stdout = "Mocked Output"
    mock_run.return_value = mock_result

    response = client.post("/api/sync/force", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "Mocked Output" in data["output"]

    calls = mock_run.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0][1:] == ["sync-config", "--configs", ""]
    assert calls[1][0][0][1:] == ["sync"]

@patch("subprocess.run")
def test_force_sync_execution_with_obsidian_sync(mock_run):
    mock_result = MagicMock()
    mock_result.stdout = "Mocked Output"
    mock_run.return_value = mock_result

    new_settings = {
        "sync_obsidian_config": True,
        "auto_sync_interval": 60,
        "github_branch_patterns": ["main"]
    }
    client.post("/api/settings", headers={"X-API-Key": "test-secret-key"}, json=new_settings)

    response = client.post("/api/sync/force", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    calls = mock_run.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0][1:] == ["sync-config", "--configs", "app,appearance,appearance-data,hotkey,core-plugin,core-plugin-data,community-plugin,community-plugin-data"]
    assert calls[1][0][0][1:] == ["sync"]

# =========================================================
# Git API: 認証チェック
# =========================================================

def test_git_status_without_api_key():
    assert client.get("/api/git/status").status_code == 401

def test_git_branches_without_api_key():
    assert client.get("/api/git/branches").status_code == 401

def test_git_checkout_without_api_key():
    assert client.post("/api/git/checkout", json={"branch": "main"}).status_code == 401

def test_git_commit_without_api_key():
    assert client.post("/api/git/commit", json={"message": "test"}).status_code == 401

def test_git_push_without_api_key():
    assert client.post("/api/git/push").status_code == 401

def test_git_pull_without_api_key():
    assert client.post("/api/git/pull").status_code == 401

# =========================================================
# Git API: /api/git/status
# =========================================================

@patch("app.main._git")
def test_git_status_clean(mock_git):
    """クリーンな状態を正しく返す"""
    mock_git.side_effect = [
        _make_proc("main\n"),   # rev-parse
        _make_proc(""),         # status --short (clean)
    ]
    response = client.get("/api/git/status", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["branch"] == "main"
    assert data["changed_files"] == []
    assert data["is_clean"] == True

@patch("app.main._git")
def test_git_status_with_changes(mock_git):
    """変更ファイルがある状態を正しく返す"""
    mock_git.side_effect = [
        _make_proc("feature-x\n"),
        _make_proc(" M journal/2026/03/04.md\n?? new_note.md\n"),
    ]
    response = client.get("/api/git/status", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["branch"] == "feature-x"
    assert len(data["changed_files"]) == 2
    assert data["is_clean"] == False

@patch("app.main._git")
def test_git_status_git_error(mock_git):
    """git コマンド失敗時に 500 を返す"""
    mock_git.side_effect = subprocess.CalledProcessError(128, "git", stderr="not a git repo")
    response = client.get("/api/git/status", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 500
    assert "git status failed" in response.json()["detail"]

# =========================================================
# Git API: /api/git/branches
# =========================================================

@patch("app.main._git")
def test_git_branches_success(mock_git):
    """ローカル + リモートのブランチを重複なく返す"""
    mock_git.side_effect = [
        _make_proc("main\n"),                          # rev-parse
        _make_proc("main\nfeature-x\n"),               # branch local
        _make_proc("origin/main\norigin/feature-x\norigin/HEAD\n"),  # branch -r
    ]
    response = client.get("/api/git/branches", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["current"] == "main"
    assert "main" in data["branches"]
    assert "feature-x" in data["branches"]
    # origin/HEAD は含まれない
    assert "HEAD" not in data["branches"]
    # 重複なし
    assert len(data["branches"]) == len(set(data["branches"]))

# =========================================================
# Git API: /api/git/checkout
# =========================================================

@patch("app.main._git")
def test_git_checkout_success(mock_git):
    """クリーンな状態でブランチ切り替えが成功する"""
    mock_git.side_effect = [
        _make_proc(""),                          # status --short (clean)
        _make_proc("Switched to branch 'feature-x'\n"),  # checkout
        _make_proc("Already up to date.\n"),     # pull
    ]
    response = client.post(
        "/api/git/checkout",
        headers={"X-API-Key": "test-secret-key"},
        json={"branch": "feature-x"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["branch"] == "feature-x"
    assert "Already up to date" in data["pull_output"]

@patch("app.main._git")
def test_git_checkout_dirty_fails(mock_git):
    """未コミット変更がある状態では 409 を返す"""
    mock_git.side_effect = [
        _make_proc(" M journal/2026/03/04.md\n"),  # status --short (dirty)
    ]
    response = client.post(
        "/api/git/checkout",
        headers={"X-API-Key": "test-secret-key"},
        json={"branch": "feature-x"}
    )
    assert response.status_code == 409
    assert "Uncommitted changes" in response.json()["detail"]

    # status だけが呼ばれ、checkout は呼ばれていない
    assert mock_git.call_count == 1

# =========================================================
# Git API: /api/git/commit
# =========================================================

@patch("app.main._git")
def test_git_commit_success(mock_git):
    """コミットが成功する"""
    mock_git.side_effect = [
        _make_proc(""),                                     # add -A
        _make_proc("[main abc1234] my commit\n 1 file changed\n"),  # commit
    ]
    response = client.post(
        "/api/git/commit",
        headers={"X-API-Key": "test-secret-key"},
        json={"message": "my commit"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "my commit" in data["output"]

@patch("app.main._git")
def test_git_commit_nothing_to_commit(mock_git):
    """コミットするものがない場合は 500 を返す"""
    mock_git.side_effect = [
        _make_proc(""),   # add -A (成功)
        subprocess.CalledProcessError(1, "git commit", stderr="", output="nothing to commit"),
    ]
    response = client.post(
        "/api/git/commit",
        headers={"X-API-Key": "test-secret-key"},
        json={"message": "empty commit"}
    )
    assert response.status_code == 500
    assert "git commit failed" in response.json()["detail"]

# =========================================================
# Git API: /api/git/push
# =========================================================

@patch("app.main._git")
def test_git_push_success(mock_git):
    """push が成功する"""
    mock_git.side_effect = [
        _make_proc("main\n"),           # rev-parse
        _make_proc("To github.com:ca5/obsidian\n   abc..def  main -> main\n"),  # push
    ]
    response = client.post("/api/git/push", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["branch"] == "main"

@patch("app.main._git")
def test_git_push_failure(mock_git):
    """push 失敗時に 500 を返す"""
    mock_git.side_effect = [
        _make_proc("main\n"),
        subprocess.CalledProcessError(1, "git push", stderr="Permission denied (publickey)."),
    ]
    response = client.post("/api/git/push", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 500
    assert "git push failed" in response.json()["detail"]

# =========================================================
# Git API: /api/git/pull
# =========================================================

@patch("app.main._git")
def test_git_pull_success(mock_git):
    """pull が成功する"""
    mock_git.side_effect = [
        _make_proc("main\n"),
        _make_proc("Already up to date.\n"),
    ]
    response = client.post("/api/git/pull", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["branch"] == "main"
    assert "Already up to date" in data["output"]

@patch("app.main._git")
def test_git_pull_failure(mock_git):
    """pull 失敗時に 500 を返す"""
    mock_git.side_effect = [
        _make_proc("main\n"),
        subprocess.CalledProcessError(1, "git pull", stderr="CONFLICT: Merge conflict"),
    ]
    response = client.post("/api/git/pull", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 500
    assert "git pull failed" in response.json()["detail"]
