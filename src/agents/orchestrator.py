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
            if "DRAFT" in intent: return "DRAFT"
            if "OBSERVE" in intent: return "OBSERVE"
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
        """
        from datetime import datetime, timedelta
        
        observer_results = self.observer.observe(user_id)
        
        # Calculate next scheduled run (weekly)
        next_run = datetime.now() + timedelta(days=7)
        next_run_str = next_run.strftime("%Y年%m月%d日")
        
        footer = f"\n\n💡 **次回の自動観察予定**: {next_run_str}\n（手動で観察を実行したい場合は「助成金を探して」と送信してください）"
        
        return observer_results + footer

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
