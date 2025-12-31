from typing import Dict, Any, List, Tuple, Optional
import yaml
import os
import re
import logging
from datetime import datetime
from google import genai
from google.genai.types import HttpOptions, GenerateContentConfig

from src.memory.profile_manager import ProfileManager
from src.tools.search_tool import SearchTool

class PRAgent:
    def __init__(self):
        self.config = self._load_config()
        self.client = self._init_client()
        self.model_name = self.config.get("model_config", {}).get("interviewer_model") # Use Pro model for drafting
        self.search_tool = SearchTool()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def _init_client(self):
        project_id = self.config.get("model_config", {}).get("project_id")
        location = self.config.get("model_config", {}).get("location", "us-central1")
        
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        
        try:
            return genai.Client(http_options=HttpOptions(api_version="v1beta1"))
        except Exception as e:
            print(f"Failed to init GenAI client: {e}")
            return None

    def remember_sns_info(self, user_id: str, platform: str, url: str) -> str:
        """
        Stores user's SNS information in their profile.
        """
        pm = ProfileManager(user_id=user_id)
        pm.update_sns_info(platform, url)
        return f"✅ {platform}の情報を記憶しました。\nURL: {url}"

    def generate_monthly_summary(self, user_id: str, target_month: Optional[str] = None) -> str:
        """
        Generates a monthly activity summary based on profile and recent history.
        """
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()
        
        if not target_month:
            target_month = datetime.now().strftime("%Y年%m月")

        # Get system prompt for summary
        system_prompt = self.config.get("system_prompts", {}).get("pr_monthly_summary", "")
        
        # Construct prompt
        prompt = f"""
{system_prompt}

対象年月: {target_month}

現在のNPOプロファイル:
{profile}

最近の活動履歴(助成金検索履歴など):
{pm.get_shown_grants_summary()}

上記情報を元に、今月の広報用活動サマリを作成してください。
"""
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"❌ 月次サマリの作成中にエラーが発生しました: {str(e)}"

    def create_post_draft(self, user_id: str, platform: str, content_context: str, attachments=None) -> str:
        """
        Creates a draft for an SNS post (Facebook/Instagram).
        
        Args:
            attachments: Discord attachment objects (can be PDF or images)
        """
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()

        # Select prompt based on platform
        if platform.lower() == "facebook":
            system_prompt_key = "pr_facebook_post"
        elif platform.lower() == "instagram":
            system_prompt_key = "pr_instagram_post"
        else:
            system_prompt_key = "pr_facebook_post" # Default

        system_prompt = self.config.get("system_prompts", {}).get(system_prompt_key, "")

        # Process attachments if provided
        attachment_parts = []
        attachment_descriptions = []
        
        if attachments and len(attachments) > 0:
            import requests
            from google.genai import types
            
            # Download attachments synchronously using requests
            logging.info(f"Downloading {len(attachments)} attachments...")
            for attachment in attachments:
                try:
                    logging.info(f"Downloading attachment: {attachment.filename} ({attachment.url})")
                    # Download file content
                    response = requests.get(attachment.url, timeout=30)
                    response.raise_for_status()
                    
                    filename = attachment.filename
                    content = response.content
                    content_type = attachment.content_type
                    logging.info(f"Downloaded {filename}: {len(content)} bytes, type: {content_type}")
                    
                    # Handle different file types
                    if content_type and 'image' in content_type:
                        # Image file - pass directly to Gemini
                        attachment_parts.append(types.Part.from_bytes(
                            data=content,
                            mime_type=content_type
                        ))
                        attachment_descriptions.append(f"画像ファイル: {filename}")
                    
                    elif filename.lower().endswith('.pdf') or (content_type and 'pdf' in content_type):
                        # PDF file - pass directly to Gemini (Gemini supports PDFs)
                        attachment_parts.append(types.Part.from_bytes(
                            data=content,
                            mime_type='application/pdf'
                        ))
                        attachment_descriptions.append(f"PDFファイル: {filename}")
                    
                    else:
                        # Unknown file type
                        attachment_descriptions.append(f"ファイル: {filename} (タイプ不明)")
                        logging.warning(f"Unknown file type for {filename}: {content_type}")
                
                except Exception as e:
                    logging.error(f"Failed to download attachment {attachment.filename}: {e}")
                    return f"❌ 添付ファイル '{attachment.filename}' のダウンロード中にエラーが発生しました: {str(e)}"

        # Build the attachment info text
        if attachment_descriptions:
            attachment_info = "\n".join([f"- {desc}" for desc in attachment_descriptions])
        else:
            attachment_info = "画像・資料なし"

        # Create prompt
        text_prompt = f"""{system_prompt}

NPOプロファイル:
{profile}

投稿のネタ(企画書・写真の内容など):
{content_context}

添付ファイル:
{attachment_info}

この内容を元に、{platform}用の素晴らしい投稿記事ドラフトを作成してください。
"""

        try:
            # Prepare contents for Gemini
            contents = []
            
            # Add text part
            contents.append(text_prompt)
            
            # Add attachment parts (images/PDFs)
            if attachment_parts:
                contents.extend(attachment_parts)
            
            logging.info(f"Calling Gemini API (model: {self.model_name}) with {len(contents)} parts...")
            start_time = datetime.now()
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            logging.info(f"Gemini API returned successfully in {duration:.2f}s")
            return response.text
        except Exception as e:
            logging.error(f"Gemini API Error: {e}")
            return f"❌ 記事作成エラー: {str(e)}"

    def search_related_info(self, user_id: str, keywords: str) -> str:
        """
        Searches for related information using Google Search.
        """
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()

        system_prompt = self.config.get("system_prompts", {}).get("pr_related_search", "")
        
        prompt = f"""
{system_prompt}

NPOプロファイル:
{profile}

検索キーワード・関心事項:
{keywords}

上記に関連する最新のニュース、トレンド、他団体の活動事例などを検索して報告してください。
"""
        
        try:
            # Enable Google Search Tool
            tool_config = self.search_tool.get_tool_config()
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=GenerateContentConfig(
                    tools=[tool_config]
                )
            )
            
            # Simple grounding check (can be improved similar to Observer)
            return response.text
        except Exception as e:
             return f"❌ 検索エラー: {str(e)}"
