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

    def create_draft(self, user_id: str, grant_info: str) -> str:
        """
        Generates a grant application draft.
        """
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()

        full_prompt = f"""
{self.system_prompt}

Soul Profile:
{profile}

Target Grant Information:
{grant_info}

Task:
Write a full grant application draft for this opportunity.
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            draft_content = response.text
            
            # Save to mock GDocs
            # Extract a title (first line or generic)
            lines = draft_content.split('\n')
            title = "Grant_Draft"
            if lines and lines[0].startswith('# '):
                 title = lines[0].replace('# ', '').strip()
            
            file_path = self.docs_tool.create_document(title, draft_content)
            
            return f"Draft created successfully at: {file_path}\n\n[Preview]\n{draft_content[:200]}..."
            
        except Exception as e:
            return f"Error creating draft: {e}"
