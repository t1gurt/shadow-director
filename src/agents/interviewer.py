from typing import Dict, Any, List, Optional
import yaml
import os
from google import genai
from google.genai.types import HttpOptions
from src.memory.profile_manager import ProfileManager

class InterviewerAgent:
    def __init__(self, profile_manager: ProfileManager):
        self.profile_manager = profile_manager
        self.config = self._load_config()
        self.system_prompt = self.config.get("system_prompts", {}).get("interviewer", "")
        
        # Initialize Google Gen AI Client (Vertex AI Mode)
        project_id = self.config.get("model_config", {}).get("project_id")
        if not project_id:
             raise ValueError("project_id not found in config/prompts.yaml")

        location = self.config.get("model_config", {}).get("location", "us-central1")
        
        # Set environment variables for the SDK
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        
        print(f"Initializing Interviewer with google-genai SDK. Project: {project_id}, Location: {location}")
        self.client = genai.Client(http_options=HttpOptions(api_version="v1"))
        
        self.model_name = self.config.get("model_config", {}).get("interviewer_model", "gemini-2.5-flash")

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def process_message(self, user_message: str) -> str:
        """
        Processes the user message using Vertex AI Gemini model (google-genai SDK).
        """
        current_profile = self.profile_manager.get_profile_context()
        
        # Construct the full prompt for the LLM
        full_prompt = f"""
{self.system_prompt}

{current_profile}

User: {user_message}
Agent:
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            return response.text
        except Exception as e:
            return f"Error communicating with AI: {e}"
