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
    
    async def find_file_links_visually(
        self,
        page: Any,
        grant_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        スクリーンショットからファイルダウンロードリンクを視覚的に探す。
        DOM分析で見つからない場合のFallback機能。
        
        Args:
            page: Playwright page object
            grant_name: 助成金名（関連性判定用、オプション）
            
        Returns:
            見つかったファイルリンクのリスト。各要素は以下の情報を含む:
            - text: リンクテキスト
            - click_coordinates: クリック座標 (x, y)
            - confidence: 信頼度 (high/medium/low)
            - file_type: 推定ファイル形式 (pdf/word/excel/unknown)
            - position: 画面内の位置説明
        """
        import tempfile
        import json
        import re
        
        if not self.client:
            self.logger.warning("[VISUAL_ANALYZER] No Gemini client available")
            return []
        
        # Take screenshot
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            screenshot_path = tmp.name
        
        try:
            await page.screenshot(path=screenshot_path, full_page=False)
            
            # Get viewport size for coordinate validation
            viewport_size = await page.evaluate('() => ({ width: window.innerWidth, height: window.innerHeight })')
            
            # Build prompt
            prompt = self._build_file_link_detection_prompt(grant_name, viewport_size)
            
            # Encode image
            image_base64 = self._encode_image_to_base64(screenshot_path)
            if not image_base64:
                return []
            
            from google.genai.types import GenerateContentConfig, Part, Content
            
            # Create image part
            image_part = Part.from_bytes(
                data=base64.b64decode(image_base64),
                mime_type=self._get_mime_type(screenshot_path)
            )
            
            contents = [
                Content(parts=[image_part, Part.from_text(prompt)])
            ]
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=GenerateContentConfig(
                    temperature=0.1
                )
            )
            
            # Parse response
            found_links = self._parse_file_links_response(response.text, viewport_size)
            
            self.logger.info(f"[VISUAL_ANALYZER] Found {len(found_links)} file links visually")
            return found_links
            
        except Exception as e:
            self.logger.error(f"[VISUAL_ANALYZER] find_file_links_visually failed: {e}")
            return []
            
        finally:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
    
    def _build_file_link_detection_prompt(
        self, 
        grant_name: str = None,
        viewport_size: Dict[str, int] = None
    ) -> str:
        """
        ファイルリンク検出用のVLMプロンプトを構築する。
        
        Args:
            grant_name: 助成金名（関連性判定用）
            viewport_size: ビューポートサイズ
            
        Returns:
            VLMプロンプト文字列
        """
        width = viewport_size.get('width', 1280) if viewport_size else 1280
        height = viewport_size.get('height', 720) if viewport_size else 720
        
        grant_context = ""
        if grant_name:
            grant_context = f"""
**対象助成金:** {grant_name}
この助成金に関連するファイル（申請書、様式、募集要項など）を優先的に探してください。
"""
        
        return f"""
この画面のスクリーンショットを詳細に分析し、ファイルダウンロードリンクを探してください。

{grant_context}

**探すべき要素:**
1. PDF/Word/Excelのアイコン付きリンク
2. 「ダウンロード」「様式」「申請書」「フォーマット」などのボタン/リンク
3. ファイル一覧テーブル内のリンク
4. アコーディオンやタブ内のリンク（開いている場合）
5. ファイル拡張子が表示されているテキストリンク

**画像サイズ:** {width} x {height} ピクセル

**出力形式（JSON形式で回答）:**
```json
{{
  "found_count": [見つかったファイルリンクの数],
  "file_links": [
    {{
      "text": "[リンクのテキスト]",
      "file_type": "[pdf/word/excel/zip/unknown]",
      "x": [クリック座標X（0-{width}）],
      "y": [クリック座標Y（0-{height}）],
      "confidence": "[high/medium/low]",
      "position": "[画面内の位置説明]",
      "reason": "[このリンクがファイルだと判断した理由]"
    }}
  ]
}}
```

**重要な注意:**
- 座標は画像の左上を原点(0,0)としたピクセル値で指定
- リンクの中心付近の座標を推定してください
- 見つからない場合は found_count: 0 で空の配列を返してください
- 必ず有効なJSON形式で回答してください
"""
    
    def _parse_file_links_response(
        self, 
        response_text: str,
        viewport_size: Dict[str, int] = None
    ) -> List[Dict[str, Any]]:
        """
        VLMレスポンスからファイルリンク情報をパースする。
        
        Args:
            response_text: VLMレスポンステキスト
            viewport_size: ビューポートサイズ（座標検証用）
            
        Returns:
            パースされたファイルリンクのリスト
        """
        import json
        import re
        
        found_links = []
        
        try:
            # JSONブロックを抽出
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                # JSONブロックがない場合、レスポンス全体をJSONとしてパース試行
                json_str = response_text.strip()
            
            data = json.loads(json_str)
            
            file_links = data.get('file_links', [])
            
            width = viewport_size.get('width', 1280) if viewport_size else 1280
            height = viewport_size.get('height', 720) if viewport_size else 720
            
            for link in file_links:
                # 座標の検証
                x = link.get('x', 0)
                y = link.get('y', 0)
                
                # 範囲外の座標を補正
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    x = max(0, min(int(x), width))
                    y = max(0, min(int(y), height))
                else:
                    continue  # 無効な座標はスキップ
                
                found_links.append({
                    'text': link.get('text', 'Unknown'),
                    'file_type': link.get('file_type', 'unknown'),
                    'click_coordinates': {'x': x, 'y': y},
                    'confidence': link.get('confidence', 'low'),
                    'position': link.get('position', ''),
                    'reason': link.get('reason', ''),
                    'source': 'visual_analysis'
                })
                
        except json.JSONDecodeError as e:
            self.logger.warning(f"[VISUAL_ANALYZER] Failed to parse JSON response: {e}")
            # フォールバック: テキストから手動でパース
            found_links = self._fallback_parse_file_links(response_text)
        except Exception as e:
            self.logger.error(f"[VISUAL_ANALYZER] Error parsing file links: {e}")
        
        return found_links
    
    def _fallback_parse_file_links(self, response_text: str) -> List[Dict[str, Any]]:
        """
        JSONパースに失敗した場合のフォールバックパーサー。
        テキストから手動でファイルリンク情報を抽出する。
        """
        import re
        
        found_links = []
        
        # パターンマッチで情報を抽出
        # "text": "xxx" パターン
        text_matches = re.findall(r'"text"\s*:\s*"([^"]+)"', response_text)
        coord_matches = re.findall(r'"x"\s*:\s*(\d+)[,\s]+"y"\s*:\s*(\d+)', response_text)
        type_matches = re.findall(r'"file_type"\s*:\s*"([^"]+)"', response_text)
        
        # マッチした情報を組み合わせ
        for i, text in enumerate(text_matches):
            link = {
                'text': text,
                'file_type': type_matches[i] if i < len(type_matches) else 'unknown',
                'source': 'visual_analysis_fallback'
            }
            
            if i < len(coord_matches):
                x, y = coord_matches[i]
                link['click_coordinates'] = {'x': int(x), 'y': int(y)}
            
            found_links.append(link)
        
        return found_links


# Singleton for easy access
_visual_analyzer_instance = None

def get_visual_analyzer(gemini_client=None, model_name: str = "gemini-3.0-pro") -> VisualAnalyzer:
    """Get or create VisualAnalyzer instance."""
    global _visual_analyzer_instance
    if _visual_analyzer_instance is None or gemini_client is not None:
        _visual_analyzer_instance = VisualAnalyzer(gemini_client, model_name)
    return _visual_analyzer_instance
