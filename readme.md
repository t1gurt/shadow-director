# 🤝 NPO-SoulSync Agent: The Autonomous "Shadow Director"

**「熱意はあるが、時間がない」すべてのソーシャルリーダーへ。**

Google Cloud の最先端（Gemini 3.0 & Vertex AI）を駆使し、あなたの「魂（Soul）」を学習・自律行動する、分身パートナー。

[![Built with Google Cloud](https://img.shields.io/badge/Built_with-Google_Cloud-4285F4?logo=google-cloud)](https://cloud.google.com/vertex-ai)
[![Gemini 3.0](https://img.shields.io/badge/Gemini-3.0_Pro-orange)](https://deepmind.google/technologies/gemini/)

## 📖 概要 (Overview)

NPO法人の代表者は、想いと行動力を持ちながらも、常に事務作業とリソース不足に忙殺されています。

本プロダクトは、従来の「人間が使うツール」ではありません。Discord上に常駐し、代表者の「判断基準」と「原体験」を深い対話を通じて学習。その後は **"Shadow Director（影の事務局長）"** として、自律的に外部環境を監視し、チャンスを掴み取りに行きます。

本プロジェクトは、**Google Gemini 3.0 Pro** の推論能力と **Vertex AI** のマネージド機能を極限まで引き出した、次世代の自律型エージェント（Agentic AI）実装です。

## 🏆 Zenn Agentic AI Hackathon 第4回

**Theme:** Agentic AI (自律性・推論・ツール利用・マルチエージェント協調)

### 最先端技術スタック:

- **Gemini 3.0 Pro (Preview)**: 圧倒的な推論・コーディング能力で、複雑な文脈理解とドラフト作成を担当
- **Gemini 3.0 Flash (Preview)**: コストと速度のバランスに優れ、常時監視エージェントとして採用
- **Vertex AI**: Google Cloudの最新AIプラットフォーム、本番グレードのスケーラビリティを提供
- **Google Search Grounding**: Dynamic Retrievalによるリアルタイム情報取得
- **Google Cloud Run**: フルマネージドなコンテナ実行環境、自動スケーリング対応

## ✨ 実装済み機能 (Implemented Features)

### 1. 🗣️ The Soul Sync (Interview Agent) - ✅ Implemented

**「設定ファイルは書かない。対話して、魂を同期する。」**

- **Tech:** Gemini 3.0 Pro + GCS Storage
- **Features:**
  - **PDF/URLドキュメント分析**: 定款・団体HPなどを自動読み込み・理解
  - **Active Inquiry**: AIが「書かれていない代表の想い（原体験）」を特定し、核心を突く質問を投げかける
  - **選択的ターンカウント**: 挨拶や補足説明はカウントせず、実質的なインタビュー質問のみを15問でカウント
  - **構造化プロファイル**: 対話結果を構造化し、GCS (Google Cloud Storage) に永続化
  - **会話履歴管理**: ターン数とコンテキストを保持し、自然な対話を実現
  - **申請書特化モード**: 団体詳細（予算・スタッフ等）やプロジェクト構想（5W1H）を深掘りインタビューし、申請書作成に直結する情報を収集

### 2. 🦅 Autonomous Funding Watch (Observer Agent) - ✅ Implemented

**「あなたが寝ている間に、チャンスを見つけ出す。」**

- **Tech:** Gemini 3.0 Flash + Google Search Grounding + Playwright + **SGNAモデル**
- **Features:**
  - **SGNAモデル（Search-Ground-Navigate-Act）**: 助成金検索の精度と信頼性を大幅に向上
    - **Site Restrictions**: 信頼ドメイン（go.jp/or.jp/lg.jp/co.jp/org/com）を優先検索
    - **Landing Page Priority**: PDFへの直リンクより公募ページを優先
    - **Progressive Wait**: networkidle → domcontentloaded → load の段階的待機
    - **Rate Limiting**: 政府系サイトへの1秒遅延でサーバー配慮
  - **Accessibility Tree Parsing**: CSSセレクタに依存しないセマンティックリンク検索
  - **File Validation Loop**: PDF/ZIPのダウンロード後に年度・公募回を自動検証
  - **Error Recovery**: ポップアップ自動クローズ、代替URL自動試行
  - **Playwright Site Explorer**: DOM解析によるサイト深掘り検索、フォーマットファイル自動検出
  - **Resonance Reasoning**: 財団の理念と自団体の「Soul Profile」の共鳴度（マッチ度）を推論
  - **週次スケジュール**: Discord Tasks Loopによる定期実行（168時間/週）

### 3. ✍️ Shadow Drafter (Action Agent) - ✅ Implemented

**「『とりあえず書いておいたよ』と言えるエージェント。」**

- **Tech:** Gemini 3.0 Pro + Google Docs API / GCS
- **Features:**
  - **自動ドラフト生成**: Soul Profileを基に助成金申請書のドラフトを作成
  - **3層保存ストレージ**:
    1. Google Docs API: 認証情報があればGoogle Docとして直接作成
    2. GCS: Production環境で `gs://{bucket}/drafts/{user_id}/` に永続化
    3. ローカル: 開発環境で `drafts/` フォルダにフォールバック
  - **インテリジェントルーティング**: ユーザーの発言から「DRAFT」意図を自動検出
  - **Word/Excel項目別入力**: Gemini 3.0 Flashで各項目をプロファイル情報をもとに個別生成し、高精度な自動入力
  - **Word入力パターン高精度検出**: VLM (Vision-Language Model) により、`line` / `next_line` / `underline` / `bracket` / `table` 等の入力パターンを視覚的に識別し、正確に記入
  - **Strong Match自動生成**: Observer検出時（共鳴度70+）に自動でドラフトを作成

### 4. 🛡️ Production-Ready Infrastructure - ✅ Implemented

- **Cloud Run Deployment**: フルマネージド、自動スケーリング
  - **Single Instance Mode**: Discord Bot用に `max-instances=1` 設定で重複接続を防止
  - **Always-On**: `min-instances=1` でコールドスタート防止
- **GCS Storage**: プロファイルデータの永続化（`gs://zenn-shadow-director-data`）
- **Health Check**: HTTP ヘルスチェックサーバー内蔵
- **Message Deduplication**: メッセージIDベースの重複処理防止機構

## 🏗️ システム構成 (Architecture)

現在の実装は、Google Cloud上で動作するシンプルかつスケーラブルな構成です。

```mermaid
graph TD
    User((NPO Representative)) -->|Chat & Upload| Discord
    
    subgraph "Interface Layer"
        Discord[Discord Bot]
    end

    subgraph "Brain Layer (Cloud Run)"
        Discord -->|Message Event| Orchestrator[Orchestrator Agent]
        
        Orchestrator -->|Route: INTERVIEW| Interviewer[Interviewer Agent]
        Orchestrator -->|Route: OBSERVE| Observer[Observer Agent]
        Orchestrator -->|Route: DRAFT| Drafter[Drafter Agent]
        Orchestrator -->|Route: PR| PRAgent[PR Agent]
        
        subgraph "Vertex AI Backend"
            GeminiClient[Gemini Client Factory]
            GeminiClient -->|vertexai=True| VertexAI[Vertex AI API]
            VertexAI --> GeminiPro[Gemini 3.0 Pro]
            VertexAI --> GeminiFlash[Gemini 3.0 Flash]
        end
        
        Interviewer --> GeminiClient
        Observer --> GeminiClient
        Drafter --> GeminiClient
        PRAgent --> GeminiClient
        
        GeminiFlash -->|Grounding| GoogleSearch[Google Search]
    end

    subgraph "SGNA Model (Search-Ground-Navigate-Act)"
        Observer -->|Search| GrantFinder[Grant Finder]
        GrantFinder -->|Navigate| Playwright[Playwright Browser]
        Playwright -->|Act| PageScraper[Grant Page Scraper]
        PageScraper -->|Validate| FileValidator[File Validator]
        PageScraper -.->|Fallback| VisualAnalyzer[Visual Analyzer]
    end

    subgraph "Storage Layer"
        Interviewer <-->|Save/Load Profile| GCS[(Google Cloud Storage)]
        Observer <-->|Read Profile| GCS
        Drafter <-->|Read Profile| GCS
    end

    subgraph "Action Layer"
        Drafter -->|Create Doc| GDocs[Google Docs API]
        Orchestrator -->|Send Response| Discord
    end
    
    subgraph "Scheduling"
        Tasks[Discord Tasks Loop] -->|Weekly Trigger| Observer
    end
```

## 🛠️ 技術スタック (Tech Stack)

### LLM & AI
- **Gemini 3.0 Pro (Preview)**: 推論・執筆・戦略立案（インタビュアー、ドラフター）
- **Gemini 3.0 Flash (Preview)**: チャット・検索・一次選別（オブザーバー）
- **Google Search Grounding**: リアルタイム情報検索
- **Playwright**: ヘッドレスブラウザによるDOM解析・サイト探索

### Platform & Infrastructure
- **Google Cloud Run**: フルマネージドコンテナ実行環境
  - Region: `us-central1`
  - Instances: `min=1, max=1` (Discord Bot用シングルトン構成)
  - Memory: `2Gi` (Playwrightブラウザ実行用に増量)
- **Google Cloud Storage (GCS)**: プロファイルデータ永続化
  - Bucket: `gs://zenn-shadow-director-data`
  - プロファイル: `profiles/{user_id}/soul_profile.json`
  - ドラフト: `drafts/{user_id}/*.md`
- **Google Docs API**: ドラフトをGoogle Docとして直接作成（有効時）
- **Vertex AI**: Gemini API アクセス（`google-genai` SDK with Vertex AI backend）

### Development
- **Language**: Python 3.10
- **Framework**: `discord.py` (Discord Bot), `google-genai` (Gemini SDK)
- **Containerization**: Docker + Cloud Build

## 📂 ディレクトリ構成 (Directory Structure)

```text
shadow-director/
├── README.md                     # このファイル
├── Dockerfile                    # Cloud Run デプロイ用
├── deploy_cloudrun.sh            # デプロイスクリプト
├── pyproject.toml                # 依存関係
├── main.py                       # Discord Bot エントリーポイント
├── .agent/
│   └── workflows/
│       └── deploy_on_wsl.md      # WSLデプロイワークフロー
├── src/
│   ├── agents/
│   │   ├── orchestrator.py       # ルーティングロジック
│   │   ├── interviewer.py        # インタビューエージェント (Gemini 3.0 Pro)
│   │   ├── observer.py           # 監視エージェント (Gemini 3.0 Flash + Search)
│   │   └── drafter.py            # ドラフト生成エージェント (Gemini 3.0 Pro)
│   ├── tools/
│   │   ├── file_processor.py     # PDF/URL処理ユーティリティ
│   │   ├── search_tool.py        # Google Search Grounding設定
│   │   ├── gdocs_tool.py         # Google Docs API Tool
│   │   └── site_explorer.py      # Playwright基盤クラス
│   ├── logic/
│   │   ├── grant_finder.py       # 助成金検索ロジック（SGNAモデル実装）
│   │   ├── grant_validator.py    # URL検証・品質評価
│   │   ├── grant_page_scraper.py # Playwright助成金ページスクレイパー
│   │   └── file_validator.py     # PDF/ZIPファイル検証（SGNAモデル）
│   └── memory/
│       └── profile_manager.py    # GCS操作 (プロファイル管理)
└── config/
    └── prompts.yaml              # 各エージェントのシステムプロンプト
```

## 🗓️ 開発ロードマップ (Roadmap)

### Phase 1: The Soul Sync (Foundation) - ✅ Complete
- [x] Project Setup & Environment Configuration
- [x] Interviewer Agent
  - [x] Gemini 3.0 Pro インタビューロジック
  - [x] **PDF/URLドキュメント処理** (Vertex AI Part API)
  - [x] **選択的ターンカウント** (理解度マーカー検出)
  - [x] 会話履歴管理 & ターンカウント
  - [x] Insight抽出と構造化データ保存
- [x] Profile Manager
  - [x] ローカル環境(JSON)とGCS環境の抽象化
  - [x] GCS統合 (`gs://zenn-shadow-director-data`)

### Phase 2: The Observer (Autonomy) - ✅ Complete
- [x] Observer Agent
  - [x] Google Search Grounding統合
  - [x] Resonance Score判定ロジック
  - [x] 自律的検索クエリ生成
- [x] Scheduling
  - [x] Discord Tasks Loop (週次実行)
  - [x] マニュアルトリガー (`/observe` コマンド相当)

### Phase 3: The Action & Interface - ✅ Complete
- [x] Drafter Agent
  - [x] 申請書ドラフト生成ロジック
  - [x] Google Docs API統合
- [x] Discord Integration
  - [x] Discord Bot UI (メンション対応)
  - [x] **進捗メッセージ表示** (ファイル/URL分析中)
  - [x] **メッセージ重複処理防止**
  - [x] 長文応答の自動分割 (2000文字制限対応)
- [x] Intelligent Routing
  - [x] Router Prompt (INTERVIEW / OBSERVE / DRAFT 判定)
  - [x] インタビュー完了時の自動Observer起動

### Phase 6-9: Production Deployment - ✅ Complete
- [x] Containerization (Dockerfile)
- [x] Cloud Run Deployment
  - [x] **シングルインスタンス設定** (Discord Bot用)
  - [x] **ヘルスチェックサーバー**
  - [x] **環境変数管理**
- [x] Gemini 3.0 Migration
  - [x] `google-genai` SDK with Vertex AI
  - [x] `api_version="v1beta1"` 設定
  - [x] Gemini 3.0 Pro/Flash モデル利用

## 🚧 未実装機能 (Not Implemented Yet)

以下の機能は将来の拡張として検討中です：

- [x] **Vertex AI Memory Bank**: `USE_MEMORY_BANK=true` 環境変数で有効化可能（Preview）
- [ ] **Context Caching**: 長文プロファイルの効率的な再利用
- [ ] **Multi-Tenant Support**: 複数のNPO団体を同時サポート（現在はチャネルベースの分離のみ）
- [ ] **Advanced Analytics**: プロファイルデータの可視化・分析ダッシュボード
- [ ] **Webhook Integration**: 外部サービス（Slack, Teams等）との連携

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Google Cloud Project (Vertex AI API enabled)
- Gemini 3.0 Pro/Flash Preview Access
- Discord Bot Token

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/shadow-director.git
cd shadow-director
```

2. **Install Dependencies**
```bash
pip install -e .
```

3. **Configure Environment**
```bash
cp .env.example .env
# Edit .env with your credentials:
# - DISCORD_BOT_TOKEN
# - GOOGLE_CLOUD_PROJECT
# - GCS_BUCKET_NAME
```

4. **Local Development**
```bash
python main.py
```

## 🚀 Deployment (Google Cloud Run)

### 1. Prerequisites
- Google Cloud SDK (`gcloud`) installed & authenticated
- Docker installed

### 2. Setup Google Cloud Project
```bash
# Login to Google Cloud
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable APIs
gcloud services enable run.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  docs.googleapis.com \
  drive.googleapis.com
```

**Note:** デプロイスクリプト (`deploy_cloudrun.sh`) を使用すると、これらのAPIは自動的に有効化されます。

### 3. Create GCS Bucket
```bash
gsutil mb -l us-central1 gs://YOUR-BUCKET-NAME
```

### 4. Build & Deploy
```bash
# Build Docker image
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/shadow-director-bot

# Deploy to Cloud Run
gcloud run deploy shadow-director-bot \
  --image gcr.io/YOUR_PROJECT_ID/shadow-director-bot \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --max-instances 1 \
  --min-instances 1 \
  --set-env-vars "APP_ENV=production,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,GOOGLE_GENAI_USE_VERTEXAI=True,GCS_BUCKET_NAME=YOUR-BUCKET-NAME,DISCORD_BOT_TOKEN=YOUR_TOKEN"
```

**Note:** For production, use [Secret Manager](https://cloud.google.com/secret-manager) for sensitive values like `DISCORD_BOT_TOKEN`.

### 5. Discord Bot Setup
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application → **OAuth2** → **URL Generator**
3. Select scopes: `bot`
4. Select permissions:
   - `Send Messages`
   - `Read Message History`
   - `Attach Files`
   - `View Channels`
5. Use generated URL to invite bot to your server

## 🌐 Current Deployment Status

**Environment:** Production (Google Cloud Run)
- **Service URL:** `https://shadow-director-bot-182793624818.us-central1.run.app`
- **Latest Revision:** `shadow-director-bot-00125-rwk`
- **Last Deployed:** 2026-01-05 21:19 JST
- **Region:** `us-central1`
- **Status:** ✅ Active
- **Version:** 1.8.0

### Latest Updates (v1.8.0)
- 🏗️ **内部構造改善**: OrchestratorとDrafterAgentのリファクタリングにより、ファイル分類ロジック`FileClassifier`を分離・最適化
- 🚀 **処理効率化**: ファイル分類を早期段階（Step 1.5）で実行し、無関係なファイルの解析処理をスキップ
- 🛡️ **検索精度向上**: Google Search GroundingやSearch Toolのクエリ厳格化により、無関係なWebページ探索を防止

### Latest Updates (v1.7.0)
- 📝 **項目別フォーマット入力**: VLMで検出した入力項目を、1項目ずつGemini 3.0 Flashとプロファイルをもとに生成・入力

### Latest Updates (v1.6.0)
- 📝 **申請書特化インタビュー**: 団体基本情報やプロジェクト詳細（構想・計画・予算）を対話で引き出し、プロファイルに保存
- 👁️ **VLM入力パターン検出**: Word申請書の入力欄（下線、括弧、次行など）をGemini 3.0 Flash (VLM) で視覚的に特定し、自動入力精度を向上
- 🔧 **モデル構成等の柔軟化**: プロンプト設定ファイルによるVLMモデル切り替えに対応
- 🏢 **団体情報管理**: スタッフ数、予算規模、設立年などの定量的データを構造化保存

## 📝 License

This project is built for Zenn Agentic AI Hackathon 2025.

---

**Built with ❤️ for Zenn Agentic AI Hackathon 2025**