# Obsidian 3-Way Sync システム仕様書 (Settings-Integrated 版)

## 1. サーバー側：動的設定機能の追加

サーバー側に設定値を保存する `config.json` を用意し、API経由でプラグインから書き換え可能にします。

### A. 管理する設定項目（例）

*   `sync_obsidian_config` (boolean): `.obsidian` フォルダを同期対象に含めるかどうか。
*   `auto_sync_interval` (int): 自動同期のサイクル（分）。
*   `github_branch_patterns` (array): 同期対象とするブランチのホワイトリストなど。

### B. 設定用 API エンドポイント

| エンドポイント | メソッド | 説明 |
|---|---|---|
| `/api/settings` | GET | 現在のサーバー設定を取得。 |
| `/api/settings` | POST | 設定値を更新（`.obsidian` 同期のON/OFFなど）。 |
| `/api/sync/force` | POST | 強制フル同期を実行。 |

## 2. 同期ロジックの動的制御

サーバーの同期は、公式のヘッドレスクライアントである `obsidian-headless` (npmパッケージ) を利用します。
実行時に設定値（`sync_obsidian_config`）をチェックし、`ob sync-config` コマンドを使用して、`.obsidian`（設定）の同期有無を動的に切り替えます。

### 必要な環境変数・構成

*   `OBSIDIAN_AUTH_TOKEN`: `ob login` の代わりに使用する、非対話環境用の認証トークン。
*   `OBSIDIAN_VAULT_NAME` (or ID): 同期対象のVault名。
*   `OBSIDIAN_E2E_PASSWORD` (任意): エンドツーエンド暗号化のパスワード。

### 同期コマンドの流れ（擬似ロジック）

```bash
cd ./vault

# 1. プラグインから設定された sync_obsidian_config の値に応じて
#    ob sync-config コマンドで構成同期の有無を更新する。
if [ "$SYNC_OBSIDIAN_CONFIG" = "true" ]; then
  # 設定項目をすべて同期する（app, appearance, core-plugin, community-pluginなど）
  ob sync-config --configs "app,appearance,appearance-data,hotkey,core-plugin,core-plugin-data,community-plugin,community-plugin-data"
else
  # 設定項目の同期を無効化する（空文字を渡す）
  ob sync-config --configs ""
fi

# 2. 同期を実行する
#    Force Sync (手動) の場合:
ob sync

#    Auto Sync Worker (自動) の場合:
ob sync --continuous
```

## 3. iPhone/Mac 自作プラグイン：設定画面（Settings Tab）

プラグイン（**Obsidian Sync Bridge**）の設定画面を「サーバーのダッシュボード」として機能させます。

### A. 設定項目 UI

*   **Server URL**: 構築したサーバーのIPアドレスまたはドメイン。
*   **API Key**: 認証用のトークン。
*   **Sync Settings**:
    *   **Sync .obsidian folder**: トグルスイッチ。これを切り替えるとサーバーの API を叩き、サーバー側の挙動が即座に変わります。
    *   **Sync Interval**: 数値入力。
*   **Maintenance**:
    *   **Force Full Sync**: サーバー側で強制的な `push --force` を実行させるボタン。

## 4. Web管理画面の役割

Macのブラウザから開くWeb画面も、プラグインの設定画面と同じ API を共有します。

*   **用途**: Obsidianを開いていない状態でも、ブラウザから現在の同期ステータスを確認したり、緊急でブランチを切り替えたりするために利用します。

## 5. 修正版：システム全体の連携フロー

1.  **プラグインで設定変更**:
    iPhoneのObsidian設定画面で「Sync .obsidian」をONにする。
2.  **サーバーへ通知**:
    プラグインが `/api/settings` (POST) を叩き、サーバーの `config.json` が更新される。
3.  **次回同期からの反映**:
    サーバーが設定を読み込み、`ob sync-config --configs "..."` コマンドを発行して構成設定の同期状態を更新した上で、`ob sync` による同期を行う。

## 6. 技術的なポイント：設定の永続化

サーバー側は Docker で動かす際、設定ファイルを **Volume マウント** しておくことで、コンテナを再起動してもプラグインから設定した内容（`.obsidian` 同期のON/OFFなど）が消えないようにします。
