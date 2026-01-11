import json
import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

try:
    from google.cloud import storage
except ImportError:
    storage = None

try:
    from src.memory.memory_bank_storage import MemoryBankStorage, MEMORY_BANK_AVAILABLE
except ImportError:
    MemoryBankStorage = None
    MEMORY_BANK_AVAILABLE = False

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
    Selects storage backend based on APP_ENV and USE_MEMORY_BANK.
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.env = os.getenv("APP_ENV", "local")
        use_memory_bank = os.getenv("USE_MEMORY_BANK", "false").lower() == "true"
        
        if self.env == "production":
            # Check if Memory Bank should be used
            if use_memory_bank and MEMORY_BANK_AVAILABLE and MemoryBankStorage:
                try:
                    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
                    location = os.getenv("MEMORY_BANK_LOCATION", "us-central1")
                    self.storage = MemoryBankStorage(project_id=project_id, location=location)
                    logging.info(f"[PROFILE] Using Memory Bank storage for {user_id}")
                except Exception as e:
                    logging.error(f"[PROFILE] Failed to initialize Memory Bank, falling back to GCS: {e}")
                    self._init_gcs_storage()
            else:
                self._init_gcs_storage()
        else:
            self.storage = LocalProfileStorage()
            
        self._profile: Dict[str, Any] = self.storage.load(self.user_id)
    
    def _init_gcs_storage(self):
        """Initialize GCS storage backend."""
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        if not bucket_name:
            logging.warning("GCS_BUCKET_NAME not set in production. Falling back to local.")
            self.storage = LocalProfileStorage()
        else:
            self.storage = GCSProfileStorage(bucket_name)

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
        
        insights = self._profile.get("insights", {})
        
        # Category labels in Japanese
        # Category labels in Japanese
        category_labels = {
            # Core Identity & Origin
            "primary_experience": "🌱 原体験",
            "origin_story": "📖 創設ストーリー",
            "mission": "🎯 ミッション",
            "vision": "🌟 ビジョン",
            "values": "💎 価値観",
            
            # Organization Details - Individual Fields
            "org_name": "🏢 団体名",
            "representative_name": "👤 代表者名",
            "phone_number": "📞 連絡先電話番号",
            "website_url": "🌐 ホームページ",
            "email_address": "📧 メールアドレス",
            "founding_year": "📅 設立年",
            "annual_budget": "💰 年間予算",
            
            # Legacy organization info (for backward compatibility)
            "organization_info": "🏢 団体基本情報",
            "contact_info": "📞 連絡先情報",
            "staff_info": "👥 スタッフ構成",
            "finance_info": "💰 財務状況",
            
            # Project Concept
            "project_name": "🚀 プロジェクト名",
            "project_plan": "📝 プロジェクト計画",
            "activity_plan": "📅 活動スケジュール",
            "budget_plan": "💸 予算計画",
            
            # Existing specific fields
            "activities": "📋 活動内容",
            "target_beneficiaries": "👥 支援対象",
            "achievements": "🏆 成果・実績",
            "strengths": "💪 強み",
            "partnerships": "🤝 連携先",
            "challenges": "⚠️ 課題",
            "keywords": "🏷️ キーワード"
        }
        
        # Section groupings
        sections = {
            "団体詳細情報": ["org_name", "representative_name", "phone_number", "website_url", "email_address", "founding_year", "annual_budget", "organization_info", "contact_info", "staff_info", "finance_info"],
            "コア・アイデンティティ": ["primary_experience", "origin_story", "mission", "vision", "values"],
            "活動・組織力": ["activities", "target_beneficiaries", "achievements", "strengths", "partnerships", "challenges"],
            "プロジェクト構想": ["project_name", "project_plan", "activity_plan", "budget_plan"],
            "マッチング": ["keywords"]
        }
        
        context = "【Soul Profile】\n\n"
        
        for section_name, categories in sections.items():
            section_content = []
            for cat in categories:
                if cat in insights and insights[cat]:
                    label = category_labels.get(cat, cat)
                    section_content.append(f"**{label}**\n{insights[cat]}")
            
            if section_content:
                context += f"## {section_name}\n\n"
                context += "\n\n".join(section_content)
                context += "\n\n"
        
        # Add any unlabeled insights
        for key, value in insights.items():
            if key not in category_labels and value:
                context += f"- {key}: {value}\n"
        
        return context.strip()

    
    def get_conversation_history(self) -> list:
        """Returns the conversation history as a list of {role, content} dicts."""
        return self._profile.get("conversation_history", [])
    
    def add_to_history(self, role: str, content: str) -> None:
        """Adds a message to the conversation history.
        
        Args:
            role: Either 'user' or 'agent'
            content: The message content
        """
        if "conversation_history" not in self._profile:
            self._profile["conversation_history"] = []
        
        self._profile["conversation_history"].append({
            "role": role,
            "content": content
        })
        self.save_profile()
    
    def get_turn_count(self) -> int:
        """Returns the current turn number (number of user messages)."""
        history = self.get_conversation_history()
        # Count only user turns
        return sum(1 for turn in history if turn.get("role") == "user")
    
    def clear_history(self) -> None:
        """Clears the conversation history (for testing or reset)."""
        self._profile["conversation_history"] = []
        self.save_profile()

    # ==================== PR/SNS情報管理 ====================

    def update_sns_info(self, platform: str, url: str) -> None:
        """
        Updates SNS monitoring information for the profile.
        
        Args:
            platform: sns platform (e.g., 'facebook', 'instagram', 'twitter', 'website')
            url: The URL to watch
        """
        if "sns_watch_info" not in self._profile:
            self._profile["sns_watch_info"] = {}
        
        # Normalize key
        platform_key = platform.lower().strip()
        self._profile["sns_watch_info"][platform_key] = url
        self.save_profile()
        logging.info(f"[PROFILE] Updated SNS info for {platform_key}: {url}")

    def get_sns_info(self) -> Dict[str, str]:
        """
        Returns all stored SNS watch information.
        """
        return self._profile.get("sns_watch_info", {})

    def add_monthly_summary(self, summary_text: str) -> None:
        """
        Saves a generated monthly summary to the profile history.
        """
        from datetime import datetime
        if "monthly_summaries" not in self._profile:
            self._profile["monthly_summaries"] = []
            
        record = {
            "date": datetime.now().isoformat(),
            "summary": summary_text
        }
        self._profile["monthly_summaries"].append(record)
        self.save_profile()

    # ==================== 助成金履歴管理 ====================
    
    def get_shown_grants(self) -> List[Dict[str, Any]]:
        """
        Returns the list of grants that have already been shown to the user.
        
        Returns:
            List of grant dictionaries with title, url, date_shown, etc.
        """
        return self._profile.get("shown_grants", [])
    
    def add_shown_grant(self, grant: Dict[str, Any]) -> None:
        """
        Adds a grant to the shown grants history.
        
        Args:
            grant: Dictionary containing grant info (title, url, amount, etc.)
        """
        from datetime import datetime
        
        if "shown_grants" not in self._profile:
            self._profile["shown_grants"] = []
        
        # Add timestamp
        grant_record = {
            "title": grant.get("title", ""),
            "url": grant.get("url", ""),
            "amount": grant.get("amount", ""),
            "resonance_score": grant.get("resonance_score", 0),
            "date_shown": datetime.now().isoformat()
        }
        
        # Check for duplicates by URL or title
        existing_urls = [g.get("url", "") for g in self._profile["shown_grants"]]
        existing_titles = [g.get("title", "").lower() for g in self._profile["shown_grants"]]
        
        if grant_record["url"] not in existing_urls and grant_record["title"].lower() not in existing_titles:
            self._profile["shown_grants"].append(grant_record)
            self.save_profile()
    
    def is_grant_shown(self, grant: Dict[str, Any]) -> bool:
        """
        Checks if a grant has already been shown to the user.
        
        Args:
            grant: Dictionary containing grant info
        
        Returns:
            True if the grant has already been shown
        """
        shown_grants = self.get_shown_grants()
        
        grant_url = grant.get("url", "")
        grant_title = grant.get("title", "").lower()
        
        for shown in shown_grants:
            # Check by URL
            if grant_url and shown.get("url", "") == grant_url:
                return True
            # Check by title (fuzzy match)
            if grant_title and shown.get("title", "").lower() == grant_title:
                return True
        
        return False
    
    def get_shown_grants_summary(self) -> str:
        """
        Returns a formatted summary of all shown grants.
        
        Returns:
            Formatted string for display
        """
        shown_grants = self.get_shown_grants()
        
        if not shown_grants:
            return "まだ提案済みの助成金はありません。"
        
        summary = f"📋 **提案済み助成金一覧** ({len(shown_grants)}件)\n\n"
        
        for i, grant in enumerate(shown_grants, 1):
            title = grant.get("title", "タイトル不明")
            url = grant.get("url", "")
            amount = grant.get("amount", "金額不明")
            score = grant.get("resonance_score", "")
            date_shown = grant.get("date_shown", "")[:10]  # YYYY-MM-DD
            
            summary += f"**{i}. {title}**\n"
            if url:
                summary += f"   🔗 URL: {url}\n"
            summary += f"   💰 金額: {amount}\n"
            if score:
                summary += f"   🎯 共鳴度: {score}/100\n"
            summary += f"   📅 提案日: {date_shown}\n\n"
        
        return summary
    
    def clear_shown_grants(self) -> None:
        """Clears the shown grants history."""
        self._profile["shown_grants"] = []
        self.save_profile()

    # ==================== NPO共鳴マッチング ====================
    
    def list_all_profiles(self) -> List[Dict[str, Any]]:
        """
        Lists all profiles in GCS storage.
        
        Returns:
            List of (user_id, profile_data) tuples
        """
        profiles = []
        
        if not isinstance(self.storage, GCSProfileStorage):
            logging.warning("[PROFILE] Resonance matching requires GCS storage")
            return profiles
        
        try:
            # List all blobs in profiles/ prefix
            blobs = self.storage.bucket.list_blobs(prefix="profiles/")
            
            for blob in blobs:
                if blob.name.endswith("soul_profile.json"):
                    # Extract user_id from path: profiles/{user_id}/soul_profile.json
                    parts = blob.name.split("/")
                    if len(parts) >= 2:
                        user_id = parts[1]
                        if user_id != self.user_id:  # Exclude self
                            try:
                                content = blob.download_as_text()
                                profile_data = json.loads(content)
                                profiles.append({
                                    "user_id": user_id,
                                    "profile": profile_data
                                })
                            except Exception as e:
                                logging.error(f"[PROFILE] Error loading profile {user_id}: {e}")
        except Exception as e:
            logging.error(f"[PROFILE] Error listing profiles: {e}")
        
        return profiles
    
    def calculate_resonance(self, other_profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates resonance score between this profile and another.
        
        Args:
            other_profile: The other NPO's profile data
            
        Returns:
            Dict with resonance score and breakdown
        """
        my_insights = self._profile.get("insights", {})
        other_insights = other_profile.get("insights", {})
        
        if not my_insights or not other_insights:
            return {"score": 0, "reason": "プロファイル情報が不足しています"}
        
        # Calculate keyword overlap
        my_keywords = set(
            k.strip().lower() 
            for k in my_insights.get("keywords", "").split(",") 
            if k.strip()
        )
        other_keywords = set(
            k.strip().lower() 
            for k in other_insights.get("keywords", "").split(",") 
            if k.strip()
        )
        
        keyword_overlap = len(my_keywords & other_keywords)
        keyword_score = min(keyword_overlap * 15, 40)  # Max 40 points
        
        # Check mission alignment
        my_mission = my_insights.get("mission", "").lower()
        other_mission = other_insights.get("mission", "").lower()
        
        mission_score = 0
        if my_mission and other_mission:
            # Simple word overlap check
            my_words = set(my_mission.split())
            other_words = set(other_mission.split())
            common_words = len(my_words & other_words)
            if common_words >= 3:
                mission_score = 30
            elif common_words >= 1:
                mission_score = 15
        
        # Check target beneficiaries alignment
        my_target = my_insights.get("target_beneficiaries", "").lower()
        other_target = other_insights.get("target_beneficiaries", "").lower()
        
        target_score = 0
        if my_target and other_target:
            my_words = set(my_target.split())
            other_words = set(other_target.split())
            if len(my_words & other_words) >= 2:
                target_score = 20
            elif len(my_words & other_words) >= 1:
                target_score = 10
        
        # Check strengths complementarity
        strengths_score = 10 if other_insights.get("strengths") else 0
        
        total_score = keyword_score + mission_score + target_score + strengths_score
        
        # Build reason
        reasons = []
        if keyword_overlap > 0:
            common = my_keywords & other_keywords
            reasons.append(f"共通キーワード: {', '.join(list(common)[:3])}")
        if mission_score > 0:
            reasons.append("ミッションに共通点あり")
        if target_score > 0:
            reasons.append("支援対象が類似")
        
        return {
            "score": min(total_score, 100),
            "keyword_score": keyword_score,
            "mission_score": mission_score,
            "target_score": target_score,
            "reason": ", ".join(reasons) if reasons else "共通点なし"
        }
    
    def find_resonating_npos(self, min_score: int = 30) -> str:
        """
        Finds NPOs with resonating Soul Profiles.
        
        Args:
            min_score: Minimum resonance score to include (default 30)
            
        Returns:
            Formatted string with resonating NPOs
        """
        all_profiles = self.list_all_profiles()
        
        if not all_profiles:
            return "⚠️ 他のNPOプロファイルが見つかりませんでした。\n\n同じチャンネル内で他のNPOがプロファイルを作成すると、共鳴するNPOを探すことができます。"
        
        # Calculate resonance for each
        resonance_results = []
        for profile_info in all_profiles:
            other_profile = profile_info["profile"]
            resonance = self.calculate_resonance(other_profile)
            
            if resonance["score"] >= min_score:
                resonance_results.append({
                    "user_id": profile_info["user_id"],
                    "profile": other_profile,
                    "resonance": resonance
                })
        
        # Sort by score descending
        resonance_results.sort(key=lambda x: x["resonance"]["score"], reverse=True)
        
        if not resonance_results:
            return f"⚠️ 共鳴度{min_score}以上のNPOは見つかりませんでした。\n\n{len(all_profiles)}件のプロファイルを検索しましたが、あなたのNPOと十分な共通点を持つ団体は見つかりませんでした。"
        
        # Build result
        result = f"# 🤝 共鳴するNPO ({len(resonance_results)}件)\n\n"
        
        for i, item in enumerate(resonance_results[:5], 1):  # Top 5
            other_insights = item["profile"].get("insights", {})
            resonance = item["resonance"]
            
            # Get NPO info
            mission = other_insights.get("mission", "ミッション未設定")
            activities = other_insights.get("activities", "")
            
            result += f"## {i}. 共鳴度: {resonance['score']}/100\n\n"
            result += f"**🎯 ミッション**: {mission[:100]}{'...' if len(mission) > 100 else ''}\n\n"
            if activities:
                result += f"**📋 活動内容**: {activities[:100]}{'...' if len(activities) > 100 else ''}\n\n"
            result += f"**💫 共鳴理由**: {resonance['reason']}\n\n"
            result += "---\n\n"
        
        result += "*共鳴度は、キーワード・ミッション・支援対象の類似性から算出しています。*"
        
        return result
