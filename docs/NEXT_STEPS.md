# Remaining Tasks & Next Steps

プロジェクトの主要機能（Phase 1~6）の実装は完了しました。
完全な本番運用に向けて、以下のタスクが残されています。

## 1. Google Cloud Deployment (Production) - ✅ Complete
Cloud Run へのデプロイが完了し、サービスは正常に稼働しています。

- [x] **GCP Project Setup**:
    - Project: `zenn-shadow-director`
    - Region: `us-central1`
- [x] **Execute Deployment**:
    - Service URL: `https://shadow-director-bot-182793624818.us-central1.run.app`
- [ ] **Secret Management** (Recommended):
    - `DISCORD_BOT_TOKEN` などの機密情報を `Google Secret Manager` に登録し、Cloud Run から参照するように修正することを推奨します。
    - 現在は環境変数で注入されています。

## 2. Real-World Integration Tests
Mock Runner での検証は完了していますが、実際の Discord サーバーでの動作確認が必要です。

- [ ] **Discord Bot Hosting**:
    - デプロイした Cloud Run サービスのエンドポイント、または常時起動コンテナとして Discord Bot をオンラインにする。
    - 実際のユーザーアカウント（NPO代表者）との対話テスト。


## 3. Vertex AI Tuning
- [ ] **Prompt Engineering**:
    - 実際の対話ログを基に、System Prompt（特に `Interviewer` の深掘り質問や `Drafter` の文体）を微調整する。
- [ ] **Model Switch**:
    - `gemini-3-flash-preview` などの最新モデルが正式公開された際、モデルIDを更新する。
