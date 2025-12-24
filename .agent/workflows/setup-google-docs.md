---
description: Google Docs APIの有効化確認と動作テスト
---

# Google Docs API セットアップワークフロー

## 1. APIの有効化確認

```bash
gcloud services list --enabled --project=zenn-shadow-director | grep -E "docs|drive"
```

期待される出力：
```
docs.googleapis.com          Google Docs API
drive.googleapis.com         Google Drive API
```

## 2. 有効化されていない場合

```bash
gcloud services enable docs.googleapis.com --project=zenn-shadow-director
gcloud services enable drive.googleapis.com --project=zenn-shadow-director
```

## 3. サービスアカウントの確認

```bash
# Cloud Runで使用されているサービスアカウントを取得
gcloud run services describe shadow-director-bot \
    --region=us-central1 \
    --platform=managed \
    --format="value(spec.template.spec.serviceAccountName)"
```

デフォルトでは空（Compute Engine デフォルトサービスアカウント使用）

## 4. デプロイして確認

// turbo
```bash
cd /mnt/c/Users/keisu/workspace/shadow-director
./deploy_cloudrun.sh
```

## 5. ボットで動作確認

Discordボットに以下を送信して、Google Docsが作成されることを確認：

```
トヨタ財団の助成金に申請書を書いて
```

期待される返答：
- `Google Docを作成: https://docs.google.com/document/d/...` （API有効時）
- `GCSに保存: gs://...` （フォールバック時）

## トラブルシューティング

### ローカルでテストしたい場合

```bash
# ADCでログイン
gcloud auth application-default login

# Pythonでテスト
python -c "from src.tools.gdocs_tool import GoogleDocsTool; tool = GoogleDocsTool(); print(tool.docs_service)"
```

`None`以外が表示されればAPI認証成功
