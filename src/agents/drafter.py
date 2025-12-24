from typing import Dict, Any, Optional
import yaml
import os
from google import genai
from google.genai.types import HttpOptions
from src.tools.gdocs_tool import GoogleDocsTool
from src.memory.profile_manager import ProfileManager

class DrafterAgent:
    def __init__(self):
        self.config = self._load_config()
        self.system_prompt = self.config.get("system_prompts", {}).get("drafter", "")
        
        # Initialize Google Gen AI Client
        project_id = self.config.get("model_config", {}).get("project_id")
        location = self.config.get("model_config", {}).get("location", "us-central1")
        
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        
        try:
            self.client = genai.Client(http_options=HttpOptions(api_version="v1beta1"))
        except Exception as e:
            print(f"Failed to init GenAI client: {e}")
            self.client = None
            
        # Using Interviewer model (Pro) for drafting as it requires high reasoning/writing capability
        # Or we can define a separate drafter_model in config if needed. 
        # For now, reusing interviewer_model or defaulting to gemini-2.5-pro
        self.model_name = self.config.get("model_config", {}).get("interviewer_model")
        if not self.model_name:
             raise ValueError("interviewer_model (for drafter) not found in config")
        self.docs_tool = GoogleDocsTool()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def create_draft(self, user_id: str, grant_info: str) -> tuple[str, str, str]:
        """
        Generates a grant application draft.
        
        Returns:
            tuple: (message, draft_content, filename)
        """
        import logging
        logging.info(f"[DRAFTER] create_draft started for user: {user_id}")
        
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()
        
        logging.info(f"[DRAFTER] Profile loaded, length: {len(profile)} chars")

        full_prompt = f"""
{self.system_prompt}

Soul Profile（魂のプロファイル）:
{profile}

対象助成金情報:
{grant_info}

タスク:
この助成金に対する完全な申請書ドラフトを日本語で作成してください。
必ず📋考慮点、🌟アピールポイント、⚠️懸念点のセクションを含めてください。
"""
        try:
            logging.info(f"[DRAFTER] Calling Gemini model: {self.model_name}")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            draft_content = response.text
            logging.info(f"[DRAFTER] Draft generated, length: {len(draft_content)} chars")
            
            # Extract a title (first line or generic)
            lines = draft_content.split('\n')
            title = "Grant_Draft"
            if lines and lines[0].startswith('# '):
                 title = lines[0].replace('# ', '').strip()
            
            logging.info(f"[DRAFTER] Title: {title}")
            
            file_path = self.docs_tool.create_document(title, draft_content, user_id=user_id)
            logging.info(f"[DRAFTER] Document saved: {file_path}")
            
            # Extract filename from path
            import os
            if 'gs://' in file_path:
                # GCS path: gs://bucket/drafts/user_id/filename.md
                filename = file_path.split('/')[-1]
            elif 'Google Doc' in file_path:
                # Google Docs: extract from message
                filename = f"{title}.md"
            else:
                # Local path
                filename = os.path.basename(file_path)
            
            logging.info(f"[DRAFTER] Filename: {filename}")
            
            message = f"ドラフトを作成しました: {file_path}"
            
            logging.info(f"[DRAFTER] create_draft completed successfully")
            return (message, draft_content, filename)
            
        except Exception as e:
            logging.error(f"[DRAFTER] Error in create_draft: {e}", exc_info=True)
            error_msg = f"ドラフト作成エラー: {e}"
            return (error_msg, "", "")

    def list_drafts(self, user_id: str) -> str:
        """
        Lists all drafts for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Formatted list of drafts or message if none found
        """
        try:
            drafts = self.docs_tool.list_drafts(user_id)
            
            if not drafts:
                return "まだドラフトが作成されていません。「助成金申請書を書いて」とリクエストしてください。"
            
            result = f"📄 **保存済みドラフト一覧** ({len(drafts)}件)\n\n"
            for i, filename in enumerate(drafts, 1):
                result += f"{i}. `{filename}`\n"
            
            result += "\n💡 特定のドラフトを見るには「[ファイル名]を見せて」または「最新のドラフトを見せて」と送信してください。"
            
            return result
            
        except Exception as e:
            return f"ドラフト一覧取得エラー: {e}"

    def get_latest_draft(self, user_id: str) -> tuple[str, Optional[str]]:
        """
        Gets the latest draft for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Tuple of (message, content). If content is present, it should be sent as attachment.
        """
        try:
            drafts = self.docs_tool.list_drafts(user_id)
            
            if not drafts:
                return ("まだドラフトが作成されていません。", None)
            
            # Sort by filename (which includes timestamp)
            latest_draft = sorted(drafts)[-1]
            content = self.docs_tool.get_draft(user_id, latest_draft)
            
            if not content:
                return (f"ドラフト '{latest_draft}' が見つかりませんでした。", None)
            
            message = f"📄 **最新のドラフト**: `{latest_draft}`\n\n"
            
            # If content is short, include it in message
            if len(content) <= 1800:
                message += f"```markdown\n{content}\n```"
                return (message, None)
            else:
                # Return content for file attachment
                message += "（ファイルとして送信します）"
                return (message, content)
                
        except Exception as e:
            return (f"最新ドラフト取得エラー: {e}", None)

    def get_draft(self, user_id: str, filename: str) -> tuple[str, Optional[str]]:
        """
        Gets a specific draft by filename.
        
        Args:
            user_id: User ID
            filename: Draft filename
            
        Returns:
            Tuple of (message, content). If content is present, it should be sent as attachment.
        """
        try:
            content = self.docs_tool.get_draft(user_id, filename)
            
            if not content:
                # Try fuzzy match
                drafts = self.docs_tool.list_drafts(user_id)
                matches = [d for d in drafts if filename.lower() in d.lower()]
                
                if matches:
                    if len(matches) == 1:
                        # Use the matched file
                        filename = matches[0]
                        content = self.docs_tool.get_draft(user_id, filename)
                    else:
                        suggestion = "\n\n候補:\n" + "\n".join([f"- {m}" for m in matches])
                        return (f"ファイル名が曖昧です。{suggestion}", None)
                else:
                    return (f"ドラフト '{filename}' が見つかりませんでした。「ドラフト一覧」で確認してください。", None)
            
            message = f"📄 **ドラフト**: `{filename}`\n\n"
            
            # If content is short, include it in message
            if len(content) <= 1800:
                message += f"```markdown\n{content}\n```"
                return (message, None)
            else:
                # Return content for file attachment
                message += "（ファイルとして送信します）"
                return (message, content)
                
        except Exception as e:
            return (f"ドラフト取得エラー: {e}", None)

