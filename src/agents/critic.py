"""
敵対的評価エージェント (Critic Agent)
「冷徹な財団審査員」として申請書を批判的に評価し、修正指示を生成
"""

import os
import re
import logging
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
import yaml

from google import genai
from google.genai.types import GenerateContentConfig


@dataclass
class CritiqueResult:
    """評価結果"""
    score: int  # 0-100
    verdict: str  # 'pass' or 'reject'
    critique: str  # 批判コメント
    improvement_points: List[str]  # 修正指示
    reasoning: str  # 思考プロセス
    scores_detail: Dict[str, int] = field(default_factory=dict)  # 5軸スコア詳細


@dataclass
class DialogueEntry:
    """議論ログのエントリ"""
    round: int
    role: str  # 'writer' or 'critic'
    content: str
    score: int = 0


@dataclass
class RevisionResult:
    """推敲ループの結果"""
    final_draft: str
    final_score: int
    iterations: int
    dialogue_log: List[DialogueEntry]
    passed: bool
    best_draft: str = ""  # 最高スコアのドラフト
    best_score: int = 0


class CriticAgent:
    """
    敵対的評価エージェント
    
    「冷徹な財団審査員」のペルソナで、申請書ドラフトを
    批判的に評価し、具体的な修正指示を生成する。
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
    
    def critique_draft(
        self,
        draft_content: str,
        evaluation_criteria: str,
        grant_name: str,
        profile: str,
        competitive_insight: str = "",
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> CritiqueResult:
        """
        申請書ドラフトを審査員視点で評価
        
        Args:
            draft_content: 評価対象のドラフト
            evaluation_criteria: 評価基準（公募要領）
            grant_name: 助成金名
            profile: NPOプロファイル
            competitive_insight: 競合調査結果（オプション）
            progress_callback: Discord通知用コールバック
            
        Returns:
            CritiqueResult: 評価結果と修正指示
        """
        if not self.client:
            return CritiqueResult(
                score=0,
                verdict="reject",
                critique="評価システムが初期化されていません",
                improvement_points=[],
                reasoning=""
            )
        
        try:
            # システムプロンプトを取得（カスタムまたはデフォルト）
            critic_prompt = self.config.get("system_prompts", {}).get("critic", self._get_default_prompt())
            
            # 評価プロンプトを構築
            prompt = f"""{critic_prompt}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 評価対象
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**助成金名:** {grant_name}

**公募要領・評価基準:**
{evaluation_criteria[:2000] if evaluation_criteria else "評価基準情報なし"}

**競合調査結果:**
{competitive_insight[:1000] if competitive_insight else "競合情報なし"}

**申請団体プロファイル:**
{profile[:1500]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 評価対象ドラフト
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{draft_content[:4000]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 出力形式（JSON）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```json
{{
  "scores_detail": {{
    "social_impact": XX,
    "budget_validity": XX,
    "feasibility": XX,
    "uniqueness": XX,
    "credibility": XX
  }},
  "total_score": XX,
  "verdict": "pass または reject",
  "reasoning": "審査員としての思考プロセス（各観点の評価理由を階層的に記述）",
  "critique": "総評コメント",
  "improvement_points": [
    "具体的な修正指示1",
    "具体的な修正指示2",
    "具体的な修正指示3"
  ]
}}
```
"""
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=0.3,
                    thinking_config={"thinking_budget": 2048}
                )
            )
            
            # JSONをパース
            response_text = response.text
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            
            if json_match:
                import json
                data = json.loads(json_match.group(1))
                
                score = data.get("total_score", 0)
                verdict = "pass" if score >= 80 else "reject"
                
                result = CritiqueResult(
                    score=score,
                    verdict=verdict,
                    critique=data.get("critique", ""),
                    improvement_points=data.get("improvement_points", []),
                    reasoning=data.get("reasoning", ""),
                    scores_detail=data.get("scores_detail", {})
                )
                
                # 思考プロセスをフォーマットして通知
                if progress_callback:
                    formatted_thinking = self._format_thinking_process(result)
                    progress_callback(formatted_thinking)
                
                return result
            
            return CritiqueResult(
                score=0,
                verdict="reject",
                critique="評価結果のパースに失敗しました",
                improvement_points=[],
                reasoning=""
            )
            
        except Exception as e:
            logging.error(f"Critique failed: {e}")
            return CritiqueResult(
                score=0,
                verdict="reject",
                critique=f"評価エラー: {str(e)}",
                improvement_points=[],
                reasoning=""
            )
    
    def _format_thinking_process(self, result: CritiqueResult) -> str:
        """思考プロセスをDiscord通知用にフォーマット"""
        scores = result.scores_detail
        
        # スコア表示用のアイコン
        def score_icon(score: int) -> str:
            if score >= 18:
                return "🟢"
            elif score >= 14:
                return "🟡"
            else:
                return "🔴"
        
        # 日本語ラベル
        labels = {
            "social_impact": "社会的インパクト",
            "budget_validity": "予算の妥当性",
            "feasibility": "実現可能性",
            "uniqueness": "独自性・差別化",
            "credibility": "団体の信頼性"
        }
        
        scores_text = "\n".join([
            f"│  {score_icon(score)} {labels.get(key, key)}: {score}/20点"
            for key, score in scores.items()
        ])
        
        verdict_icon = "✅" if result.verdict == "pass" else "❌"
        verdict_text = "合格" if result.verdict == "pass" else "不採択"
        
        improvements = "\n".join([
            f"   {i+1}. {point}" 
            for i, point in enumerate(result.improvement_points[:5])
        ]) if result.improvement_points else "   なし"
        
        return f"""
🔍 **Critic 思考プロセス:**
├─────────────────────────────
{scores_text}
├─────────────────────────────
│  📊 **総合スコア: {result.score}点**
│  {verdict_icon} **判定: {verdict_text}**
└─────────────────────────────

📝 **修正指示:**
{improvements}
"""
    
    def _get_default_prompt(self) -> str:
        """デフォルトのCriticプロンプト"""
        return """あなたは「冷徹な財団審査員」として、NPO助成金申請書を厳しく評価します。

**ペルソナ:**
- 20年以上の助成金審査経験を持つ財団事務局長
- 採択率10%以下の厳しい審査を担当
- 「お情け採択」は一切しない
- 具体性と根拠のない申請は容赦なく却下

**評価観点（各20点、合計100点）:**
1. **社会的インパクト (social_impact)**: 数値目標、受益者数、成果指標の具体性
2. **予算の妥当性 (budget_validity)**: 積算根拠、費用対効果の明確さ
3. **実現可能性 (feasibility)**: 実施体制、スケジュールの具体性
4. **独自性・差別化 (uniqueness)**: 他団体との違い、新規性
5. **団体の信頼性 (credibility)**: 実績、専門性、継続性

**80点以上で合格、それ未満は不採択として修正指示を出す。**
"""
    
    def revise_draft(
        self,
        original_draft: str,
        critique: CritiqueResult,
        grant_name: str,
        profile: str,
        evaluation_criteria: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Criticの指摘を受けてドラフトを修正
        
        Args:
            original_draft: 元のドラフト
            critique: Criticからの評価結果
            grant_name: 助成金名
            profile: NPOプロファイル
            evaluation_criteria: 評価基準
            progress_callback: Discord通知用コールバック
            
        Returns:
            修正後のドラフト
        """
        if not self.client:
            return original_draft
        
        if progress_callback:
            progress_callback("✍️ **Writer: 指摘事項を修正中...**")
        
        try:
            # 修正指示をテキスト化
            improvements = "\n".join([
                f"{i+1}. {point}" 
                for i, point in enumerate(critique.improvement_points)
            ])
            
            prompt = f"""あなたは助成金申請書のリライターです。
審査員からのフィードバックを受けて、申請書を改善してください。

**助成金名:** {grant_name}

**現在のスコア:** {critique.score}点（目標: 80点以上）

**審査員からの総評:**
{critique.critique}

**修正すべき点:**
{improvements}

**申請団体プロファイル:**
{profile[:2000]}

**元のドラフト:**
{original_draft[:4000]}

**改善の原則:**
- 指摘された点を的確に修正
- 具体的な数値・根拠を追加
- プロファイル情報を最大限活用
- 文字数制限を遵守
- 元の良い部分は維持

**出力:**
修正後のドラフト全文を出力してください。
"""
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=GenerateContentConfig(temperature=0.4)
            )
            
            revised_draft = response.text.strip()
            
            if progress_callback:
                progress_callback("✅ **Writer: 修正版を提出しました**")
            
            return revised_draft
            
        except Exception as e:
            logging.error(f"Draft revision failed: {e}")
            return original_draft
    
    def run_revision_loop(
        self,
        initial_draft: str,
        evaluation_criteria: str,
        grant_name: str,
        profile: str,
        competitive_insight: str = "",
        max_iterations: int = 3,
        pass_threshold: int = 80,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> RevisionResult:
        """
        Writer-Criticの推敲ループを実行
        
        Args:
            initial_draft: 初回ドラフト
            evaluation_criteria: 評価基準
            grant_name: 助成金名
            profile: NPOプロファイル
            competitive_insight: 競合調査結果
            max_iterations: 最大ループ回数
            pass_threshold: 合格閾値スコア
            progress_callback: Discord通知用コールバック
            
        Returns:
            RevisionResult: 推敲結果
        """
        dialogue_log: List[DialogueEntry] = []
        current_draft = initial_draft
        best_draft = initial_draft
        best_score = 0
        
        def notify(msg: str):
            if progress_callback:
                progress_callback(msg)
        
        for iteration in range(max_iterations):
            round_num = iteration + 1
            
            # ラウンド開始通知
            notify(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 **推敲ループ Round {round_num}/{max_iterations}**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")
            
            # Writer提出を記録
            dialogue_log.append(DialogueEntry(
                round=round_num,
                role="writer",
                content=f"{'初回' if round_num == 1 else '修正'}ドラフトを提出",
                score=0
            ))
            
            if round_num == 1:
                notify("✍️ **Writer: 初回ドラフトを提出しました**")
            
            # Criticによる評価
            critique = self.critique_draft(
                draft_content=current_draft,
                evaluation_criteria=evaluation_criteria,
                grant_name=grant_name,
                profile=profile,
                competitive_insight=competitive_insight,
                progress_callback=notify
            )
            
            # 評価結果を記録
            dialogue_log.append(DialogueEntry(
                round=round_num,
                role="critic",
                content=critique.critique,
                score=critique.score
            ))
            
            # ベストスコアを更新
            if critique.score > best_score:
                best_score = critique.score
                best_draft = current_draft
            
            # 合格判定
            if critique.score >= pass_threshold:
                notify(f"""
✅ **合格！ 最終スコア: {critique.score}点**
推敲ラウンド: {round_num}回
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")
                
                return RevisionResult(
                    final_draft=current_draft,
                    final_score=critique.score,
                    iterations=round_num,
                    dialogue_log=dialogue_log,
                    passed=True,
                    best_draft=current_draft,
                    best_score=critique.score
                )
            
            # 最後のラウンドなら修正せず終了
            if round_num >= max_iterations:
                break
            
            # Writerによる修正
            current_draft = self.revise_draft(
                original_draft=current_draft,
                critique=critique,
                grant_name=grant_name,
                profile=profile,
                evaluation_criteria=evaluation_criteria,
                progress_callback=notify
            )
        
        # 最大ラウンド到達（不合格）
        notify(f"""
⚠️ **推敲ループ完了（目標スコア未達）**
最終スコア: {best_score}点（目標: {pass_threshold}点）
最高スコアのドラフトを採用します。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")
        
        return RevisionResult(
            final_draft=best_draft,
            final_score=best_score,
            iterations=max_iterations,
            dialogue_log=dialogue_log,
            passed=False,
            best_draft=best_draft,
            best_score=best_score
        )
    
    def format_dialogue_log(self, dialogue_log: List[DialogueEntry]) -> str:
        """議論ログをDiscord表示用にフォーマット"""
        lines = ["📜 **AI議論ログ**", ""]
        
        for entry in dialogue_log:
            if entry.role == "writer":
                lines.append(f"**Round {entry.round}** ✍️ Writer: {entry.content}")
            else:
                icon = "✅" if entry.score >= 80 else "❌"
                lines.append(f"  🔍 Critic: {entry.score}点 {icon}")
                if entry.content:
                    lines.append(f"     → {entry.content[:100]}...")
        
        return "\n".join(lines)
