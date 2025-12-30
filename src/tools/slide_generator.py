"""
Slide Generator Tool using Gemini 3 Pro Image (Nano Banana Pro)
Generates visual slide images for grant summaries and drafts.
"""

import os
import yaml
import logging
from google import genai
from google.genai import types
from google.cloud import storage
from datetime import datetime
from typing import Dict, Any, Tuple, Optional


class SlideGenerator:
    """Generates visual slide images using Gemini 3 Pro Image."""
    
    def __init__(self):
        """Initialize the slide generator with config from prompts.yaml."""
        self.config = self._load_config()
        self._init_client()
        self._init_storage()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from prompts.yaml."""
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logging.error(f"[SLIDE_GEN] Failed to load config: {e}")
            return {}
    
    def _init_client(self):
        """Initialize Gemini client with Vertex AI."""
        model_config = self.config.get("model_config", {})
        project_id = model_config.get("project_id", "zenn-shadow-director")
        location = model_config.get("location", "us-central1")
        
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        
        try:
            self.client = genai.Client()
            logging.info("[SLIDE_GEN] Initialized with Vertex AI")
        except Exception as e:
            logging.error(f"[SLIDE_GEN] Failed to initialize client: {e}")
            self.client = None
        
        # Get model from config
        self.model = model_config.get("slide_generator_model", "gemini-3-pro-image-preview")
        logging.info(f"[SLIDE_GEN] Using model: {self.model}")
    
    def _init_storage(self):
        """Initialize GCS storage client."""
        self.bucket_name = os.environ.get("GCS_BUCKET_NAME", "zenn-shadow-director-data")
        
        try:
            self.storage_client = storage.Client()
            self.bucket = self.storage_client.bucket(self.bucket_name)
            logging.info(f"[SLIDE_GEN] GCS bucket initialized: {self.bucket_name}")
        except Exception as e:
            logging.error(f"[SLIDE_GEN] Failed to initialize GCS: {e}")
            self.storage_client = None
            self.bucket = None
    
    def _get_prompt_template(self, prompt_type: str) -> str:
        """Get prompt template from config."""
        prompts = self.config.get("system_prompts", {})
        return prompts.get(prompt_type, "")
    
    def generate_grant_slide(self, grant_info: dict) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generate a visual slide image for a grant opportunity.
        
        Args:
            grant_info: Dictionary containing grant details (title, amount, deadline, etc.)
        
        Returns:
            Tuple of (image_bytes, filename)
        """
        if not self.client:
            logging.error("[SLIDE_GEN] Client not initialized")
            return None, None
        
        title = grant_info.get("title", "助成金情報")
        amount = grant_info.get("amount", "金額未定")
        deadline = grant_info.get("deadline", "締切未定")
        resonance_score = grant_info.get("resonance_score", "")
        reason = grant_info.get("reason", "")
        
        # Get prompt template from config
        prompt_template = self._get_prompt_template("slide_grant")
        
        # Format resonance info
        resonance_info = f"• 共鳴度スコア: {resonance_score}/100" if resonance_score else ""
        
        # Format summary
        summary = reason[:200] if reason else "助成金の概要"
        
        # Build prompt from template
        prompt = prompt_template.format(
            title=title,
            amount=amount,
            deadline=deadline,
            resonance_info=resonance_info,
            summary=summary
        )
        
        return self._generate_image(prompt, f"slide_{title}")
    
    def generate_draft_slide(self, draft_content: str, title: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generate a visual slide image summarizing a grant draft.
        
        Args:
            draft_content: The full draft content
            title: Title of the draft
        
        Returns:
            Tuple of (image_bytes, filename)
        """
        if not self.client:
            logging.error("[SLIDE_GEN] Client not initialized")
            return None, None
        
        # Extract summary from draft (first 500 chars)
        summary = draft_content[:500].replace("\n", " ").strip()
        
        # Get prompt template from config
        prompt_template = self._get_prompt_template("slide_draft")
        
        # Build prompt from template
        prompt = prompt_template.format(
            title=title,
            summary=summary
        )
        
        return self._generate_image(prompt, f"draft_slide_{title}")
    
    def _generate_image(self, prompt: str, filename_prefix: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generate an image using Gemini 3 Pro Image with reference image.
        
        Args:
            prompt: The prompt for image generation
            filename_prefix: Prefix for the generated filename
        
        Returns:
            Tuple of (image_bytes, filename)
        """
        try:
            logging.info(f"[SLIDE_GEN] Generating image: {filename_prefix}")
            
            # Load reference image for consistent design
            reference_image_path = "assets/slide_template.png"
            contents = []
            
            try:
                with open(reference_image_path, "rb") as f:
                    reference_bytes = f.read()
                    contents.append(types.Part.from_bytes(
                        data=reference_bytes,
                        mime_type="image/png"
                    ))
                    logging.info(f"[SLIDE_GEN] Reference image loaded: {len(reference_bytes)} bytes")
            except FileNotFoundError:
                logging.warning(f"[SLIDE_GEN] Reference image not found: {reference_image_path}")
            except Exception as e:
                logging.warning(f"[SLIDE_GEN] Failed to load reference image: {e}")
            
            # Add prompt with reference instruction
            reference_instruction = """
上記の参照画像と同じレイアウト・デザインで新しいスライドを作成してください。
以下の仕様を厳密に守ること：

【レイアウト構造】
- 左上: "Shadow Director" ヘッダー
- 中央上部: 大きなタイトル（太字）
- 下部左: "主要情報" カード（角丸、アイコン付きの箇条書き）
- 下部右: "概要" カード（角丸、本文テキスト）
- 右下: "NPO-SoulSync AI" フッター

【カラーパレット】
- 背景: 薄いブルーグレーのグラデーション
- タイトル: 濃紺 (#1A365D)
- 見出し: オレンジ (#ED8936)
- 本文: ダークグレー
- アイコン: ティール/グリーン系

"""
            contents.append(reference_instruction + prompt)
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=['Image'],
                    image_config=types.ImageConfig(
                        aspect_ratio="16:9",
                    )
                )
            )
            
            # Extract image from response
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    image_bytes = part.inline_data.data
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_prefix = "".join(
                        c for c in filename_prefix[:30] 
                        if c.isalnum() or c in " _-"
                    ).strip()
                    filename = f"{safe_prefix}_{timestamp}.png"
                    
                    logging.info(f"[SLIDE_GEN] Image generated: {len(image_bytes)} bytes")
                    return image_bytes, filename
            
            logging.error("[SLIDE_GEN] No image in response")
            return None, None
            
        except Exception as e:
            logging.error(f"[SLIDE_GEN] Error generating image: {e}", exc_info=True)
            return None, None
    
    def save_to_gcs(self, image_bytes: bytes, user_id: str, filename: str) -> Optional[str]:
        """
        Save image to Google Cloud Storage.
        
        Args:
            image_bytes: The image data
            user_id: User identifier for organizing files
            filename: Name of the file
        
        Returns:
            GCS path of the saved file, or None if failed
        """
        if not self.bucket or not image_bytes:
            logging.error("[SLIDE_GEN] Cannot save to GCS: bucket or image not available")
            return None
        
        try:
            blob_path = f"slides/{user_id}/{filename}"
            blob = self.bucket.blob(blob_path)
            blob.upload_from_string(image_bytes, content_type="image/png")
            
            gcs_path = f"gs://{self.bucket_name}/{blob_path}"
            logging.info(f"[SLIDE_GEN] Saved to GCS: {gcs_path}")
            return gcs_path
            
        except Exception as e:
            logging.error(f"[SLIDE_GEN] Error saving to GCS: {e}", exc_info=True)
            return None
    
    def get_slide(self, user_id: str, filename: str) -> Optional[bytes]:
        """
        Retrieve a slide image from GCS.
        
        Args:
            user_id: User identifier
            filename: Name of the file
        
        Returns:
            Image bytes, or None if not found
        """
        if not self.bucket:
            return None
        
        try:
            blob_path = f"slides/{user_id}/{filename}"
            blob = self.bucket.blob(blob_path)
            
            if blob.exists():
                return blob.download_as_bytes()
            return None
            
        except Exception as e:
            logging.error(f"[SLIDE_GEN] Error retrieving slide: {e}")
            return None
