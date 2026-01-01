import logging
from typing import Dict, Any, List, Optional, Tuple
import yaml
import os
import re
from google import genai
from datetime import datetime

from src.memory.profile_manager import ProfileManager
from src.utils.progress_notifier import get_progress_notifier, ProgressStage
from src.logic.grant_finder import GrantFinder

class ObserverAgent:
    """
    Agent responsible for finding new grant opportunities.
    Refactored to delegate logic to GrantFinder and GrantValidator.
    """
    
    def __init__(self):
        self.config = self._load_config()
        self._init_client()
        self.profile_manager = None
        
        # Initialize GrantFinder with client and config
        self.finder = GrantFinder(self.client, self.model_name, self.config)

    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from prompts.yaml.
        """
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            return {}

    def _init_client(self):
        """
        Initialize the GenAI client.
        """
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
            
        self.model_name = model_config.get("observer_model", "gemini-2.0-flash-exp")

    def observe(self, user_id: str) -> Tuple[str, List[Dict]]:
        """
        Main entry point for the observation task.
        Finds grant opportunities, validates them, and returns a report.
        """
        logging.info(f"Starting observation for user: {user_id}")
        notifier = get_progress_notifier()
        notifier.notify_sync(ProgressStage.STARTING, "助成金情報の収集を開始します...")
        
        # Initialize ProfileManager
        self.profile_manager = ProfileManager(user_id)
        profile_context = self.profile_manager.get_profile_context()

        # Get current date in JST (Japan Standard Time, UTC+9)
        from datetime import timezone, timedelta
        jst = timezone(timedelta(hours=9))
        current_date_str = datetime.now(jst).strftime("%Y年%m月%d日")
        
        notifier.notify_sync(ProgressStage.SEARCHING, "共鳴する助成金を検索中...")
        
        # 1. Search for opportunities using GrantFinder
        response_text, opportunities = self.finder.search_grants(profile_context, current_date_str)
        
        if not opportunities:
            notifier.notify_sync(ProgressStage.COMPLETED, "新しい助成金は見つかりませんでした。")
            return "現在、条件に合う新しい助成金・資金調達機会は見つかりませんでした。", []

        notifier.notify_sync(ProgressStage.ANALYZING, f"{len(opportunities)}件の候補が見つかりました。詳細を調査します...")

        valid_opportunities = []
        for opp in opportunities:
            title = opp.get('title')
            
            # Check duplication
            if self.profile_manager.is_grant_shown(opp):
                logging.info(f"Skipping already shown grant: {title}")
                continue
                
            notifier.notify_sync(ProgressStage.VERIFYING, f"検証中: {title}...", "公式ページの確認と信頼性評価")
            
            # 2. Find and Validate Official Page using GrantFinder
            official_info = self.finder.find_official_page(title, current_date_str)
            
            # Merge results
            opp.update(official_info)
            
            # Filter invalid or closed grants
            if opp.get('is_valid', False):
                valid_opportunities.append(opp)
                # Mark as shown so we don't show it again immediately
                self.profile_manager.add_shown_grant(opp)
            else:
                logging.info(f"Skipping invalid/closed grant: {title} (Reason: {opp.get('exclude_reason') or opp.get('status')})")

        # 3. Format Report
        if not valid_opportunities:
            notifier.notify_sync(ProgressStage.COMPLETED, "有効な助成金は見つかりませんでした。")
            return "候補は見つかりましたが、現在募集中または信頼できる公式サイトが確認できるものはありませでした。", []

        notifier.notify_sync(ProgressStage.PROCESSING, "レポートを作成中...")
        report = self._format_observation_report(valid_opportunities)
        
        notifier.notify_sync(ProgressStage.COMPLETED, "調査完了！", f"{len(valid_opportunities)}件の助成金を提案します。")
        return report, valid_opportunities

    def _format_observation_report(self, opportunities: List[Dict]) -> str:
        """
        Formats the list of opportunities into a user-friendly markdown report.
        """
        if not opportunities:
            return "有効な助成金情報は見つかりませんでした。"
            
        report = f"# 🔍 最新の資金調達機会レポート\n\n"
        report += f"あなたの団体（Soul Profile）に共鳴する、現在募集中の助成金を{len(opportunities)}件見つけました。\n\n"
        
        for i, opp in enumerate(opportunities, 1):
            title = opp.get('title', '不明な助成金')
            amount = opp.get('amount', '不明')
            reason = opp.get('reason', 'なし')
            score = opp.get('resonance_score', 0)
            url = opp.get('official_url', 'N/A')
            deadline_end = opp.get('deadline_end', '不明')
            deadline_start = opp.get('deadline_start', '')
            
            # Quality/Confidence indicators
            quality_note = ""
            if opp.get('url_quality_score', 0) >= 80:
                quality_note = " 🛡️公式サイト確認済"
            elif opp.get('url_quality_score', 0) < 50:
                quality_note = " ⚠️情報源要確認"

            deadline_str = f"{deadline_end}"
            if deadline_start:
                 deadline_str = f"{deadline_start} 〜 {deadline_end}"

            # Format resonance info
            resonance_visual = "⚡" * (score // 20)
            
            report += f"## {i}. {title} {quality_note}\n"
            report += f"**💰 金額**: {amount}\n"
            report += f"**📅 締切**: {deadline_str}\n"
            report += f"**⚡ 共鳴度**: {score}/100 {resonance_visual}\n"
            report += f"**🔗 リンク**: {url}\n"
            report += f"**💭 推選理由**: {reason}\n\n"
            
            if opp.get('url_quality_reason'):
                 report += f"> *信頼性チェック: {opp.get('url_quality_reason')}*\n\n"
                 
            report += "---\n\n"
            
        report += "\n💡 気になる助成金があれば、「[番号]のドラフトを作成して」と指示してください。"
        
        return report
