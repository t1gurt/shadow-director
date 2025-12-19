import json
import os
from typing import Dict, Any, Optional
# Vertex AI integration would be added here in a production environment
# from google.cloud import aiplatform

class ProfileManager:
    """
    Manages the 'Soul Profile' of the NPO representative.
    In Phase 1, this uses a local JSON file as a mock for Vertex AI Memory Bank.
    """
    
    def __init__(self, storage_path: str = "soul_profile.json"):
        self.storage_path = storage_path
        self._profile: Dict[str, Any] = self._load_profile()

    def _load_profile(self) -> Dict[str, Any]:
        """Loads the profile from disk or initializes an empty one."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def save_profile(self) -> None:
        """Saves the current profile to disk."""
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._profile, f, indent=4, ensure_ascii=False)

    def update_key_insight(self, category: str, content: str) -> None:
        """
        Updates a specific insight in the profile.
        
        Args:
            category: e.g., 'primary_experience', 'mission', 'vision'
            content: The extracted text or summary.
        """
        if "insights" not in self._profile:
            self._profile["insights"] = {}
        
        self._profile["insights"][category] = content
        self.save_profile()

    def get_profile_context(self) -> str:
        """Returns a formatted string of the current profile for LLM context."""
        if not self._profile.get("insights"):
            return "現在のプロファイル情報はありません。ゼロからインタビューを開始してください。"
            
        context = "【現在のSoul Profile】\n"
        for key, value in self._profile.get("insights", {}).items():
            context += f"- {key}: {value}\n"
        return context
