from typing import Dict, Any, List, Tuple
import yaml
import os
import glob
from src.agents.interviewer import InterviewerAgent
from src.agents.observer import ObserverAgent
from src.agents.drafter import DrafterAgent
from src.memory.profile_manager import ProfileManager

class Orchestrator:
    def __init__(self):
        self.interviewer = InterviewerAgent()
        self.observer = ObserverAgent()
        self.drafter = DrafterAgent()
        self.system_prompt = self._load_system_prompt()

        self.client = self._init_client()
    
    def _init_client(self):
        try:
            # Using Flash for routing (Router) as it needs to be fast
            from google import genai
            from google.genai.types import HttpOptions
            return genai.Client(http_options=HttpOptions(api_version="v1"))
        except:
             return None

    def _load_system_prompt(self) -> Dict[str, str]:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("system_prompts", {})
        except Exception:
            return {}

    def _classify_intent(self, user_message: str) -> str:
        """
        Classifies user intent using Gemini Flash.
        """
        if not self.client: 
            return "INTERVIEW" # Fallback
            
        router_prompt = self.system_prompt.get("router", "")
        prompt = f"{router_prompt}\n\nUser Input: {user_message}"
        
        try:
            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt
            )
            intent = response.text.strip().upper()
            if "DRAFT" in intent: return "DRAFT"
            return "INTERVIEW"
        except Exception as e:
            print(f"Routing error: {e}")
            return "INTERVIEW"

    def route_message(self, user_message: str, user_id: str, **kwargs) -> str:
        """
        Routes the message based on intent.
        """
        intent = self._classify_intent(user_message)
        print(f"Routing Intent: {intent}")

        if intent == "DRAFT":
            # Just pass the user_message as 'grant_info' for now.
            # Ideally we extract structure, but MVP: Input is the grant info.
            return f"【Drafting Started】\n{self.drafter.create_draft(user_id, user_message)}"
        
        # Default to Interviewer
        return self.interviewer.process_message(user_message, user_id, **kwargs)

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
