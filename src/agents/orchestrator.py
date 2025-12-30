import re
import logging
from typing import Dict, Any, List, Tuple
import yaml
import os
import glob
from src.agents.interviewer import InterviewerAgent
from src.agents.observer import ObserverAgent
from src.agents.drafter import DrafterAgent
from src.memory.profile_manager import ProfileManager
from src.tools.slide_generator import SlideGenerator

class Orchestrator:
    def __init__(self):
        self.interviewer = InterviewerAgent()
        self.observer = ObserverAgent()
        self.drafter = DrafterAgent()
        self.slide_generator = SlideGenerator()
        self.system_prompt = self._load_system_prompt()

        self.client = self._init_client()
    
    def _init_client(self):
        try:
            # Using Flash for routing (Router) as it needs to be fast
            from google import genai
            from google.genai.types import HttpOptions
            return genai.Client(http_options=HttpOptions(api_version="v1beta1"))
        except:
             return None

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            return {}

    def _load_system_prompt(self) -> Dict[str, str]:
        return self._load_config().get("system_prompts", {})

    def _classify_intent(self, user_message: str) -> str:
        """
        Classifies user intent using Gemini Flash.
        """
        if not self.client: 
            return "INTERVIEW" # Fallback
            
        router_prompt = self.system_prompt.get("router", "")
        prompt = f"{router_prompt}\n\nUser Input: {user_message}"
        
        router_model = self._load_config().get("model_config", {}).get("router_model")
        if not router_model:
            raise ValueError("router_model not found in config")
        
        try:
            response = self.client.models.generate_content(
                model=router_model,
                contents=prompt
            )
            intent = response.text.strip().upper()
            # Use exact match or startswith to avoid overlap issues
            if intent.startswith("HELP"): return "HELP"
            if intent.startswith("UNKNOWN"): return "UNKNOWN"
            if intent.startswith("DETAIL_GRANT"): return "DETAIL_GRANT"
            if intent.startswith("FIND_RESONANCE"): return "FIND_RESONANCE"
            if intent.startswith("CLEAR_DRAFTS"): return "CLEAR_DRAFTS"
            if intent.startswith("CLEAR_GRANTS"): return "CLEAR_GRANTS"
            if intent.startswith("VIEW_PROFILE"): return "VIEW_PROFILE"
            if intent.startswith("VIEW_GRANTS") or intent.startswith("GRANT_HISTORY"): return "VIEW_GRANTS"
            if intent.startswith("VIEW_DRAFTS"): return "VIEW_DRAFTS"
            if intent.startswith("VIEW") or intent.startswith("LIST"): return "VIEW_DRAFTS"
            if intent.startswith("DRAFT"): return "DRAFT"
            if intent.startswith("OBSERVE"): return "OBSERVE"
            if intent.startswith("INTERVIEW"): return "INTERVIEW"
            return "UNKNOWN"  # Default to UNKNOWN for unclear intents


        except Exception as e:
            print(f"Routing error: {e}")
            return "UNKNOWN"

    def _get_help_message(self) -> str:
        """Returns the help message with all available commands."""
        return """# 🤖 Shadow Director - 機能一覧

**Shadow Director**はNPOの資金調達を支援するAIアシスタントです。

---

## 📋 利用可能なコマンド

**インタビュー**
→ NPO情報をヒアリングしProfile作成(デフォルト)

**プロファイル**
→ 現在のSoul Profileを表示

**共鳴NPOを探す**
→ 同じ志を持つNPOを検索

**助成金を探して**
→ あなたのNPOに合った助成金を検索

**○○について詳しく調べて**
→ 指定した助成金の詳細と5軸評価を表示

**ドラフトを書いて**
→ 助成金申請書のドラフトを自動生成

**ドラフト一覧** / **ドラフトをクリア**
→ ドラフトの一覧表示・削除

**提案済み助成金** / **助成金履歴をクリア**
→ 助成金履歴の表示・リセット

---

## 🚀 使い方の流れ

1️⃣ **まずは自己紹介** - NPOの活動内容を教えてください
2️⃣ **助成金を探す** - 「助成金を探して」と言ってください
3️⃣ **ドラフト作成** - 共鳴度70以上の助成金には自動でドラフトが作成されます

---

💡 **ヒント**: 資料やURLを添付すると、より詳しくNPOを理解できます！
"""


    def route_message(self, user_message: str, user_id: str, **kwargs) -> str:
        """
        Routes the message based on intent.
        Returns: Response message, possibly with [ATTACHMENT_NEEDED] marker.
        """
        intent = self._classify_intent(user_message)
        print(f"Routing Intent: {intent}")

        if intent == "HELP" or intent == "UNKNOWN":
            # Show help message for both HELP and UNKNOWN intents
            return self._get_help_message()

        if intent == "VIEW_GRANTS":
            # View shown grants history
            pm = ProfileManager(user_id=user_id)
            return pm.get_shown_grants_summary()

        if intent == "CLEAR_GRANTS":
            # Clear shown grants history
            pm = ProfileManager(user_id=user_id)
            pm.clear_shown_grants()
            return "✅ 助成金履歴をクリアしました。次回の検索では全ての助成金が提案対象になります。"

        if intent == "VIEW_PROFILE":
            # View Soul Profile
            pm = ProfileManager(user_id=user_id)
            profile = pm.get_profile_context()
            if not profile or profile.strip() == "" or "プロファイルがまだ作成されていません" in profile:
                return "⚠️ Soul Profileがまだ作成されていません。\n\nまずはあなたのNPOについて教えてください。ミッション、活動内容、対象課題などをお話しいただければ、プロファイルを作成します。"
            return f"""# 🌟 Soul Profile

---

{profile}

---

*プロファイルを更新するには、会話を続けてください。新しい情報が自動的に反映されます。*
"""


        if intent == "FIND_RESONANCE":
            # Find resonating NPOs
            pm = ProfileManager(user_id=user_id)
            if not pm._profile.get("insights"):
                return "⚠️ まずはあなたのSoul Profileを作成してください。\n\n共鳴するNPOを探すには、先にあなたのNPOについて教えていただく必要があります。"
            return pm.find_resonating_npos()

        if intent == "CLEAR_DRAFTS":
            # Clear all drafts
            return self.drafter.clear_drafts(user_id)

        if intent == "DETAIL_GRANT":
            # Investigate a specific grant in detail
            # Extract grant name from user message (remove common prefixes)
            grant_name = user_message
            prefixes_to_remove = [
                "について詳しく調べて", "について調べて", "を詳しく",
                "詳しく教えて", "の詳細", "について", "を調べて",
                "詳細を教えて", "について教えて", "深掘り"
            ]
            for prefix in prefixes_to_remove:
                grant_name = grant_name.replace(prefix, "").strip()
            
            if not grant_name or len(grant_name) < 3:
                return "⚠️ 調べたい助成金名を教えてください。例：「○○財団 社会起業家支援助成について詳しく調べて」"
            
            print(f"[DEBUG] Investigating grant: {grant_name}")
            return self.observer.investigate_grant(user_id, grant_name)

        if intent == "VIEW_DRAFTS":
            # View draft functionality
            return self._handle_view_drafts(user_message, user_id)

        if intent == "DRAFT":
            # Create draft and automatically attach file
            message, content, filename = self.drafter.create_draft(user_id, user_message)
            
            if content:
                # Success: send minimal message with attachment marker
                # Details will be in the attached file
                return f"✅ ドラフト作成完了\n📄 ファイルとして送信します...\n[ATTACHMENT_NEEDED:{user_id}:{filename}]"
            else:
                # Error occurred
                return f"❌ ドラフト作成エラー\n{message}"
        
        if intent == "OBSERVE":
            # Manual Observer trigger
            return self._run_observer(user_id)
        
        # Default to Interviewer
        interviewer_response = self.interviewer.process_message(user_message, user_id, **kwargs)
        
        # Check if interview just completed
        if "[INTERVIEW_COMPLETE]" in interviewer_response:
            # Remove the marker from user-facing response
            interviewer_response = interviewer_response.replace("[INTERVIEW_COMPLETE]", "")
            # Auto-trigger Observer
            observer_results = self._run_observer(user_id)
            return f"{interviewer_response}\n\n---\n\n【自動分析開始】\n{observer_results}"
        
        return interviewer_response
    
    def _run_observer(self, user_id: str) -> str:
        """
        Runs the Observer and formats the output with next scheduled run info.
        Auto-triggers Drafter for Strong Match opportunities (resonance score >= 70).
        Filters out previously shown grants.
        """
        from datetime import datetime, timedelta
        
        # Get profile manager for grant history
        pm = ProfileManager(user_id=user_id)
        
        # Run Observer (returns text and parsed opportunities)
        observer_text, opportunities = self.observer.observe(user_id)
        
        # Filter out already shown grants
        new_opportunities = []
        skipped_count = 0
        for opp in opportunities:
            if pm.is_grant_shown(opp):
                skipped_count += 1
                print(f"[DEBUG] Skipping already shown grant: {opp.get('title', 'Unknown')}")
            else:
                new_opportunities.append(opp)
                # Save to shown grants history
                pm.add_shown_grant(opp)
        
        if skipped_count > 0:
            observer_text += f"\n\n⏭️ *{skipped_count}件の助成金は既に提案済みのためスキップしました。*"
        
        # Filter Strong Matches (resonance score >= 70) from NEW opportunities only
        strong_matches = [
            opp for opp in new_opportunities 
            if opp.get("resonance_score", 0) >= 70
        ]
        
        print(f"[DEBUG] Found {len(opportunities)} total, {len(new_opportunities)} new, {len(strong_matches)} Strong Matches")
        
        # Build result message
        result = observer_text
        
        # Auto-trigger Drafter for Strong Matches
        if strong_matches:
            result += "\n\n---\n\n【🎯 Strong Match検出！自動ドラフト生成開始】\n"
            result += f"\n共鳴度70以上の案件が{len(strong_matches)}件見つかりました。スライドとドラフトを自動生成します...\n"
            
            for i, opp in enumerate(strong_matches, 1):
                result += f"\n\n**{i}. {opp['title']} (共鳴度: {opp['resonance_score']})**\n"
                
                # Generate slide image for grant
                try:
                    logging.info(f"[ORCH] Generating slide for: {opp['title']}")
                    image_bytes, slide_filename = self.slide_generator.generate_grant_slide(opp)
                    if image_bytes:
                        gcs_path = self.slide_generator.save_to_gcs(image_bytes, user_id, slide_filename)
                        if gcs_path:
                            result += f"📊 スライド生成完了\n[IMAGE_NEEDED:{user_id}:{slide_filename}]\n"
                except Exception as e:
                    logging.error(f"[ORCH] Slide generation failed: {e}")
                
                # Format grant information for Drafter
                grant_info = f"""助成金名: {opp['title']}
URL: {opp.get('url', 'N/A')}
金額: {opp.get('amount', 'N/A')}
共鳴理由: {opp['reason']}

この助成金の申請書ドラフトを作成してください。"""
                
                # Auto-trigger Drafter
                try:
                    logging.info(f"[ORCH] Auto-triggering Drafter for: {opp['title']}")
                    message, content, filename = self.drafter.create_draft(user_id, grant_info)
                    
                    if content:
                        # Success: add concise message with attachment marker
                        result += f"✅ ドラフト作成完了\n[ATTACHMENT_NEEDED:{user_id}:{filename}]\n"
                    else:
                        # Error occurred
                        result += f"⚠️ ドラフト作成エラー: {message}\n"
                except Exception as e:
                    logging.error(f"[ORCH] Drafter auto-trigger failed for {opp['title']}: {e}")
                    result += f"⚠️ ドラフト作成エラー: {str(e)}\n"
        else:
            result += "\n\n💡 今回は共鳴度70以上の Strong Match は見つかりませんでした。"
        
        # Add footer with next scheduled run
        next_run = datetime.now() + timedelta(days=7)
        next_run_str = next_run.strftime("%Y年%m月%d日")
        
        footer = f"\n\n📅 **次回の自動観察予定**: {next_run_str}\n（手動で観察を実行したい場合は「助成金を探して」と送信してください）"
        
        return result + footer

    def _handle_view_drafts(self, user_message: str, user_id: str) -> str:
        """
        Handles draft viewing requests.
        Returns response with optional [ATTACHMENT_NEEDED] marker.
        """
        msg_lower = user_message.lower()
        
        # List all drafts
        if "一覧" in msg_lower or "リスト" in msg_lower:
            return self.drafter.list_drafts(user_id)
        
        # Get latest draft
        if "最新" in msg_lower:
            message, content = self.drafter.get_latest_draft(user_id)
            if content:
                # Include attachment marker
                return f"{message}\n[ATTACHMENT_NEEDED:{user_id}:latest]"
            return message
        
        # Try to extract filename from message
        # Look for patterns like "XXX.mdを見せて" or "XXXを見せて"
        
        # Pattern 1: explicit filename with .md
        match = re.search(r'([\w\-_]+\.md)', msg_lower)
        if match:
            filename = match.group(1)
            message, content = self.drafter.get_draft(user_id, filename)
            if content:
                return f"{message}\n[ATTACHMENT_NEEDED:{user_id}:{filename}]"
            return message
        
        # Pattern 2: any word before "を見せて" or "見せて"
        match = re.search(r'([\w\-_]+)(?:を)?(?:見せて|表示)', msg_lower)
        if match:
            search_term = match.group(1)
            
            # Get all drafts for fuzzy matching
            drafts = self.drafter.docs_tool.list_drafts(user_id)
            
            if not drafts:
                return "まだドラフトが作成されていません。"
            
            # Fuzzy match: search term in filename
            matches = [d for d in drafts if search_term in d.lower()]
            
            if len(matches) == 1:
                # Exact match found
                filename = matches[0]
                message, content = self.drafter.get_draft(user_id, filename)
                if content:
                    return f"{message}\n[ATTACHMENT_NEEDED:{user_id}:{filename}]"
                return message
            elif len(matches) > 1:
                # Multiple matches - show candidates
                suggestion = "\n\n📝 **候補**:\n" + "\n".join([f"- `{m}`" for m in matches])
                return f"複数のドラフトが見つかりました。より具体的なファイル名を指定してください。{suggestion}"
            else:
                # No matches
                return f"'{search_term}' に一致するドラフトが見つかりませんでした。「ドラフト一覧」で確認してください。"
        
        # Default: show list
        return self.drafter.list_drafts(user_id)

    def run_periodic_checks(self) -> List[Tuple[str, str]]:
        """
        Triggered by scheduler. Checks for funding opportunities for all known profiles.
        Returns a list of (user_id, notification_message).
        """
        notifications = []
        # List all profiles in the profiles directory
        # Assuming LocalProfileStorage structure: profiles/{user_id}_profile.json
        profile_files = glob.glob(os.path.join("profiles", "*_profile.json"))
        
        for file_path in profile_files:
            try:
                filename = os.path.basename(file_path)
                # Extract user_id from filename "user_id_profile.json"
                user_id = filename.replace("_profile.json", "")
                
                print(f"Running periodic check for User: {user_id}")
                observation_result = self.observer.observe(user_id)
                
                # Check if the result is meaningful (has Resonance Score > Threshold implies logic inside observe)
                # For now, Observer returns text. We assume if it returns text, it's worth sending.
                # In future, Observer should return structured object or None.
                if observation_result and "Resonance Score" in observation_result:
                     notifications.append((user_id, observation_result))
                     
            except Exception as e:
                print(f"Error checking profile {file_path}: {e}")
                
        return notifications
