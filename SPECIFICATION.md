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

サーバーの同期スクリプト実行時に、設定値（`sync_obsidian_config`）をチェックしてコマンドを分岐させます。

```bash
# 擬似ロジック
if [ "$SYNC_OBSIDIAN_CONFIG" = "true" ]; then
  # 全て同期
  obsidian-sync push ./vault
else
  # .obsidian を除外して同期
  obsidian-sync push ./vault --ignore ".obsidian/*"
fi
```

## 3. iPhone/Mac 自作プラグイン：設定画面（Settings Tab）

プラグインの設定画面を「サーバーのダッシュボード」として機能させます。

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
    サーバーの定期実行スクリプトが設定を読み込み、`obsidian-sync` の実行引数から `--ignore ".obsidian/*"` を外す。

## 6. 技術的なポイント：設定の永続化

サーバー側は Docker で動かす際、設定ファイルを **Volume マウント** しておくことで、コンテナを再起動してもプラグインから設定した内容（`.obsidian` 同期のON/OFFなど）が消えないようにします。
