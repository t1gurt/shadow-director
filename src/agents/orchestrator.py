from typing import Dict, Any
import yaml
from src.agents.interviewer import InterviewerAgent
from src.memory.profile_manager import ProfileManager

class Orchestrator:
    def __init__(self):
        self.profile_manager = ProfileManager()
        self.interviewer = InterviewerAgent(self.profile_manager)
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("system_prompts", {}).get("orchestrator", "")
        except Exception:
            return ""

    def route_message(self, user_message: str, user_id: str) -> str:
        """
        Routes the message to the appropriate agent.
        In Phase 1, it primarily routes to the Interviewer.
        """
        # Simple routing logic for Phase 1
        # In future, use LLM to decide routing based on intent (Search vs Interview vs Draft)
        
        return self.interviewer.process_message(user_message)
