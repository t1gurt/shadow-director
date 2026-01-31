"""
競合調査・勝率予測エンジン (Competitive Intelligence)
過去採択団体の調査と戦略的トーン調整を担当
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
import yaml

from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch


@dataclass
class WinnerInfo:
    """過去採択団体情報"""
    name: str
    year: int
    project_title: str
    category: str
    budget_scale: str = ""
    key_features: List[str] = field(default_factory=list)


@dataclass
class CompetitiveResult:
    """競合調査結果"""
    past_winners: List[WinnerInfo]
    winning_patterns: str  # 採択傾向の分析
    strategy: str  # 戦略提案
    win_probability: int  # 勝率予測 (0-100)
    tone_adjustment: str  # トーン調整指示
    analysis_log: List[str] = field(default_factory=list)  # 思考プロセスログ


class CompetitiveAnalyzer:
    """
    競合調査・戦略立案エンジン
    
    過去の採択団体を調査し、自団体との比較分析を行い、
    勝率を高めるための戦略提案を生成する。
    """
    
    def __init__(self):
        self.config = self._load_config()
        self._init_client()
        
    def _load_config(self) -> Dict[str, Any]:
        """設定ファイルを読み込む"""
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            return {}
    
    def _init_client(self):
        """GenAIクライアントを初期化"""
        model_config = self.config.get("model_config", {})
        project_id = model_config.get("project_id", "zenn-shadow-director")
        location = model_config.get("location", "us-central1")
        
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        
        try:
            self.client = genai.Client()
        except Exception as e:
            logging.error(f"Failed to initialize client: {e}")
            self.client = None
            
        self.model_name = model_config.get("observer_model", "gemini-3-pro-preview")
    
    def analyze_competitors(
        self,
        grant_name: str,
        profile: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> CompetitiveResult:
        """
        競合調査と戦略分析を実行
        
        Args:
            grant_name: 助成金名
            profile: 自団体のプロファイル
            progress_callback: Discord通知用コールバック
            
        Returns:
            CompetitiveResult: 競合調査結果と戦略提案
        """
        analysis_log = []
        
        def notify(msg: str):
            analysis_log.append(msg)
            if progress_callback:
                progress_callback(msg)
        
        notify("🔍 **競合調査を開始します...**")
        
        # Step 1: 過去採択団体を検索
        notify("📊 過去の採択団体を検索中...")
        past_winners = self._search_past_winners(grant_name, notify)
        
        if not past_winners:
            notify("⚠️ 過去の採択情報が見つかりませんでした。一般的な戦略を提案します。")
            return self._generate_generic_strategy(grant_name, profile, analysis_log)
        
        notify(f"✅ {len(past_winners)}件の過去採択団体を発見")
        
        # Step 2: 採択傾向を分析
        notify("🔬 採択傾向を分析中...")
        winning_patterns = self._analyze_winning_patterns(past_winners, grant_name, notify)
        
        # Step 3: 自団体との比較分析
        notify("📈 自団体との比較分析中...")
        comparison = self._compare_with_profile(past_winners, winning_patterns, profile, grant_name)
        
        # Step 4: 戦略提案と勝率予測
        notify("🎯 戦略提案を生成中...")
        strategy_result = self._generate_strategy(
            grant_name, profile, past_winners, winning_patterns, comparison
        )
        
        # 結果をフォーマットして通知
        result_message = self._format_result_message(strategy_result)
        notify(result_message)
        
        strategy_result.analysis_log = analysis_log
        return strategy_result
    
    def _search_past_winners(
        self, 
        grant_name: str, 
        notify: Callable[[str], None]
    ) -> List[WinnerInfo]:
        """過去採択団体をGoogle検索で調査"""
        if not self.client:
            return []
        
        try:
            # 検索クエリを生成（複数年度）
            current_year = 2026  # 現在年
            search_queries = [
                f"{grant_name} {current_year - 1}年度 採択団体 一覧",
                f"{grant_name} {current_year - 2}年度 採択 結果",
                f"{grant_name} 過去採択事例 採択実績"
            ]
            
            prompt = f"""以下の検索クエリを使用して、「{grant_name}」の過去採択団体を調査してください。

検索クエリ:
{chr(10).join(search_queries)}

**出力形式（JSON形式で出力）:**
```json
{{
  "winners": [
    {{
      "name": "採択団体名",
      "year": 2025,
      "project_title": "採択事業名",
      "category": "分野（IT教育/地域活性化/福祉など）",
      "budget_scale": "予算規模（例: 500万円）",
      "key_features": ["特徴1", "特徴2"]
    }}
  ],
  "search_summary": "検索結果の要約"
}}
```

最大10件まで抽出してください。情報が不明確な場合は推測せず「不明」としてください。
"""
            
            # Google Search Groundingを使用
            google_search_tool = Tool(google_search=GoogleSearch())
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=GenerateContentConfig(
                    tools=[google_search_tool],
                    temperature=0.3
                )
            )
            
            # JSONをパース
            response_text = response.text
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            
            if json_match:
                import json
                data = json.loads(json_match.group(1))
                winners = []
                for w in data.get("winners", []):
                    winners.append(WinnerInfo(
                        name=w.get("name", "不明"),
                        year=w.get("year", 0),
                        project_title=w.get("project_title", "不明"),
                        category=w.get("category", "不明"),
                        budget_scale=w.get("budget_scale", ""),
                        key_features=w.get("key_features", [])
                    ))
                return winners
            
            return []
            
        except Exception as e:
            logging.error(f"Past winner search failed: {e}")
            return []
    
    def _analyze_winning_patterns(
        self,
        winners: List[WinnerInfo],
        grant_name: str,
        notify: Callable[[str], None]
    ) -> str:
        """採択傾向を分析"""
        if not self.client or not winners:
            return ""
        
        try:
            # 採択団体情報をテキスト化
            winners_text = "\n".join([
                f"- {w.name} ({w.year}年): {w.project_title} / 分野: {w.category} / 規模: {w.budget_scale}"
                for w in winners
            ])
            
            prompt = f"""以下の「{grant_name}」の過去採択団体を分析し、採択傾向を抽出してください。

**過去採択団体:**
{winners_text}

**分析観点:**
1. どの分野・テーマが多いか（割合を算出）
2. 採択団体の規模傾向（予算・組織規模）
3. 共通する特徴・キーワード
4. 審査で重視されていると思われるポイント

**出力形式:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 採択傾向分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**分野別割合:**
- [分野1]: XX%
- [分野2]: XX%

**採択団体の特徴:**
- [特徴1]
- [特徴2]

**審査で重視されるポイント:**
- [ポイント1]
- [ポイント2]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=GenerateContentConfig(temperature=0.3)
            )
            
            patterns = response.text.strip()
            notify(patterns)
            return patterns
            
        except Exception as e:
            logging.error(f"Pattern analysis failed: {e}")
            return ""
    
    def _compare_with_profile(
        self,
        winners: List[WinnerInfo],
        patterns: str,
        profile: str,
        grant_name: str
    ) -> str:
        """自団体と過去採択団体を比較"""
        if not self.client:
            return ""
        
        try:
            prompt = f"""以下の情報を基に、自団体と過去採択団体を比較分析してください。

**助成金名:** {grant_name}

**自団体プロファイル:**
{profile[:3000]}

**過去採択傾向:**
{patterns}

**比較観点:**
1. 自団体の強み（過去採択団体と比較して）
2. 自団体の弱み・ギャップ
3. 活かせる類似点
4. 補強すべきポイント

**出力形式:**
自団体の競争力を客観的に評価し、200字程度で簡潔にまとめてください。
"""
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=GenerateContentConfig(temperature=0.3)
            )
            
            return response.text.strip()
            
        except Exception as e:
            logging.error(f"Comparison failed: {e}")
            return ""
    
    def _generate_strategy(
        self,
        grant_name: str,
        profile: str,
        winners: List[WinnerInfo],
        patterns: str,
        comparison: str
    ) -> CompetitiveResult:
        """戦略提案と勝率予測を生成"""
        if not self.client:
            return CompetitiveResult(
                past_winners=winners,
                winning_patterns=patterns,
                strategy="分析情報が不足しています",
                win_probability=50,
                tone_adjustment=""
            )
        
        try:
            prompt = f"""以下の競合分析結果を基に、申請書の戦略を提案してください。

**助成金名:** {grant_name}

**自団体プロファイル:**
{profile[:2000]}

**過去採択傾向:**
{patterns}

**比較分析:**
{comparison}

**出力形式（JSON）:**
```json
{{
  "win_probability_before": 調整前の勝率予測(0-100),
  "win_probability_after": 戦略調整後の勝率予測(0-100),
  "strategy": "具体的な戦略提案（200字程度）",
  "tone_adjustment": "申請書のトーン・文脈調整の具体的指示",
  "key_recommendations": [
    "推奨事項1",
    "推奨事項2",
    "推奨事項3"
  ]
}}
```
"""
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=GenerateContentConfig(temperature=0.4)
            )
            
            # JSONをパース
            response_text = response.text
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            
            if json_match:
                import json
                data = json.loads(json_match.group(1))
                return CompetitiveResult(
                    past_winners=winners,
                    winning_patterns=patterns,
                    strategy=data.get("strategy", ""),
                    win_probability=data.get("win_probability_after", 50),
                    tone_adjustment=data.get("tone_adjustment", "")
                )
            
            return CompetitiveResult(
                past_winners=winners,
                winning_patterns=patterns,
                strategy="戦略生成に失敗しました",
                win_probability=50,
                tone_adjustment=""
            )
            
        except Exception as e:
            logging.error(f"Strategy generation failed: {e}")
            return CompetitiveResult(
                past_winners=winners,
                winning_patterns=patterns,
                strategy=f"エラー: {str(e)}",
                win_probability=50,
                tone_adjustment=""
            )
    
    def _generate_generic_strategy(
        self,
        grant_name: str,
        profile: str,
        analysis_log: List[str]
    ) -> CompetitiveResult:
        """過去採択情報がない場合の一般的戦略"""
        return CompetitiveResult(
            past_winners=[],
            winning_patterns="過去採択情報なし",
            strategy="過去の採択情報が見つからなかったため、一般的な申請書作成ベストプラクティスに基づいて作成します。",
            win_probability=50,
            tone_adjustment="具体的な数値目標と成果指標を明確に記載してください。",
            analysis_log=analysis_log
        )
    
    def _format_result_message(self, result: CompetitiveResult) -> str:
        """結果をDiscord通知用にフォーマット"""
        winners_count = len(result.past_winners)
        
        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 **競合調査完了 - 戦略提案**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **調査結果:**
- 過去採択団体: {winners_count}件を分析

💡 **戦略提案:**
{result.strategy}

🎨 **トーン調整:**
{result.tone_adjustment}

📈 **予測勝率: {result.win_probability}%**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
