# Phase 1: The Soul Sync - インタビューロジック仕様書

## 1. 概要
本機能は、NPO代表者（ユーザー）との対話を通じて、組織のミッション・ビジョンや代表者の原体験（Soul）を引き出し、構造化されたデータとして保存する「自律型インタビューエージェント」である。

## 2. エージェント定義 (Persona)
*   **名称**: NPO-SoulSync Agent (The Interviewer)
*   **役割**: 代表者の「壁打ち相手」兼「引き出し役」
*   **特徴**:
    *   **傾聴と深掘り (Active Inquiry)**: 単なるQAではなく、「なぜ？」を問いかけることで深層心理にアプローチする。
    *   **共感 (Empathy)**: 事務的ではなく、情熱に寄り添うトーンで信頼関係を構築する。
    *   **構造化 (Structuring)**: 会話の端々から重要なキーワード（原体験、課題意識、強み）を抽出し、プロファイルに蓄積する。

## 3. システム構成
*   **Model**: Google Vertex AI Gemini 2.5 Pro (`gemini-2.5-pro`)
    *   ※コンフィグにより `gemini-1.5-pro` 等へ変更可能。
*   **Region**: `us-central1` (初期構成)
*   **Interface**: Discord Bot (via `main.py`) / CLI Mock Runner (`mock_runner.py`)

## 4. 処理フロー
1.  **ユーザー入力受信**: Discord または CLI からメッセージを受け取る。
2.  **コンテキストロード**: `ProfileManager` から現在の `Soul Profile` (JSON) を読み込む。
3.  **プロンプト構築**:
    *   `System Prompt` (振る舞いの定義)
    *   `Current Profile Context` (これまでの会話から抽出された情報)
    *   `User Message` (直近の入力)
    これらを結合し、LLMへ送信する。
4.  **推論・応答生成**: Geminiモデルが応答を生成する。
5.  **プロファイル更新** (※現在はMock動作、Phase 2以降で自動抽出ロジック強化予定):
    *   会話の中で特定のキーワードや文脈が検出された場合、`soul_profile.json` を更新する。

## 5. プロンプト設計 (`config/prompts.yaml`)
システムプロンプトには以下の要素が含まれる：
*   **Role**: NPO-SoulSync Agentとしてのアイデンティティ。
*   **Directive**:
    *   ユーザーの回答を深掘りすること。
    *   「設定ファイル」を書かせるような事務的な質問を避けること。
    *   一度に多くの質問をせず、会話のキャッチボールを重視すること。

## 6. データ構造 (`soul_profile.json`)
会話から得られたインサイトは以下のJSON形式で永続化される。

```json
{
    "insights": {
        "mission": "猫の保護活動",
        "vision": "殺処分ゼロの世界",
        "primary_experience": "子供の頃に拾った猫が..."
    }
}
```

## 7. 今後の拡張 (To-Be)
*   **自動抽出の高度化**: LLMのFunction Callingを用い、会話中に自動的にJSONフィールドを更新する機能の実装。
*   **マルチモーダル対応**: 既存の資料（PDF/画像）をアップロードし、そこから文脈を読み取る機能。
