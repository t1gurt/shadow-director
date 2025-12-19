# Phase 2: The Observer - 自律監視ロジック仕様書

## 1. 概要
本機能は、NPO代表者が活動に専念している間、バックグラウンドで自律的に助成金やCSR支援情報をリサーチし、団体の「Soul (Mission/Vision)」に深く共鳴する機会（Resonance Opportunity）のみを通知する「自律型監視エージェント」である。

## 2. エージェント定義 (Persona)
*   **名称**: Autonomous Funding Watch (The Observer)
*   **役割**: プロアクティブなスカウトマン
*   **特徴**:
    *   **能動的探索**: ユーザーからの指示を待たず、定期的に外部環境をスキャンする。
    *   **共鳴度判定 (Resonance Reasoning)**: 単なるキーワードマッチ（事務的適合）ではなく、「理念の合致」を重視する。
    *   **ノイズフィルタリング**: 適合度の低い情報は無視し、代表者の認知的負荷を最小限に抑える。

## 3. システム構成
*   **Model**: Google Vertex AI Gemini 2.5 Flash (`gemini-2.5-flash`)
    *   ※高速性とコスト効率を重視してFlashモデルを採用。
*   **Tools**: Google Search Grounding (via Google Gen AI SDK)
    *   最新のウェブ情報を取得するために利用。
*   **Trigger**: `discord.ext.tasks.loop` (168時間/1週間ごとの定期実行)

## 4. 処理フロー
1.  **定期トリガー発火**: `main.py` のスケジューラーが起動。
2.  **全プロファイルスキャン**: `Orchestrator` が保存されている全ユーザーの `Soul Profile` を読み込む。
3.  **検索クエリ自律生成 (`Autonomous Query Generation`)**:
    *   **Logic**: `_generate_queries(profile)` メソッドにて、LLMがプロファイル（Mission, Target Issue）を分析し、最適な検索キーワードを3つ生成する。
    *   **入力**: Soul Profileテキスト
    *   **出力例**: `["猫の殺処分ゼロ 助成金", "動物福祉 CSR支援", "保護猫シェルター 資金調達"]`
    *   **特徴**: ハードコードされたテンプレートを使わず、団体の固有性に合わせた柔軟なキーワード作成を行う。
4.  **グラウンディング検索 (Fully Integrated Grounding)**:
    *   生成されたクエリを検索意図としてプロンプトに含め、`google-genai` SDK の `GoogleSearch` ツールを呼び出す。
    *   LLMは自身の知識ではなく、Google検索のライブデータをソースとして回答を生成する。
5.  **共鳴度判定 (Resonance Check)**:
    *   取得した情報とプロファイルを比較し、LLMが「共鳴度スコア (0-100)」を算出する。
6.  **通知**:
    *   スコアが高い（閾値以上）情報のみを抽出し、Discord経由でユーザーにDM送信する。

## 5. 共鳴度判定基準 (`Resonance Reasoning Criteria`)
`config/prompts.yaml` に定義された以下の基準に基づき判定を行う。

| Rank | Score | 基準 |
| :--- | :--- | :--- |
| **S** | 90-100 | **Soul Sync**: 原体験レベルでの完全な一致。財団の理念がNPOのミッションを鏡のように映し出している状態。 |
| **A** | 70-89 | **Strong Match**: ミッションや解決課題が強く合致しており、採択の可能性が高い。 |
| **B** | 50-69 | **Technical Match**: 募集要項の条件は満たしているが、理念的な繋がりは弱い。 |
| **C** | 0-49 | **Mismatch**: 単なる金銭的取引に見える、または価値観の不一致。 |

## 6. 今後の拡張 (To-Be)
*   **Dynamic Retrievalの高度化**: 検索結果が不十分な場合、検索クエリを自動修正して再検索する機能（Self-Reflection）。
*   **除外リスト**: 過去に却下した助成金や、ユーザーが「興味なし」とした案件の学習。
