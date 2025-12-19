import json
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

try:
    from google.cloud import storage
except ImportError:
    storage = None

class ProfileStorageBackend(ABC):
    """Abstract base class for profile storage strategies."""
    
    @abstractmethod
    def load(self, user_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def save(self, user_id: str, data: Dict[str, Any]) -> None:
        pass

class LocalProfileStorage(ProfileStorageBackend):
    """Stores profiles in local JSON files."""
    
    def __init__(self, base_dir: str = "profiles"):
        self.base_dir = base_dir
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)

    def _get_path(self, user_id: str) -> str:
        # Create a directory per user to keep things organized, or just a file
        return os.path.join(self.base_dir, f"{user_id}_profile.json")

    def load(self, user_id: str) -> Dict[str, Any]:
        path = self._get_path(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def save(self, user_id: str, data: Dict[str, Any]) -> None:
        path = self._get_path(user_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

class GCSProfileStorage(ProfileStorageBackend):
    """Stores profiles in Google Cloud Storage."""

    def __init__(self, bucket_name: str):
        if not storage:
            raise ImportError("google-cloud-storage is required for GCSProfileStorage")
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def _get_blob_name(self, user_id: str) -> str:
        return f"profiles/{user_id}/soul_profile.json"

    def load(self, user_id: str) -> Dict[str, Any]:
        blob = self.bucket.blob(self._get_blob_name(user_id))
        if blob.exists():
            try:
                content = blob.download_as_text()
                return json.loads(content)
            except Exception as e:
                print(f"Error loading from GCS: {e}")
                return {}
        return {}

    def save(self, user_id: str, data: Dict[str, Any]) -> None:
        blob = self.bucket.blob(self._get_blob_name(user_id))
        try:
            blob.upload_from_string(
                json.dumps(data, indent=4, ensure_ascii=False),
                content_type="application/json"
            )
        except Exception as e:
            print(f"Error saving to GCS: {e}")

class ProfileManager:
    """
    Manages the 'Soul Profile' of the NPO representative.
    Selects storage backend based on APP_ENV.
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.env = os.getenv("APP_ENV", "local")
        
        if self.env == "production":
            bucket_name = os.getenv("GCS_BUCKET_NAME")
            if not bucket_name:
                # Fallback to local if config is missing, or raise error
                print("Warning: GCS_BUCKET_NAME not set in production. Falling back to local.")
                self.storage = LocalProfileStorage()
            else:
                self.storage = GCSProfileStorage(bucket_name)
        else:
            self.storage = LocalProfileStorage()
            
        self._profile: Dict[str, Any] = self.storage.load(self.user_id)

    def save_profile(self) -> None:
        """Saves the current profile to storage."""
        self.storage.save(self.user_id, self._profile)

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
