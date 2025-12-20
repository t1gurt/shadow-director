from typing import Dict, Any, List, Optional
import yaml
import os
from google import genai
from google.genai.types import HttpOptions
from src.memory.profile_manager import ProfileManager

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
            self.client = genai.Client(http_options=HttpOptions(api_version="v1"))
        except Exception as e:
            print(f"Failed to init GenAI client: {e}")
            self.client = None
        
        self.model_name = self.config.get("model_config", {}).get("interviewer_model", "gemini-1.5-pro-002")

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
        """
        # Instantiate ProfileManager for this specific user
        pm = ProfileManager(user_id=user_id)
        current_profile = pm.get_profile_context()
        
        # Format the system prompt with turn_count
        prompt_content = self.system_prompt.replace("{turn_count}", str(turn_count))

        # Construct the full prompt for the LLM
        full_prompt = f"""
{prompt_content}

{current_profile}

User: {user_message}
Agent:
"""
        try:
            # 1. Generate response to user
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            response_text = response.text

            # 2. Extract and save insights (Fire and forget, or sequential)
            # For mock, sequential is fine.
            self._extract_insights(user_message, response_text, user_id, pm)

            return response_text
        except Exception as e:
            return f"Error communicating with AI: {e}"

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
