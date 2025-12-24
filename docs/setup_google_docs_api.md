# Google Docs API セットアップガイド

## 概要
このガイドでは、Shadow DirectorでGoogle Docs APIを有効化し、ドラフトを直接Google Docsとして作成できるようにする手順を説明します。

## 自動セットアップ（推奨）

デプロイスクリプト (`deploy_cloudrun.sh`) が以下を自動実行します：

1. **Google Docs API & Drive APIの有効化**
2. **Cloud Runサービスアカウントの取得**
3. **権限の確認と案内**

### 実行方法

WSL環境で以下を実行：

```bash
./deploy_cloudrun.sh
```

デプロイ完了後、以下のような出力が表示されます：

```
✅ Google Docs & Drive APIs enabled
✅ Service account configured

📝 Google Docs API Setup:
   The service account can now create Google Docs.
   By default, docs will be created in the service account's Drive.
   
   Service Account: 123456789-compute@developer.gserviceaccount.com
```

## 動作確認

### 1. API有効化の確認

```bash
gcloud services list --enabled --project=zenn-shadow-director | grep -E "docs|drive"
```

期待される出力：
```
docs.googleapis.com          Google Docs API
drive.googleapis.com         Google Drive API
```

### 2. ボットでテスト

Discordボットに以下のメッセージを送信：

```
トヨタ財団の研究助成に申請書を書いて
```

**期待される動作**:
- Google Docs APIが有効: `Google Docを作成: https://docs.google.com/document/d/...`
- GCSフォールバック: `GCSに保存: gs://...`

## Google Docsへのアクセス

### ボットが作成したドキュメントを閲覧するには

サービスアカウントが作成したGoogle Docsは、デフォルトではサービスアカウント自身のDriveに保存されます。

#### オプション1: サービスアカウントを共有相手に追加

Google Docs APIで作成時に共有設定を追加することで、特定のユーザーと自動共有できます。

**実装例** (`gdocs_tool.py`に追加):

```python
# ドキュメント作成後、共有
from googleapiclient.discovery import build

drive_service = build('drive', 'v3', credentials=creds)
permission = {
    'type': 'user',
    'role': 'writer',
    'emailAddress': 'your-email@example.com'
}
drive_service.permissions().create(
    fileId=doc_id,
    body=permission
).execute()
```

#### オプション2: 共有ドライブに作成

組織のGoogle Workspaceを使用している場合、共有ドライブに直接作成することも可能です。

#### オプション3: URLを返してユーザーが閲覧権限をリクエスト

現在の実装では、ドキュメントURLが返されます。ユーザーはそのURLにアクセスし、「アクセス権限をリクエスト」することで閲覧可能になります。

## トラブルシューティング

### エラー: "API has not been enabled"

デプロイスクリプトを再実行するか、手動で有効化：

```bash
gcloud services enable docs.googleapis.com --project=zenn-shadow-director
gcloud services enable drive.googleapis.com --project=zenn-shadow-director
```

### エラー: "Insufficient permissions"

サービスアカウントに権限がありません。以下で確認：

```bash
gcloud projects get-iam-policy zenn-shadow-director \
    --flatten="bindings[].members" \
    --filter="bindings.members:*compute@developer.gserviceaccount.com"
```

## ローカル開発でGoogle Docs APIを使う

ローカル環境では、Application Default Credentials (ADC)を使用します：

```bash
gcloud auth application-default login
```

その後、`.env`に以下を追加（オプション）：

```bash
# Google Docs APIを試す場合
USE_GOOGLE_DOCS_API=true
```

`gdocs_tool.py`は自動的にローカル認証情報を使用します。

## 今後の拡張案

- [ ] ドキュメント作成時に自動共有（ユーザーのメールアドレスを設定から取得）
- [ ] 共有ドライブ対応（組織のDriveに直接保存）
- [ ] ドキュメントテンプレート機能（フォーマット済みテンプレートを使用）
