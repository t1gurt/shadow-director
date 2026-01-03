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

from src.agents.pr_agent import PRAgent
from src.version import get_version_info


class Orchestrator:
    def __init__(self):
        self.interviewer = InterviewerAgent()
        self.observer = ObserverAgent()
        self.drafter = DrafterAgent()
        self.pr_agent = PRAgent()
        self.slide_generator = SlideGenerator()
        self.system_prompt = self._load_system_prompt()

        self.client = self._init_client()
    
    def _init_client(self):
        """Initialize Gemini client using Vertex AI backend."""
        try:
            from src.utils.gemini_client import get_gemini_client
            return get_gemini_client()
        except Exception as e:
            logging.error(f"[ORCHESTRATOR] Failed to initialize Gemini client: {e}")
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
            
            # Debug logging for intent classification
            logging.info(f"[INTENT] User: '{user_message}' → Model returned: '{intent}'")
            
            # Handle empty or invalid response with keyword-based fallback
            if not intent or len(intent) == 0:
                logging.warning(f"[INTENT] Empty response from model, using keyword fallback")
                # Keyword-based fallback for critical intents
                msg_lower = user_message.lower()
                if "助成金" in msg_lower and ("探して" in msg_lower or "検索" in msg_lower or "見つけて" in msg_lower):
                    logging.info(f"[INTENT] Fallback: Detected OBSERVE intent via keywords")
                    return "OBSERVE"
                elif "バージョン" in msg_lower or "version" in msg_lower:
                    logging.info(f"[INTENT] Fallback: Detected VERSION intent via keywords")
                    return "VERSION"
                elif "ヘルプ" in msg_lower or "help" in msg_lower:
                    logging.info(f"[INTENT] Fallback: Detected HELP intent via keywords")
                    return "HELP"
                elif "ドラフト" in msg_lower and "書いて" in msg_lower:
                    logging.info(f"[INTENT] Fallback: Detected DRAFT intent via keywords")
                    return "DRAFT"
                else:
                    logging.info(f"[INTENT] Fallback: No keywords matched, defaulting to INTERVIEW")
                    return "INTERVIEW"
            
            # Use exact match or startswith to avoid overlap issues
            # Check specific intents BEFORE generic ones like HELP/UNKNOWN
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
            
            # PR Agent Intents
            if intent.startswith("PR_REMEMBER_SNS"): return "PR_REMEMBER_SNS"
            if intent.startswith("PR_MONTHLY_SUMMARY"): return "PR_MONTHLY_SUMMARY"
            if intent.startswith("PR_CREATE_POST"): return "PR_CREATE_POST"
            if intent.startswith("PR_SEARCH_RELATED"): return "PR_SEARCH_RELATED"
            
            # Version Intent - check BEFORE HELP/UNKNOWN
            if intent.startswith("VERSION"): return "VERSION"
            
            # Generic intents - check LAST
            if intent.startswith("HELP"): return "HELP"
            if intent.startswith("INTERVIEW"): return "INTERVIEW"
            if intent.startswith("UNKNOWN"): return "UNKNOWN"
            
            return "UNKNOWN"  # Default to UNKNOWN for unclear intents


        except Exception as e:
            logging.error(f"[INTENT] Routing error: {e}", exc_info=True)
            # Keyword-based fallback on exception
            msg_lower = user_message.lower()
            if "助成金" in msg_lower and ("探して" in msg_lower or "検索" in msg_lower):
                logging.info(f"[INTENT] Exception fallback: OBSERVE")
                return "OBSERVE"
            elif "バージョン" in msg_lower or "version" in msg_lower:
                logging.info(f"[INTENT] Exception fallback: VERSION")
                return "VERSION"
            return "UNKNOWN"

    def _get_help_message(self) -> str:
        """Returns the help message with all available commands."""
        return """# 🤖 Shadow Director - 機能一覧

**Shadow Director**はNPOの資金調達と広報活動を支援するAIアシスタントです。

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

**ドラフトを書いて**
→ 助成金申請書のドラフトを自動生成

**投稿記事を作って**
→ Facebook/Instagram用の投稿記事ドラフトを作成
(写真やイベント詳細を一緒に送信してください)

**月次サマリ**
→ 今月の活動サマリレポートを作成

**関連情報を探して**
→ 興味のあるキーワードで最新情報を検索

**SNS URLを記憶**
→ 「FacebookのURLを記憶して: [URL]」のように指示

**バージョン**
→ Botのバージョン情報と最新機能を確認

---

## 🚀 使い方の流れ

1️⃣ **まずは自己紹介** - NPOの活動内容を教えてください
2️⃣ **助成金を探す** - 「助成金を探して」と言ってください
3️⃣ **広報支援** - イベントの写真などを送って「記事を作って」

---

💡 **ヒント**: 資料やURLを添付すると、より詳しくNPOを理解できます！
"""


    def route_message(self, user_message: str, user_id: str, attachments=None, **kwargs) -> str:
        """
        Routes the message based on intent.
        Returns: Response message, possibly with [ATTACHMENT_NEEDED] marker.
        
        Args:
            attachments: Discord attachments (for file uploads like PDFs, images)
        """
        intent = self._classify_intent(user_message)
        print(f"Routing Intent: {intent}")

        if intent == "VERSION":
            # Show version information
            return get_version_info()
        
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
            message, content, filename, format_files = self.drafter.create_draft(user_id, user_message)
            
            # Build response with format files first, then draft
            response = ""
            if format_files:
                response += "📎 **申請フォーマットファイル** が見つかりました:\n"
                for file_path, file_name in format_files:
                    response += f"[FORMAT_FILE_NEEDED:{user_id}:{file_path}]\n"
                response += "\n"
            else:
                # Notify user that no format files were found
                response += "ℹ️ 申請フォーマットファイルは見つかりませんでした。一般的な申請書形式でドラフトを作成しました。\n\n"
            
            if content:
                # Success: send minimal message with attachment marker
                response += f"✅ ドラフト作成完了\n📄 ファイルとして送信します...\n[ATTACHMENT_NEEDED:{user_id}:{filename}]"
                return response
            else:
                # Error occurred
                return response + f"❌ ドラフト作成エラー\n{message}"
        
        if intent == "OBSERVE":
            # Manual Observer trigger
            return self._run_observer(user_id)
            
        # --- PR Agent Intents ---
        if intent == "PR_REMEMBER_SNS":
            # Extract basic URL pattern
            urls = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', user_message)
            if not urls:
                return "⚠️ URLが見つかりませんでした。「FacebookのURLを記憶して: https://...」のように指定してください。"
            
            platform = "website"
            if "facebook" in user_message.lower(): platform = "facebook"
            elif "instagram" in user_message.lower() or "インスタ" in user_message: platform = "instagram"
            elif "twitter" in user_message.lower() or "x.com" in user_message: platform = "twitter"
            
            return self.pr_agent.remember_sns_info(user_id, platform, urls[0])
            
        if intent == "PR_MONTHLY_SUMMARY":
            return self.pr_agent.generate_monthly_summary(user_id)
            
        if intent == "PR_CREATE_POST":
            # Determine platform
            platform = "Facebook"
            if "instagram" in user_message.lower() or "インスタ" in user_message:
                platform = "Instagram"
            
            # Process attachments if provided
            attachment_data = None
            if attachments and len(attachments) > 0:
                attachment_data = attachments  # Pass Discord attachments directly
            
            return self.pr_agent.create_post_draft(user_id, platform, user_message, attachments=attachment_data)

        if intent == "PR_SEARCH_RELATED":
            return self.pr_agent.search_related_info(user_id, user_message)
        
        # Default to Interviewer
        # If attachments exist, use interviewer's file processing
        if attachments and len(attachments) > 0:
            # For interview intent with attachments, use the file processing method
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in async context, but interviewer method is async
                # This is a sync method, so we need to handle this carefully
                # For now, just pass text and note that files were attached
                interviewer_response = self.interviewer.process_message(
                    user_message + f"\n\n(添付ファイル: {len(attachments)}件を含む)", 
                    user_id, 
                    **kwargs
                )
            else:
                interviewer_response = self.interviewer.process_message(user_message, user_id, **kwargs)
        else:
            interviewer_response = self.interviewer.process_message(user_message, user_id, **kwargs)
        
        # Check if interview just completed
        if "[INTERVIEW_COMPLETE]" in interviewer_response:
            # Remove the marker from user-facing response
            interviewer_response = interviewer_response.replace("[INTERVIEW_COMPLETE]", "")
            # Auto-trigger Observer
            observer_results = self._run_observer(user_id)
            return f"{interviewer_response}\n\n---\n\n【自動分析開始】\n{observer_results}"
        
        return interviewer_response
    
    def _run_observer(self, user_id: str, message_callback=None) -> str:
        """
        Runs the Observer and formats the output with next scheduled run info.
        Auto-triggers Drafter for Strong Match opportunities (resonance score >= 70).
        Filters out previously shown grants.
        
        Args:
            user_id: User/Channel ID
            message_callback: Optional async callback function to send messages immediately
                             Signature: async def callback(message: str, attachments: list = None)
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
        
        # Build result message - first send the search results
        result = observer_text
        
        # Auto-trigger Drafter for Strong Matches - process sequentially
        if strong_matches:
            result += f"\n\n---\n\n【🎯 Strong Match検出！自動ドラフト生成開始】\n"
            result += f"\n共鳴度70以上の案件が{len(strong_matches)}件見つかりました。\n"
            result += "それぞれの助成金について順番に調査し、ドラフトを作成します...\n"
            
            # Process each grant SEQUENTIALLY with immediate message sending
            for i, opp in enumerate(strong_matches, 1):
                grant_title = opp['title']
                grant_url = opp.get('official_url', 'N/A')
                grant_result = f"\n\n---\n\n## 🔍 助成金 {i}/{len(strong_matches)}: {grant_title}\n"
                grant_result += f"**(共鳴度: {opp['resonance_score']})**\n\n"
                
                # Step 1: Generate slide image for grant
                grant_result += "**Step 1: スライド生成中...**\n"
                try:
                    logging.info(f"[ORCH] Generating slide for: {grant_title}")
                    image_bytes, slide_filename = self.slide_generator.generate_grant_slide(opp)
                    if image_bytes:
                        gcs_path = self.slide_generator.save_to_gcs(image_bytes, user_id, slide_filename)
                        if gcs_path:
                            grant_result += f"📊 スライド生成完了\n[IMAGE_NEEDED:{user_id}:{slide_filename}]\n"
                except Exception as e:
                    logging.error(f"[ORCH] Slide generation failed: {e}")
                    grant_result += f"⚠️ スライド生成スキップ\n"
                
                # Step 2: Get detailed grant information
                grant_result += "\n**Step 2: 助成金詳細を調査中...**\n"
                grant_details = ""
                format_files = []
                try:
                    logging.info(f"[ORCH] Getting details for: {grant_title}")
                    # Use Drafter's research function to get grant format info
                    grant_details, format_files = self.drafter._research_grant_format(
                        grant_title, user_id, grant_url=grant_url
                    )
                    
                    if grant_details:
                        # Summarize the key details
                        grant_result += f"📋 詳細取得完了\n"
                        # Add key info from details (truncated for display)
                        detail_summary = grant_details[:500] + "..." if len(grant_details) > 500 else grant_details
                        grant_result += f"\n```\n{detail_summary}\n```\n"
                    else:
                        grant_result += "ℹ️ 詳細情報は基本情報のみ\n"
                except Exception as e:
                    logging.error(f"[ORCH] Grant details fetch failed: {e}")
                    grant_result += f"⚠️ 詳細取得スキップ（基本情報で続行）\n"
                
                # Add format file markers if found during research
                if format_files:
                    grant_result += "📎 申請フォーマットファイル:\n"
                    for file_path, file_name in format_files:
                        grant_result += f"[FORMAT_FILE_NEEDED:{user_id}:{file_path}]\n"
                
                # Step 3: Create draft for this grant using collected information
                grant_result += "\n**Step 3: ドラフト作成中...**\n"
                
                # Format grant information for Drafter with detailed info
                grant_info = f"""助成金名: {opp['title']}
URL: {grant_url}
金額: {opp.get('amount', 'N/A')}
締切: {opp.get('deadline_end', 'N/A')}
共鳴理由: {opp['reason']}

【詳細情報】
{grant_details if grant_details else '詳細情報なし'}

この助成金の申請書ドラフトを作成してください。"""
                
                try:
                    logging.info(f"[ORCH] Auto-triggering Drafter for: {grant_title}")
                    message, content, filename, draft_format_files = self.drafter.create_draft(user_id, grant_info)
                    
                    # Add any additional format files found during draft creation
                    if draft_format_files and not format_files:
                        grant_result += "📎 申請フォーマットファイル:\n"
                        for file_path, file_name in draft_format_files:
                            grant_result += f"[FORMAT_FILE_NEEDED:{user_id}:{file_path}]\n"
                    elif not format_files and not draft_format_files:
                        grant_result += "ℹ️ 申請フォーマットファイルは見つかりませんでした。\n"
                    
                    if content:
                        grant_result += f"✅ ドラフト作成完了\n[ATTACHMENT_NEEDED:{user_id}:{filename}]\n"
                    else:
                        grant_result += f"⚠️ ドラフト作成エラー: {message}\n"
                except Exception as e:
                    logging.error(f"[ORCH] Drafter auto-trigger failed for {grant_title}: {e}")
                    grant_result += f"⚠️ ドラフト作成エラー: {str(e)}\n"
                
                grant_result += f"\n✨ **{grant_title}** の処理完了\n"
                
                # Immediately send this grant's result to Discord via callback
                if message_callback:
                    try:
                        import asyncio
                        # If callback is async, run it
                        if asyncio.iscoroutinefunction(message_callback):
                            asyncio.create_task(message_callback(grant_result))
                        else:
                            message_callback(grant_result)
                    except Exception as e:
                        logging.error(f"[ORCH] Message callback failed: {e}")
                        # Fall back to accumulating result
                        result += grant_result
                else:
                    # No callback, accumulate results
                    result += grant_result
                    
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

    def run_monthly_tasks(self) -> List[Tuple[str, str]]:
        """
        Triggered by scheduler on the 1st of every month.
        Generates monthly summary for all known profiles.
        Returns a list of (user_id, summary_text).
        """
        notifications = []
        profile_files = glob.glob(os.path.join("profiles", "*_profile.json"))
        
        for file_path in profile_files:
            try:
                filename = os.path.basename(file_path)
                user_id = filename.replace("_profile.json", "")
                
                print(f"Running monthly summary for User: {user_id}")
                
                # Generate Monthly Summary
                summary = self.pr_agent.generate_monthly_summary(user_id)
                
                # Save to history (ProfileManager extension required, but for now assuming it's part of pr_agent or pm)
                # Ideally PR Agent handles saving, but let's ensure here.
                pm = ProfileManager(user_id=user_id)
                pm.add_monthly_summary(summary)
                
                notifications.append((user_id, f"📅 **【自動実行】月次活動サマリを作成しました**\n\n{summary}"))
                     
            except Exception as e:
                print(f"Error running monthly task for {file_path}: {e}")
                
        return notifications
