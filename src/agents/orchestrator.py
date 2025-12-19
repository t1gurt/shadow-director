from typing import Dict, Any, List, Tuple
import yaml
import os
import glob
from src.agents.interviewer import InterviewerAgent
from src.agents.observer import ObserverAgent
from src.memory.profile_manager import ProfileManager

class Orchestrator:
    def __init__(self):
        self.interviewer = InterviewerAgent()
        self.observer = ObserverAgent()
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("system_prompts", {}).get("orchestrator", "")
        except Exception:
            return ""

    def route_message(self, user_message: str, user_id: str, **kwargs) -> str:
        """
        Routes the message to the appropriate agent.
        In Phase 1, it primarily routes to the Interviewer.
        """
        # Simple routing logic for Phase 1
        # In future, use LLM to decide routing based on intent (Search vs Interview vs Draft)
        
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
