# 競合調査と勝率予測 (Competitive Intelligence) 仕様書

## 概要

申請前に「勝てるか」を判断する戦略参謀AI。
過去の採択団体を調査し、自団体との比較分析に基づいて戦略的トーン調整を提案。

---

## 機能詳細

### 1. 過去採択団体検索 (Past Winner Search)

**検索クエリ例:**
- `{助成金名} 2025年度 採択団体 一覧`
- `{助成金名} 過去採択事例 採択実績`

**抽出情報:**
- 団体名
- 採択年度
- 事業名
- 分野・カテゴリ
- 予算規模

---

### 2. 採択傾向分析 (Winning Pattern Analysis)

**分析観点:**
- 分野別採択割合（IT教育 60%、地域活性化 25%など）
- 採択団体の規模傾向
- 共通キーワード・特徴
- 審査で重視されるポイント

---

### 3. 戦略提案 (Strategy Adjustment)

**提案内容:**
- 文脈・トーンの調整指示
- 強調すべきキーワード
- 勝率予測（調整前・後）

---

## Discord通知（思考プロセス可視化）

```
🔍 **競合調査を開始します...**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 過去3年の採択傾向を分析中...

💡 分析結果:
- 過去採択: IT教育系団体 60%、地域活性化 25%、その他 15%
- 採択規模: 平均予算500-800万円の団体が多い

🎯 戦略提案:
「地域活性化」→「地域DX推進」の文脈に調整

📈 予測勝率: 65% → 85%（戦略調整後）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 実装ファイル

| ファイル | 役割 |
|---------|------|
| `src/logic/competitive_analyzer.py` | 競合調査エンジン本体 |
| `src/agents/drafter.py` | 統合処理（Step 2.5で呼び出し） |
| `config/prompts.yaml` | `competitive_search`, `competitive_analysis` プロンプト |

---

## 出力データ構造

```python
CompetitiveResult:
    past_winners: List[WinnerInfo]  # 過去採択団体
    winning_patterns: str           # 採択傾向分析
    strategy: str                   # 戦略提案
    win_probability: int            # 勝率予測 (0-100)
    tone_adjustment: str            # トーン調整指示
```

---

## 統合フロー

1. **Step 2.5** で `CompetitiveAnalyzer.analyze_competitors()` を呼び出し
2. 戦略提案を取得
3. **Step 3** のドラフト生成プロンプトに戦略を反映
4. Writer が戦略を反映したドラフトを生成
