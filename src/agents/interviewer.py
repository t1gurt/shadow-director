from typing import Dict, Any, List, Optional
import yaml
import os
import re
from google import genai
from google.genai.types import HttpOptions, File
from src.memory.profile_manager import ProfileManager
from src.tools.file_processor import FileProcessor

class InterviewerAgent:
    def __init__(self, profile_manager: Optional[ProfileManager] = None):
        # We allow passing a profile_manager for testing, but typically it's created per request
        self.profile_manager = profile_manager
        self.config = self._load_config()
        self.system_prompt = self.config.get("system_prompts", {}).get("interviewer", "")
        
        # Initialize Google Gen AI Client (Vertex AI Mode)
        project_id = self.config.get("model_config", {}).get("project_id")
        if not project_id:
             # Just a warning or default might be unsafe, but sticking to existing logic pattern
             # raising error is better if strictly needed, but let's handle gracefully if config missing
             pass 
             # raise ValueError("project_id not found in config/prompts.yaml")

        location = self.config.get("model_config", {}).get("location", "us-central1")
        
        # Set environment variables for the SDK
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        
        print(f"Initializing Interviewer with google-genai SDK. Project: {project_id}, Location: {location}")
        try:
            self.client = genai.Client(http_options=HttpOptions(api_version="v1beta1"))
        except Exception as e:
            print(f"Failed to init GenAI client: {e}")
            self.client = None
        
        self.model_name = self.config.get("model_config", {}).get("interviewer_model")
        if not self.model_name:
             raise ValueError("interviewer_model not found in config")
        
        # Initialize File Processor
        self.file_processor = FileProcessor(self.client) if self.client else None

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def process_message(self, user_message: str, user_id: str, turn_count: int = 1) -> str:
        """
        Processes the user message using Vertex AI Gemini model (google-genai SDK).
        Now includes conversation history for context continuity.
        """
        # Instantiate ProfileManager for this specific user
        pm = ProfileManager(user_id=user_id)
        current_profile = pm.get_profile_context()
        
        # Get conversation history and calculate actual turn count
        history = pm.get_conversation_history()
        actual_turn_count = pm.get_turn_count() + 1  # +1 for the current turn
        
        # Format the system prompt with turn_count
        prompt_content = self.system_prompt.replace("{turn_count}", str(actual_turn_count))

        # Build conversation history context
        history_context = ""
        if history:
            history_context = "\n【これまでの会話履歴】\n"
            for turn in history:
                role_label = "ユーザー" if turn["role"] == "user" else "エージェント"
                history_context += f"{role_label}: {turn['content']}\n"
            history_context += "\n"

        # Construct the full prompt for the LLM with history
        full_prompt = f"""
{prompt_content}

{current_profile}

{history_context}ユーザー: {user_message}
エージェント:
"""
        try:
            # 1. Generate response to user
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            response_text = response.text

            # 2. Check if this is an interview question (has understanding level marker)
            # Only count as a turn if it contains understanding level display
            is_interview_question = "[設立者の魂理解度:" in response_text or "[理解度:" in response_text
            
            # 3. Save this turn to conversation history
            pm.add_to_history("user", user_message)
            pm.add_to_history("agent", response_text)
            
            # 4. Only increment turn_count if this is an actual interview question
            # Greetings, clarifications, and thank-you messages won't count
            if is_interview_question:
                # Extract and save insights (Fire and forget, or sequential)
                self._extract_insights(user_message, response_text, user_id, pm)

                # Check if interview is complete (15 turns)
                if actual_turn_count >= 15:
                    response_text += "\n\n[INTERVIEW_COMPLETE]"
            else:
                # This is a greeting/clarification - don't count it as a turn
                # The turn_count will remain the same, so next actual question will use the same number
                print(f"[DEBUG] Response is not an interview question (no understanding level marker), not counting as turn")

            return response_text
        except Exception as e:
            return f"Error communicating with AI: {e}"
    
    
    async def process_with_files_and_urls(self, user_message: str, user_id: str, 
                                           attachments: List[Any] = None, 
                                           turn_count: int = 1) -> str:
        """
        Process message with file attachments and/or URLs, then continue with interview.
        
        Args:
            user_message: User's text message
            user_id: User/Channel ID
            attachments: Discord attachments list
            turn_count: Current turn number
            
        Returns:
            Response text with document analysis + interview question
        """
        if not self.file_processor:
            # Fallback to normal interview if file processor unavailable
            return self.process_message(user_message, user_id, turn_count)
        
        pm = ProfileManager(user_id=user_id)
        
        # Extract URLs from message
        urls = self.file_processor.extract_urls(user_message)
        print(f"[DEBUG] Extracted URLs from message: {urls}")
        
        # Process attachments if any
        uploaded_files = []
        if attachments:
            print(f"[DEBUG] Found {len(attachments)} attachments")
            for att in attachments:
                print(f"[DEBUG]   - Attachment: {att.filename} ({att.content_type}, {att.size} bytes, URL: {att.url})")
            try:
                uploaded_files = await self.file_processor.process_discord_attachments(attachments)
                print(f"[DEBUG] Successfully uploaded {len(uploaded_files)} files to Gemini")
            except Exception as e:
                print(f"[ERROR] Attachment processing error: {e}")
                # File processing failed - inform user and don't count this as a turn
                error_response = f"申し訳ありません。ファイルの読み込みに失敗しました。\n\nエラー: {str(e)}\n\n通常の対話形式で情報を教えていただけますか？"
                # Save error message to history but don't increment turn
                pm.add_to_history("user", user_message + " [添付ファイルあり]")
                pm.add_to_history("agent", error_response)
                return error_response
        
        # If no files/URLs, just do normal interview
        if not uploaded_files and not urls:
            print(f"[DEBUG] No files or URLs detected, proceeding with normal interview")
            return self.process_message(user_message, user_id, turn_count)
        
        print(f"[DEBUG] Starting document analysis - {len(uploaded_files)} files, {len(urls)} URLs")
        
        # Build analysis prompt
        analysis_parts = []
        
        # Add files to prompt
        for file in uploaded_files:
            analysis_parts.append(file)
        
        # Build text instruction
        instruction = f"""
以下の資料から団体の情報を抽出してください：

【抽出する情報】
- 団体名
- 設立年月日
- 活動目的・ミッション
- 主な活動内容
- 対象者・受益者
- 特徴・強み

【資料】
"""
        
        if urls:
            instruction += f"\n📎 URL: {', '.join(urls)}\n"
        
        if uploaded_files:
            instruction += f"\n📄 添付ファイル: {len(uploaded_files)}件\n"
        
        instruction += f"\n【ユーザーメッセージ】\n{user_message}"
        instruction += "\n\n抽出した情報を簡潔にまとめて報告してください。"
        
        analysis_parts.append(instruction)
        
        try:
            # Analyze documents
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=analysis_parts
            )
            
            analysis_result = response.text
            
            # Save document analysis to conversation history
            pm.add_to_history("user", f"[資料提供] {user_message}")
            pm.add_to_history("agent", f"[資料分析] {analysis_result}")
            
            # Extract insights from the analysis
            self._extract_insights(user_message, analysis_result, user_id, pm)
            
            # Now continue with interview based on the analyzed information
            # Get updated profile
            current_profile = pm.get_profile_context()
            actual_turn_count = pm.get_turn_count() + 1
            
            # Build interview prompt with analyzed info
            prompt_content = self.system_prompt.replace("{turn_count}", str(actual_turn_count))
            
            interview_prompt = f"""
{prompt_content}

{current_profile}

【これまでの経緯】
資料を分析し、以下の情報を取得しました：
{analysis_result[:300]}...

上記の情報を踏まえて、さらに深く理解するための質問を1つしてください。
既に分かっている情報は繰り返し聞かないでください。
"""
            
            # Generate interview question
            interview_response = self.client.models.generate_content(
                model=self.model_name,
                contents=interview_prompt
            )
            
            interview_question = interview_response.text
            
            # Save interview turn
            pm.add_to_history("agent", interview_question)
            
            # Combine document analysis + interview question
            full_response = f"📚 **資料を分析しました**\n\n{analysis_result}\n\n---\n\n{interview_question}"
            
            return full_response
            
        except Exception as e:
            print(f"Document analysis error: {e}")
            # Fallback to normal interview
            return self.process_message(user_message, user_id, turn_count)

    def _extract_insights(self, user_input: str, agent_response: str, user_id: str, pm: ProfileManager) -> None:
        """
        Analyzes the latest turn to extract insights and update the profile.
        """
        import json
        
        insight_prompt = self.config.get("system_prompts", {}).get("insight_extractor", "")
        if not insight_prompt:
            return

        # Simple context for extraction: just the last turn
        extraction_input = f"""
{insight_prompt}

Conversation to Analyze:
User: {user_input}
Agent: {agent_response}
"""
        try:
            # parsing can be fragile. We ask for JSON.
            # Using a simpler model for extraction if possible, but using same model for now is fine.
            extraction_response = self.client.models.generate_content(
                model=self.model_name,
                contents=extraction_input,
                config={'response_mime_type': 'application/json'} # Use JSON mode if supported or prompt engineering
            )
            
            # Clean up potential markdown code blocks if the model puts them in
            text = extraction_response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            
            data = json.loads(text)
            insights = data.get("extracted_insights", [])
            
            if insights:
                print(f"[Debug] Extracted Insights: {len(insights)}")
                for item in insights:
                    category = item.get("category")
                    content = item.get("content")
                    if category and content:
                        print(f"  - Saving {category}: {content[:30]}...")
                        pm.update_key_insight(category, content)

        except Exception as e:
            print(f"[Debug] Insight extraction failed: {e}")
