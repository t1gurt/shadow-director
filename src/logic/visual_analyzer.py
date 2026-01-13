"""
Visual Analyzer - Screenshot-based visual reasoning using Gemini 3.0 multimodal.

This module provides visual reasoning fallback when DOM-based analysis is difficult.
Uses Gemini 3.0's multimodal capabilities to analyze page screenshots.
"""

import base64
import logging
import os
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path


class VisualAnalyzer:
    """
    Provides visual reasoning using Gemini 3.0 multimodal capabilities.
    Used as fallback when DOM-based analysis fails or is unreliable.
    """
    
    # Visual elements to look for
    DOWNLOAD_BUTTON_KEYWORDS = [
        'ダウンロード', 'Download', 'PDF', 'Excel', 'Word', 'ZIP',
        '様式', '申請書', 'フォーマット', '書式'
    ]
    
    ERROR_PAGE_INDICATORS = [
        '404', 'Not Found', 'エラー', 'ページが見つかりません',
        '存在しません', 'アクセスできません'
    ]
    
    def __init__(self, gemini_client=None, model_name: str = "gemini-3.0-pro"):
        """
        Initialize VisualAnalyzer.
        
        Args:
            gemini_client: Google Gemini API client
            model_name: Model to use for visual reasoning
        """
        self.client = gemini_client
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)
    
    def _encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """
        Encode an image file to base64 string.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Base64 encoded string or None if failed
        """
        try:
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            self.logger.error(f"[VISUAL_ANALYZER] Failed to encode image: {e}")
            return None
    
    def _get_mime_type(self, image_path: str) -> str:
        """Get MIME type from file extension."""
        ext = Path(image_path).suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        return mime_types.get(ext, 'image/png')
    
    async def analyze_page_screenshot(
        self, 
        screenshot_path: str,
        analysis_type: str = "general"
    ) -> Dict[str, Any]:
        """
        Analyze a page screenshot using Gemini multimodal.
        
        Args:
            screenshot_path: Path to the screenshot image
            analysis_type: Type of analysis - "general", "find_download", "verify_page"
            
        Returns:
            Analysis result with findings
        """
        if not self.client:
            self.logger.warning("[VISUAL_ANALYZER] No Gemini client available")
            return {"success": False, "reason": "Geminiクライアントが設定されていません"}
        
        if not os.path.exists(screenshot_path):
            return {"success": False, "reason": f"スクリーンショットが見つかりません: {screenshot_path}"}
        
        # Encode image to base64
        image_base64 = self._encode_image_to_base64(screenshot_path)
        if not image_base64:
            return {"success": False, "reason": "画像のエンコードに失敗しました"}
        
        # Build prompt based on analysis type
        prompt = self._build_analysis_prompt(analysis_type)
        
        try:
            from google.genai.types import GenerateContentConfig, ThinkingConfig, Part, Content
            
            # Create image part for multimodal input
            image_part = Part.from_bytes(
                data=base64.b64decode(image_base64),
                mime_type=self._get_mime_type(screenshot_path)
            )
            
            # Build content with image and text
            contents = [
                Content(parts=[image_part, Part.from_text(prompt)])
            ]
            
            # Use Thinking Mode for deep visual reasoning
            thinking_config = ThinkingConfig(thinking_level="high")
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=GenerateContentConfig(
                    temperature=0.2,
                    thinking_config=thinking_config
                )
            )
            
            result = self._parse_visual_analysis(response.text, analysis_type)
            result["success"] = True
            self.logger.info(f"[VISUAL_ANALYZER] Analysis complete: {analysis_type}")
            return result
            
        except Exception as e:
            self.logger.error(f"[VISUAL_ANALYZER] Analysis failed: {e}")
            return {"success": False, "reason": str(e)}
    
    def _build_analysis_prompt(self, analysis_type: str) -> str:
        """Build prompt for visual analysis based on type."""
        
        if analysis_type == "find_download":
            return """
この画面のスクリーンショットを分析してください。

**タスク:** ダウンロードリンク/ボタンを探す

**探すもの:**
- PDF、Excel、Word、ZIPファイルのダウンロードリンク
- 「様式」「申請書」「フォーマット」などのボタン
- ダウンロードアイコン（矢印下向き、ファイルアイコンなど）

**出力形式:**
- **発見:** [あり/なし]
- **ダウンロード要素:** [見つかった要素のテキストまたは説明]
- **位置:** [画面のどの辺りか - 例: 中央下部、右上など]
- **推奨クリック座標:** [x, y] (画像のピクセル座標、推定)
"""
        
        elif analysis_type == "verify_page":
            return """
この画面のスクリーンショットを分析してください。

**タスク:** ページの種類を判定

**判定項目:**
1. これは正常なWebページか、エラーページか?
2. 助成金/補助金の公募ページか?
3. ダウンロードページか?

**出力形式:**
- **ページ種類:** [公募ページ/ダウンロードページ/一般ページ/エラーページ/その他]
- **エラー有無:** [あり/なし]
- **助成金関連:** [はい/いいえ]
- **信頼度:** [高/中/低]
- **理由:** [判断理由を簡潔に]
"""
        
        elif analysis_type == "find_element":
            return """
この画面のスクリーンショットを分析してください。

**タスク:** クリック可能な要素を識別

**探すもの:**
- ボタン（青/緑などの目立つボタン）
- テキストリンク
- バナーやカード形式のリンク

**出力形式:**
- **クリッカブル要素数:** [数]
- **主要な要素:** [名前と位置のリスト]
"""
        
        else:  # general
            return """
この画面のスクリーンショットを分析してください。

**タスク:** ページの概要を把握

**確認項目:**
1. ページのタイトルまたは見出し
2. 主要なコンテンツの種類
3. ナビゲーション構造
4. 目立つ情報やリンク

**出力形式:**
- **ページタイトル:** [見出しまたは推測されるタイトル]
- **コンテンツ種類:** [種類の説明]
- **主要リンク:** [見つかったリンクの概要]
"""
    
    def _parse_visual_analysis(self, response_text: str, analysis_type: str) -> Dict[str, Any]:
        """Parse the visual analysis response."""
        import re
        
        result = {
            "raw_response": response_text,
            "analysis_type": analysis_type
        }
        
        # Extract structured information based on patterns
        patterns = {
            "発見": r'\*\*発見\*\*[:\s]*(.+)',
            "ダウンロード要素": r'\*\*ダウンロード要素\*\*[:\s]*(.+)',
            "位置": r'\*\*位置\*\*[:\s]*(.+)',
            "ページ種類": r'\*\*ページ種類\*\*[:\s]*(.+)',
            "エラー有無": r'\*\*エラー有無\*\*[:\s]*(.+)',
            "助成金関連": r'\*\*助成金関連\*\*[:\s]*(.+)',
            "信頼度": r'\*\*信頼度\*\*[:\s]*(.+)',
            "理由": r'\*\*理由\*\*[:\s]*(.+)',
            "ページタイトル": r'\*\*ページタイトル\*\*[:\s]*(.+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, response_text)
            if match:
                result[key] = match.group(1).strip()
        
        # Extract coordinates if present
        coord_match = re.search(r'\*\*推奨クリック座標\*\*[:\s]*\[?(\d+)[,\s]+(\d+)\]?', response_text)
        if coord_match:
            result["click_coordinates"] = {
                "x": int(coord_match.group(1)),
                "y": int(coord_match.group(2))
            }
        
        return result
    
    async def find_download_elements_visually(
        self, 
        page: Any,
        explorer: Any
    ) -> List[Dict[str, Any]]:
        """
        Find download elements using visual analysis when DOM-based search fails.
        
        Args:
            page: Playwright page object
            explorer: SiteExplorer instance for taking screenshots
            
        Returns:
            List of found download elements with coordinates
        """
        import tempfile
        
        # Take screenshot for analysis
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            screenshot_path = tmp.name
        
        try:
            await page.screenshot(path=screenshot_path, full_page=False)
            
            # Analyze screenshot
            result = await self.analyze_page_screenshot(screenshot_path, "find_download")
            
            if result.get("success") and result.get("発見") == "あり":
                elements = []
                
                if result.get("click_coordinates"):
                    elements.append({
                        "type": "visual_detection",
                        "text": result.get("ダウンロード要素", "Unknown"),
                        "position": result.get("位置", "Unknown"),
                        "coordinates": result.get("click_coordinates"),
                        "confidence": "visual"
                    })
                
                self.logger.info(f"[VISUAL_ANALYZER] Found {len(elements)} elements visually")
                return elements
            
            return []
            
        finally:
            # Cleanup
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
    
    async def verify_page_type(self, page: Any) -> Dict[str, Any]:
        """
        Verify page type using visual analysis.
        Useful when DOM-based checks are unreliable.
        
        Args:
            page: Playwright page object
            
        Returns:
            Page verification result
        """
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            screenshot_path = tmp.name
        
        try:
            await page.screenshot(path=screenshot_path, full_page=False)
            result = await self.analyze_page_screenshot(screenshot_path, "verify_page")
            return result
            
        finally:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)


# Singleton for easy access
_visual_analyzer_instance = None

def get_visual_analyzer(gemini_client=None, model_name: str = "gemini-3.0-pro") -> VisualAnalyzer:
    """Get or create VisualAnalyzer instance."""
    global _visual_analyzer_instance
    if _visual_analyzer_instance is None or gemini_client is not None:
        _visual_analyzer_instance = VisualAnalyzer(gemini_client, model_name)
    return _visual_analyzer_instance
