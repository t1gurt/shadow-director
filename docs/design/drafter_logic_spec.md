# Phase 3: The Action - ドラフト生成ロジック仕様書

## 1. 概要
本機能は、NPOの「Soul Profile」と特定された「助成金機会」に基づき、採択率の高い申請書ドラフト（または提案書）を自動生成する「自律型執筆エージェント」である。単なるテンプレートへの流し込みではなく、団体の原体験を武器にした説得力のあるナラティブを構築する。

## 2. エージェント定義 (Persona)
*   **名称**: Shadow Drafter
*   **役割**: プロフェッショナル・グランツ・ライター（熟練の資金調達コンサルタント）
*   **特徴**:
    *   **Emotional & Logical**: 「情熱（Soul）」と「論理（Fund Logic）」の架け橋となる。
    *   **Structure-Oriented**: 評価者が読みやすい明確な章立て（Summary, Problem, Solution, Impact）を行う。
    *   **Adaptive Tone**: 助成元の性質（行政、民間財団、企業CSR）に合わせて文体を微調整する。

## 3. システム構成
*   **Model**: Google Vertex AI Gemini 2.5 Pro (or 3.0 Pro if available)
    *   高度な推論と長文生成能力が必要なため、Proモデルを採用。
*   **Tools**: `GoogleDocsTool` (Mock: Local Markdown Output)
    *   生成されたテキストをドキュメント形式で保存する。将来的には Google Docs API に直結。
*   **Input**:
    1.  User ID (to fetch Soul Profile)
    2.  Target Grant Information (募集要項、目的、金額など)

## 4. 処理フロー
1.  **ドラフトリクエスト受信**: `Orchestrator`（またはUser Command）から、対象となる助成金情報が渡される。
2.  **プロファイル読み込み**: `ProfileManager` から `Soul Profile` を取得。
3.  **ドラフト生成 (Drafting)**:
    *   プロファイルの `Primary Experience`（原体験）を導入部のフックとして使用。
    *   `Mission/Vision` を長期的なインパクト（Long-term Vision）として提示。
    *   助成金の `Requirement` に合わせて、具体的な `Activities` と `Budget` を構成。
4.  **出力**:
    *   Markdown形式で整形されたドキュメントを生成し、`drafts/` ディレクトリに保存。

## 5. 出力構造 (Example Structure)
生成されるドキュメントは以下のセクションを持つことを標準とする。

| Section | Content | Source |
| :--- | :--- | :--- |
| **Title** | プロジェクト名（キャッチーかつ具体的） | Generated |
| **Executive Summary** | 原体験から始まる、心を掴む概要。 | Soul Profile (Primary Experience) |
| **Problem Statement** | 社会課題の深刻さと、既存解決策の限界。 | Soul Profile (Target Issue) |
| **Methods** | 具体的な解決策。革新性や独自性。 | Grant Info + Profile (Strengths) |
| **Budget** | 要求金額の使途。 | Grant Info (Max Budget) |
| **Expected Impact** | 短期的な成果と、長期的なビジョン（Vision）。 | Soul Profile (Vision) |

## 6. 今後の拡張 (To-Be)
*   **Google Docs API 連携**: 生成されたドラフトを入稿用の Google Doc として出力。
*   **Iterative Refinement**: ユーザーからのフィードバック（「もっと具体的数値を」「ここはトーンを抑えて」）を受けた修正ループ。
*   **Past Proposal Learning**: 過去の採択/不採択データを学習し、書き方を最適化（RAG）。
