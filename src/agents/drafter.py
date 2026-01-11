from typing import Dict, Any, Optional, Tuple, List
import yaml
import os
import asyncio
import logging
from src.tools.gdocs_tool import GoogleDocsTool
from src.memory.profile_manager import ProfileManager
from src.tools.file_downloader import FileDownloader
from src.logic.grant_page_scraper import GrantPageScraper
from src.logic.format_field_mapper import FormatFieldMapper
from src.tools.document_filler import DocumentFiller
from src.logic.file_classifier import FileClassifier

class DrafterAgent:
    def __init__(self):
        self.config = self._load_config()
        self.system_prompt = self.config.get("system_prompts", {}).get("drafter", "")
        
        # Initialize Gemini client via Vertex AI backend
        try:
            from src.utils.gemini_client import get_gemini_client
            self.client = get_gemini_client()
            logging.info("[DRAFTER] Gemini client initialized via Vertex AI")
        except Exception as e:
            logging.error(f"[DRAFTER] Failed to init Gemini client: {e}")
            self.client = None
            
        # Using Interviewer model (Pro) for drafting as it requires high reasoning/writing capability
        self.model_name = self.config.get("model_config", {}).get("interviewer_model")
        if not self.model_name:
             raise ValueError("interviewer_model (for drafter) not found in config")
        self.docs_tool = GoogleDocsTool()
        self.file_downloader = FileDownloader()
        
        # Initialize page scraper with Gemini client for visual fallback
        # Use shorter timeout (10s) for drafter operations to avoid long hangs
        self.page_scraper = GrantPageScraper(
            gemini_client=self.client, 
            model_name=self.model_name,
            timeout=10000  # 10 seconds timeout for Playwright operations
        )
        
        # Initialize format field mapper and document filler
        self.format_mapper = FormatFieldMapper(
            gemini_client=self.client,
            model_name=self.model_name
        )
        self.document_filler = DocumentFiller()
        
        # Initialize file classifier for early filtering
        vlm_model = self.config.get("model_config", {}).get("vlm_model", "gemini-3-flash-preview")
        self.file_classifier = FileClassifier(self.client, vlm_model)

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def _sanitize_grant_name_for_search(self, grant_name: str) -> str:
        """
        検索クエリで使用するためにgrant_nameをサニタイズする。
        ユーザーのコマンド（「ドラフトを作成して」等）を除去。
        
        Args:
            grant_name: サニタイズ対象の助成金名
            
        Returns:
            サニタイズ済みの助成金名
        """
        import re
        
        if not grant_name:
            return ""
        
        # 除去すべきフレーズ（コマンド系）
        remove_phrases = [
            r'のドラフトを作成して',
            r'ドラフトを作成して',
            r'のドラフト作成',
            r'ドラフト作成',
            r'の申請書を書いて',
            r'申請書を書いて',
            r'を書いて',
            r'について調べて',
            r'について詳しく',
            r'を調べて',
            r'の詳細',
        ]
        
        sanitized = grant_name
        for phrase in remove_phrases:
            sanitized = re.sub(phrase, '', sanitized)
        
        # 前後の空白を除去
        sanitized = sanitized.strip()
        
        # 括弧内の年度情報は保持（例：「2025年度後期」）
        # ただし、空になった場合は元の名前を返す
        if not sanitized:
            # 最低限のサニタイズ：明らかなコマンド部分のみ除去
            sanitized = grant_name.replace('のドラフトを作成して', '').replace('ドラフトを作成して', '').strip()
        
        return sanitized

    def _research_grant_format(self, grant_name: str, user_id: str, grant_url: str = None) -> Tuple[str, List[Tuple[str, str]]]:
        """
        Researches the grant application format using Google Search Grounding.
        Also attempts to find and download application format files.
        
        Args:
            grant_name: Name of the grant to research
            user_id: User ID for file organization
            grant_url: Optional URL of the grant page (from Observer)
            
        Returns:
            Tuple of (format_info, downloaded_files)
            - format_info: Application format information text
            - downloaded_files: List of (file_path, filename) tuples
        """
        import logging
        from google.genai.types import GenerateContentConfig, Tool, GoogleSearch
        
        logging.info(f"[DRAFTER] Researching format for: {grant_name}, URL: {grant_url}")
        
        # If we have a URL from Observer, try Playwright scraping first
        if grant_url and grant_url != 'N/A':
            try:
                logging.info(f"[DRAFTER] Using provided URL for direct scraping: {grant_url}")
                playwright_files = self._scrape_url_for_files(grant_url, user_id)
                if playwright_files:
                    logging.info(f"[DRAFTER] Found {len(playwright_files)} files from provided URL")
                    format_info = f"""
## 申請フォーマット情報

公式ページ ({grant_url}) から以下のフォーマットファイルを検出しました。

詳細な申請方法は添付のファイルをご確認ください。
"""
                    return (format_info, playwright_files)
            except Exception as e:
                logging.warning(f"[DRAFTER] Direct URL scraping failed: {e}")
        
        research_prompt = f"""
以下の助成金の申請書フォーマット（質問項目・記入欄）を調査してください。

助成金名: {grant_name}

調査すべき内容:
1. 申請書の質問項目（例：団体概要、事業計画、予算など）
2. 各項目の文字数制限や記入例
3. 審査のポイント・評価基準
4. 必要な添付書類
5. **重要**: 申請書のフォーマットファイル（PDF、Word、Excelなど）のダウンロードURLがあれば特定してください

出力形式:
## 申請書フォーマット

### 質問項目
1. [項目名] （文字数制限があれば記載）
2. [項目名] （文字数制限があれば記載）
...

### 審査ポイント
- [ポイント1]
- [ポイント2]

### 必要書類
- [書類1]
- [書類2]

### 申請フォーマットファイル
- URL: [ダウンロードURL]（見つかった場合のみ記載）
- ファイル形式: [PDF/Word/Excel等]

※見つからない場合は一般的な助成金申請書の形式を想定してください。
"""
        
        try:
            # Use Google Search Grounding for format research
            google_search_tool = Tool(google_search=GoogleSearch())
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=research_prompt,
                config=GenerateContentConfig(
                    tools=[google_search_tool],
                    temperature=0.3
                )
            )
            
            
            format_info = response.text
            logging.info(f"[DRAFTER] Format research completed, length: {len(format_info)} chars")
            
            # 1. Extract file URLs from the text response
            import re
            url_pattern = r'https?://[^\s<>"\)]+\.(?:pdf|doc|docx|xls|xlsx|zip)'
            found_urls = set(re.findall(url_pattern, format_info, re.IGNORECASE))
            
            # 2. Extract page URLs from Grounding Metadata and deep search
            # Only explore URLs that appear to be related to the target grant
            try:
                if response.candidates and response.candidates[0].grounding_metadata:
                    metadata = response.candidates[0].grounding_metadata
                    if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                        # Extract keywords from grant name for URL validation
                        grant_keywords = self._extract_grant_keywords_for_validation(grant_name)
                        logging.info(f"[DRAFTER] Grant keywords for URL validation: {grant_keywords}")
                        
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and chunk.web and chunk.web.uri:
                                page_url = chunk.web.uri
                                
                                # Resolve redirect if needed (simple version)
                                if 'grounding-api-redirect' in page_url:
                                    try:
                                        import requests
                                        res = requests.head(page_url, allow_redirects=True, timeout=5)
                                        page_url = res.url
                                    except:
                                        pass
                                
                                # Validate URL relevance before exploring
                                if not self._is_url_relevant_to_grant(page_url, grant_keywords):
                                    logging.info(f"[DRAFTER] Skipping unrelated URL: {page_url}")
                                    continue
                                
                                logging.info(f"[DRAFTER] Deep searching relevant page for files: {page_url}")
                                page_files = self.file_downloader.find_files_in_page(page_url)
                                found_urls.update(page_files)
            except Exception as e:
                logging.error(f"[DRAFTER] Error in deep search: {e}")
            
            downloaded_files = []
            failed_urls = []
            
            if found_urls:
                # Convert set back to list and sort to prioritize generic names? No, just list.
                url_list = list(found_urls)
                logging.info(f"[DRAFTER] Found {len(url_list)} potential format file URLs")
                
                # Filter out likely irrelevant files (images, common assets) if extension check failed
                # But regex ensures extension is valid.
                
                for url in url_list[:5]:  # Limit to first 5 URLs (increased from 3)
                    logging.info(f"[DRAFTER] Attempting to download: {url}")
                    result = self.file_downloader.download_file(url, user_id)
                    if result:
                        downloaded_files.append(result)
                        logging.info(f"[DRAFTER] Successfully downloaded: {result[1]}")
                    else:
                        failed_urls.append(url)
                        logging.warning(f"[DRAFTER] Failed to download: {url}")
                
                # Add download summary to format_info
                if downloaded_files or failed_urls:
                    summary = "\n\n---\n## 📎 フォーマットファイルのダウンロード結果\n\n"
                    if downloaded_files:
                        summary += f"✅ **ダウンロード成功**: {len(downloaded_files)}件\n"
                        for file_path, filename in downloaded_files:
                            summary += f"  - {filename}\n"
                    if failed_urls:
                        summary += f"\n⚠️ **ダウンロード失敗**: {len(failed_urls)}件\n"
                        summary += "  （URLが無効、またはアクセスできませんでした）\n"
                    format_info += summary
            else:
                logging.info("[DRAFTER] No format file URLs found in search results, trying Playwright deep search...")
                
                # Fallback: Use Playwright for deep search
                try:
                    playwright_files = self._run_playwright_deep_search(grant_name, user_id)
                    if playwright_files:
                        downloaded_files.extend(playwright_files)
                        summary = "\n\n---\n## 📎 Playwright深掘り検索の結果\n\n"
                        summary += f"✅ **ダウンロード成功**: {len(playwright_files)}件\n"
                        for file_path, filename in playwright_files:
                            summary += f"  - {filename}\n"
                        format_info += summary
                    else:
                        logging.info("[DRAFTER] Playwright deep search also found no files")
                except Exception as pw_error:
                    logging.warning(f"[DRAFTER] Playwright deep search failed: {pw_error}")
            
            return (format_info, downloaded_files)
            
        except Exception as e:
            logging.error(f"[DRAFTER] Format research failed: {e}")
            # Return generic format as fallback
            return ("""
## 申請書フォーマット（一般的な形式）

### 質問項目
1. 団体概要（400字程度）
2. 事業の目的と背景（600字程度）
3. 具体的な活動計画
4. 期待される成果・効果
5. 予算計画
6. 今後の展望

### 審査ポイント
- 社会的意義と必要性
- 実現可能性
- 団体の実績と信頼性
- 費用対効果
""", [])

    def _extract_grant_keywords_for_validation(self, grant_name: str) -> List[str]:
        """
        助成金名からURL検証用のキーワードを抽出する。
        組織名や助成金名の主要部分を意味のある単位で抽出する。
        """
        import re
        keywords = []
        
        if not grant_name:
            return keywords
        
        # 財団名・法人名の抽出
        org_patterns = [
            r'(?:公益)?(?:社団|財団)法人\s*([^\s（(]+)',  # 法人名（括弧前まで）
            r'([^\s・（(]+財団)',      # ～財団
            r'([^\s・（(]+基金)',      # ～基金
            r'([^\s・（(]+協会)',      # ～協会
            r'([^\s・（(]+機構)',      # ～機構
        ]
        
        for pattern in org_patterns:
            match = re.search(pattern, grant_name)
            if match:
                keywords.append(match.group(1))
        
        # 中黒（・）やスペースで区切られた主要な部分を抽出
        # 例: "コンサベーション・アライアンス・ジャパン" → ["コンサベーション", "アライアンス", "ジャパン"]
        parts = re.split(r'[・\s　]+', grant_name)
        for part in parts:
            # 括弧や年度を除去
            clean_part = re.sub(r'[（(【「].*$', '', part)
            # 3文字以上の部分のみ追加
            if len(clean_part) >= 3:
                keywords.append(clean_part)
        
        # 重複を除去して返す
        return list(set(keywords))
    
    def _is_url_relevant_to_grant(self, url: str, grant_keywords: List[str]) -> bool:
        """
        URLが対象助成金に関連しているか判定する。
        ドメイン判定はFQDN（ドメイン名のみ）で行う。
        
        Returns:
            True if URL appears to be related to the grant
        """
        from urllib.parse import urlparse
        
        url_lower = url.lower()
        
        # URLからFQDN（ドメイン名）を抽出
        try:
            parsed = urlparse(url)
            fqdn = parsed.netloc.lower()  # 例: "outdoorconservation.jp"
            path = parsed.path.lower()    # 例: "/promotion-support"
        except Exception:
            fqdn = ""
            path = ""
        
        logging.debug(f"[DRAFTER] URL validation: FQDN={fqdn}, path={path}")
        
        # Google検索ページは除外（grounding_metadataが検索ページを返すことがある）
        if 'google.com' in fqdn or 'google.co.jp' in fqdn:
            if '/search' in path:
                logging.info(f"[DRAFTER] Blocking Google search page URL: {url[:100]}")
                return False
        
        # 明らかに無関係なドメインを除外（FQDNで判定）
        blocked_domains = [
            'amazon.co.jp', 'amazon.com', 'rakuten.co.jp',
            'yahoo.co.jp',  # Yahoo知恵袋など
            'twitter.com', 'x.com', 'facebook.com', 'instagram.com',
            'youtube.com', 'wikipedia.org',
            'note.com',  # 個人ブログ
            'time.is',  # 時刻サイト
            'weather.com', 'tenki.jp',  # 天気サイト
        ]
        for blocked in blocked_domains:
            if fqdn == blocked or fqdn.endswith('.' + blocked):
                return False
        
        # キーワードがあればURL全体で許可
        if grant_keywords:
            for keyword in grant_keywords:
                if keyword.lower() in url_lower:
                    return True
        
        # 信頼できる日本のドメイン（FQDNで判定）
        # .jp で終わるドメインは基本的に信頼
        if fqdn.endswith('.jp'):
            return True
        
        # その他の信頼ドメイン
        trusted_tlds = ['.org', '.edu', '.gov']
        for tld in trusted_tlds:
            if fqdn.endswith(tld):
                return True
        
        # ファイル拡張子を含むURLは許可（直接ファイルリンク）
        if any(ext in path for ext in ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.zip']):
            return True
        
        # 助成金関連キーワードをパスに含むURLは許可
        grant_related_keywords = [
            '助成', '補助', '支援', '申請', '公募', '募集',  # 日本語
            'grant', 'subsidy', 'application', 'support', 'promotion', 'fund'  # 英語
        ]
        for kw in grant_related_keywords:
            if kw in path:
                return True
        
        # それ以外は無関係と判断
        logging.info(f"[DRAFTER] URL does not match criteria, skipping: {url[:100]} (FQDN: {fqdn})")
        return False

    def _analyze_application_format(
        self, 
        format_files: List[Tuple[str, str]], 
        grant_name: str
    ) -> str:
        """
        申請フォーマットファイルの内容をGemini 3.0 Proで解析し、
        質問項目・記入欄・文字数制限などを抽出する。
        
        Args:
            format_files: ダウンロードしたファイルのリスト[(file_path, filename), ...]
            grant_name: 助成金名
            
        Returns:
            解析結果のテキスト（質問項目、文字数制限、記入のポイントなど）
        """
        if not format_files:
            logging.info("[DRAFTER] No format files to analyze")
            return ""
        
        logging.info(f"[DRAFTER] Analyzing {len(format_files)} format files with Gemini")
        
        # ファイル内容を収集
        file_contents_text = ""
        analyzed_count = 0
        
        for file_path, filename in format_files[:5]:  # 最大5ファイルまで
            try:
                file_ext = filename.lower().split('.')[-1] if '.' in filename else ''
                
                # PDFファイルの処理
                if file_ext == 'pdf':
                    content = self._extract_pdf_content(file_path)
                    if content:
                        file_contents_text += f"\n\n---\n### ファイル: {filename}\n{content[:8000]}\n"
                        analyzed_count += 1
                        
                # Word/Excelファイルの処理
                elif file_ext in ['doc', 'docx', 'xls', 'xlsx']:
                    content = self._extract_office_content(file_path, file_ext)
                    if content:
                        file_contents_text += f"\n\n---\n### ファイル: {filename}\n{content[:8000]}\n"
                        analyzed_count += 1
                        
                # テキストファイルの処理
                elif file_ext in ['txt', 'text']:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()[:8000]
                        file_contents_text += f"\n\n---\n### ファイル: {filename}\n{content}\n"
                        analyzed_count += 1
                        
            except Exception as e:
                logging.warning(f"[DRAFTER] Error reading file {filename}: {e}")
                continue
        
        if not file_contents_text or analyzed_count == 0:
            logging.info("[DRAFTER] Could not extract content from any files")
            return ""
        
        logging.info(f"[DRAFTER] Successfully extracted content from {analyzed_count} files")
        
        # Gemini 3.0 Proでファイル内容を解析
        try:
            format_analyzer_prompt = self.config.get("system_prompts", {}).get("format_analyzer", "")
            if not format_analyzer_prompt:
                logging.warning("[DRAFTER] format_analyzer prompt not found in config")
                return ""
            
            # プロンプトにファイル内容を埋め込み
            full_prompt = format_analyzer_prompt.replace("{file_contents}", file_contents_text)
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            
            analysis_result = response.text
            logging.info(f"[DRAFTER] Format analysis completed, length: {len(analysis_result)} chars")
            
            return analysis_result
            
        except Exception as e:
            logging.error(f"[DRAFTER] Format analysis failed: {e}")
            return ""
    
    def _extract_pdf_content(self, file_path: str) -> str:
        """PDFファイルからテキストを抽出する"""
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(file_path)
            text_content = ""
            
            for page_num in range(min(doc.page_count, 10)):  # 最大10ページまで
                page = doc[page_num]
                text_content += page.get_text() + "\n"
            
            doc.close()
            return text_content.strip()
            
        except ImportError:
            logging.warning("[DRAFTER] PyMuPDF (fitz) not installed, skipping PDF extraction")
            return ""
        except Exception as e:
            logging.warning(f"[DRAFTER] PDF extraction failed: {e}")
            return ""
    
    def _extract_office_content(self, file_path: str, file_ext: str) -> str:
        """Word/Excelファイルからテキストを抽出する"""
        try:
            if file_ext in ['doc', 'docx']:
                from docx import Document
                doc = Document(file_path)
                return "\n".join([para.text for para in doc.paragraphs])
                
            elif file_ext in ['xls', 'xlsx']:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, read_only=True)
                text_content = ""
                
                for sheet in wb.worksheets[:3]:  # 最大3シートまで
                    for row in sheet.iter_rows(max_row=100):  # 最大100行まで
                        row_text = " | ".join([str(cell.value) if cell.value else "" for cell in row])
                        if row_text.strip():
                            text_content += row_text + "\n"
                
                return text_content.strip()
                
        except ImportError as e:
            logging.warning(f"[DRAFTER] Office library not installed: {e}")
            return ""
        except Exception as e:
            logging.warning(f"[DRAFTER] Office file extraction failed: {e}")
            return ""

    def _scrape_url_for_files(self, url: str, user_id: str) -> List[Tuple[str, str]]:

        """
        Scrape a specific URL for format files using Playwright.
        This is used when we have a verified URL from Observer.
        """
        try:
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(self._async_scrape_url_for_files(url, user_id))
        except Exception as e:
            logging.error(f"[DRAFTER] _scrape_url_for_files error: {e}")
            return []
    
    async def _async_scrape_url_for_files(self, url: str, user_id: str) -> List[Tuple[str, str]]:
        """
        Async method to scrape a URL for format files.
        """
        downloaded_files = []
        
        try:
            # Use page scraper to get grant info and files
            grant_info = await self.page_scraper.find_grant_info(url, "")
            
            if not grant_info.get('accessible'):
                logging.warning(f"[DRAFTER] Page not accessible: {url}")
                return []
            
            format_files = grant_info.get('format_files', [])
            logging.info(f"[DRAFTER] Found {len(format_files)} format files on page")
            
            # Download files
            for file_info in format_files[:5]:
                file_url = file_info.get('url')
                if not file_url:
                    continue
                
                logging.info(f"[DRAFTER] Downloading: {file_url}")
                result = self.file_downloader.download_file(file_url, user_id)
                if result:
                    downloaded_files.append(result)
                    logging.info(f"[DRAFTER] Downloaded: {result[1]}")
                    
        except Exception as e:
            logging.error(f"[DRAFTER] Async scrape error: {e}")
        
        return downloaded_files

    def _run_playwright_deep_search(self, grant_name: str, user_id: str) -> List[Tuple[str, str]]:
        """
        Run Playwright-based deep search for format files.
        Uses nest_asyncio to allow running async code within Discord.py's event loop.
        """
        try:
            import nest_asyncio
            nest_asyncio.apply()
            
            # Extract organization name for targeted search
            from src.logic.grant_validator import GrantValidator
            validator = GrantValidator()
            org_name = validator.extract_organization_name(grant_name)
            
            if not org_name:
                logging.info("[DRAFTER] Could not extract organization name for Playwright search")
                return []
            
            # Sanitize grant_name: remove command-like phrases that shouldn't be in search
            sanitized_grant_name = self._sanitize_grant_name_for_search(grant_name)
            
            # Build more specific search URL with grant name for better targeting
            # Include both organization name and grant name for more precise results
            search_query = f'"{org_name}" "{sanitized_grant_name}" 申請書 様式 filetype:pdf OR filetype:docx OR filetype:xlsx'
            search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
            
            logging.info(f"[DRAFTER] Playwright deep search for: {grant_name} (org: {org_name})")
            
            # Now we can safely run asyncio.run() within the existing event loop
            return asyncio.run(self._async_playwright_deep_search(search_url, grant_name, user_id))
            
        except Exception as e:
            logging.error(f"[DRAFTER] Playwright deep search error: {e}")
            return []
    
    async def _async_playwright_deep_search(
        self, 
        start_url: str, 
        grant_name: str, 
        user_id: str
    ) -> List[Tuple[str, str]]:
        """
        Async Playwright deep search for format files.
        """
        downloaded_files = []
        
        try:
            # Use deep search to find format files (pass grant_name for relevance filtering)
            format_files = await self.page_scraper.deep_search_format_files(start_url, max_depth=2, grant_name=grant_name)
            
            if not format_files:
                logging.info("[DRAFTER] Playwright found no format files")
                return []
            
            logging.info(f"[DRAFTER] Playwright found {len(format_files)} potential files")
            
            # Download top-scored files
            for file_info in format_files[:5]:
                file_url = file_info.get('url')
                if not file_url:
                    continue
                
                logging.info(f"[DRAFTER] Downloading: {file_url}")
                result = self.file_downloader.download_file(file_url, user_id)
                if result:
                    downloaded_files.append(result)
                    logging.info(f"[DRAFTER] Downloaded: {result[1]}")
                    
        except Exception as e:
            logging.error(f"[DRAFTER] Async deep search error: {e}")
        
        return downloaded_files

    def create_draft(self, user_id: str, grant_info: str) -> tuple[str, str, str, List[Tuple[str, str]]]:
        """
        Generates a grant application draft based on researched format with progress notifications.
        
        Returns:
            tuple: (message, draft_content, filename, format_files)
            - format_files: List of (file_path, filename) tuples for downloaded files
        """
        import logging
        from src.utils.progress_notifier import get_progress_notifier, ProgressStage
        
        logging.info(f"[DRAFTER] create_draft started for user: {user_id}")
        notifier = get_progress_notifier()
        
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()
        
        logging.info(f"[DRAFTER] Profile loaded, length: {len(profile)} chars")
        
        # Extract grant name and URL from grant_info
        grant_name = grant_info.strip()
        grant_url = None
        
        # Try to extract URL from grant_info
        import re
        url_match = re.search(r'URL:\s*(https?://[^\s]+)', grant_info)
        if url_match:
            grant_url = url_match.group(1).strip()
            logging.info(f"[DRAFTER] Extracted URL from grant_info: {grant_url}")
        
        # Try to extract just the grant name if it contains other info
        name_match = re.search(r'助成金名:\s*(.+?)(?:\n|$)', grant_info)
        if name_match:
            grant_name = name_match.group(1).strip()
        elif "助成" in grant_name:
            # Find the grant name pattern
            match = re.search(r'[^\s]+助成[^\s]*', grant_name)
            if match:
                grant_name = match.group(0)
        
        # Create display name (max 20 chars) for notifications
        grant_display_name = grant_name[:20] + "..." if len(grant_name) > 20 else grant_name
        
        logging.info(f"[DRAFTER] Grant name: {grant_name}, URL: {grant_url}")
        
        # Start notification
        notifier.notify_sync(
            ProgressStage.STARTING,
            f"✨ [{grant_display_name}] ドラフト作成を開始します..."
        )
        
        # Step 1: Research the application format (prioritize URL if available)
        logging.info(f"[DRAFTER] Step 1: Researching format for '{grant_name}'")
        format_info, format_files = self._research_grant_format(grant_name, user_id, grant_url=grant_url)
        
        # Step 1.5: Early file classification to filter irrelevant files
        # This prevents wasting resources on analyzing unrelated files
        related_files = []
        excluded_files = []
        if format_files:
            logging.info(f"[DRAFTER] Step 1.5: Classifying {len(format_files)} files for relevance")
            notifier.notify_sync(
                ProgressStage.PROCESSING,
                f"🔍 [{grant_display_name}] ファイルの関連性を確認中..."
            )
            
            for file_path, file_name in format_files:
                file_type = self.file_classifier.classify_format_file(file_name, file_path, grant_name)
                
                # Check if file is unrelated (contains "別の助成金の可能性")
                if "別の助成金の可能性" in file_type:
                    excluded_files.append((file_path, file_name, file_type))
                    logging.info(f"[DRAFTER] Excluding unrelated file: {file_name}")
                else:
                    related_files.append((file_path, file_name, file_type))
                    logging.info(f"[DRAFTER] Related file: {file_name} -> {file_type}")
            
            logging.info(f"[DRAFTER] File classification complete: {len(related_files)} related, {len(excluded_files)} excluded")
            
            # Update format_files to only include related files (without file_type for compatibility)
            format_files = [(fp, fn) for fp, fn, _ in related_files]
        
        # Step 2: Analyze downloaded format files with Gemini 3.0 Pro (only related files)
        format_analysis = ""
        if format_files:
            logging.info(f"[DRAFTER] Step 2: Analyzing {len(format_files)} format files with Gemini")
            notifier.notify_sync(
                ProgressStage.PROCESSING,
                f"📋 [{grant_display_name}] 申請フォーマットを解析中..."
            )
            format_analysis = self._analyze_application_format(format_files, grant_name)
            if format_analysis:
                logging.info(f"[DRAFTER] Format analysis completed, length: {len(format_analysis)} chars")
            else:
                logging.info("[DRAFTER] Format analysis returned empty, using format_info only")
        
        # Step 3: Generate draft based on format and analysis
        logging.info(f"[DRAFTER] Step 3: Generating format-aware draft")
        
        notifier.notify_sync(
            ProgressStage.PROCESSING,
            f"📝 [{grant_display_name}] ドラフトを生成中..."
        )
        
        # Combine format_info and format_analysis for comprehensive context
        combined_format_info = format_info
        if format_analysis:
            combined_format_info += f"\n\n---\n\n# 申請フォーマット詳細解析結果\n{format_analysis}"
        
        full_prompt = f"""
{self.system_prompt}

# Soul Profile（魂のプロファイル）
{profile}

# 対象助成金
{grant_info}

# 申請書フォーマット情報
{combined_format_info}

# タスク
上記の申請書フォーマット（特に「申請フォーマット詳細解析結果」の質問項目）に従って、各質問項目に対する回答を作成してください。

**重要な指示:**
1. 解析結果の質問項目一覧に記載された項目ごとに見出しを付けて回答を作成
2. 文字数制限が明記されている場合はそれに収まるように調整
3. Soul Profileの情報を最大限活用
4. 各回答の後に簡単な📝記入のポイントを追記
5. 審査で重視される点を意識して回答を作成

**出力形式:**
# [助成金名] 申請書ドラフト

## 1. [質問項目1]
[回答内容]
📝 ポイント: [この項目で強調すべき点]

## 2. [質問項目2]
[回答内容]
📝 ポイント: [この項目で強調すべき点]

...

---
## 📋 全体の考慮点
[申請全体で気をつけるべき点]

## 🌟 アピールポイント
[特に強調すべき団体の強み]

## ⚠️ 懸念点・改善提案
[申請で弱くなりそうな点と対策]
"""
        try:
            logging.info(f"[DRAFTER] Calling Gemini model: {self.model_name}")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            draft_content = response.text
            logging.info(f"[DRAFTER] Draft generated, length: {len(draft_content)} chars")
            
            # Extract a title (first line or generic)
            lines = draft_content.split('\n')
            title = "Grant_Draft"
            if lines and lines[0].startswith('# '):
                 title = lines[0].replace('# ', '').strip()
            
            logging.info(f"[DRAFTER] Title: {title}")
            
            notifier.notify_sync(
                ProgressStage.PROCESSING,
                f"💾 [{grant_display_name}] ドキュメントを保存中..."
            )
            
            file_path = self.docs_tool.create_document(title, draft_content, user_id=user_id)
            logging.info(f"[DRAFTER] Document saved: {file_path}")
            
            # Extract filename from path
            import os
            if 'gs://' in file_path:
                # GCS path: gs://bucket/drafts/user_id/filename.md
                filename = file_path.split('/')[-1]
            elif 'Google Doc' in file_path:
                # Google Docs: extract from message
                filename = f"{title}.md"
            else:
                # Local path
                filename = os.path.basename(file_path)
            
            logging.info(f"[DRAFTER] Filename: {filename}")
            
            message = f"ドラフトを作成しました: {file_path}"
            
            # Step 4: Fill format files with draft content (field-by-field processing)
            filled_files = []
            if format_files:
                logging.info(f"[DRAFTER] Step 4: Attempting to fill {len(format_files)} format files (field-by-field)")
                notifier.notify_sync(
                    ProgressStage.PROCESSING,
                    f"📝 [{grant_display_name}] フォーマットに項目別に入力中..."
                )
                
                # 全ファイルのfield_valuesを蓄積（懸念点レポート用）
                all_field_values = {}
                
                for file_path_orig, file_name_orig in format_files:
                    try:
                        # Only process Excel/Word files
                        ext = os.path.splitext(file_name_orig)[1].lower()
                        if ext not in ['.xlsx', '.xlsm', '.xls', '.docx', '.doc']:
                            logging.info(f"[DRAFTER] Skipping non-fillable file: {file_name_orig}")
                            continue
                        
                        # Analyze format fields using VLM
                        fields, file_type = self.format_mapper.analyze_format_file(file_path_orig)
                        
                        if not fields:
                            logging.info(f"[DRAFTER] No fillable fields found in: {file_name_orig}")
                            continue
                        
                        logging.info(f"[DRAFTER] Found {len(fields)} fields in {file_name_orig}")
                        
                        # Fill fields individually using profile (field-by-field processing)
                        # Note: No Discord notification per field - progress is logged only
                        field_values = self.format_mapper.fill_fields_individually(
                            fields=fields,
                            profile=profile,
                            grant_name=grant_name,
                            grant_info=grant_info
                        )
                        
                        if not field_values:
                            logging.info(f"[DRAFTER] Could not fill fields in: {file_name_orig}")
                            continue
                        
                        # 懸念点レポート用に蓄積
                        all_field_values.update(field_values)
                        
                        # Fill the document
                        filled_path, fill_message = self.document_filler.fill_document(
                            file_path_orig,
                            field_values,
                            user_id
                        )
                        
                        if filled_path:
                            filled_filename = os.path.basename(filled_path)
                            filled_files.append((filled_path, filled_filename))
                            logging.info(f"[DRAFTER] Successfully filled: {filled_filename}")
                        else:
                            logging.warning(f"[DRAFTER] Fill failed for {file_name_orig}: {fill_message}")
                            
                    except Exception as fill_error:
                        logging.warning(f"[DRAFTER] Error filling {file_name_orig}: {fill_error}")
                
                if filled_files:
                    message += f"\n📋 {len(filled_files)}件のフォーマットに項目別入力しました"
                
                # 懸念点レポートを生成
                if all_field_values:
                    concern_report = self.format_mapper.generate_concern_report(all_field_values)
                    if concern_report:
                        message += f"\n\n{concern_report}"
                        logging.info(f"[DRAFTER] Generated concern report")
                    
                    # 事務局長レビューを生成
                    director_review = self._generate_director_review(
                        grant_name=grant_name,
                        field_values=all_field_values,
                        profile=profile
                    )
                    if director_review:
                        message += f"\n\n{director_review}"
                        logging.info(f"[DRAFTER] Generated director review")
            
            # Completion notification
            notifier.notify_sync(
                ProgressStage.COMPLETED,
                f"✅ [{grant_display_name}] ドラフト作成完了！"
            )
            
            logging.info(f"[DRAFTER] create_draft completed successfully, filled_files: {len(filled_files)}")
            # Return related_files with file_type info (file_path, file_name, file_type)
            return (message, draft_content, filename, related_files, filled_files)
            
        except Exception as e:
            logging.error(f"[DRAFTER] Error in create_draft: {e}", exc_info=True)
            
            # Error notification
            notifier.notify_sync(
                ProgressStage.ERROR,
                f"⚠️ [{grant_display_name}] エラー発生: {str(e)[:30]}..."
            )
            
            error_msg = f"ドラフト作成エラー: {e}"
            return (error_msg, "", "", [], [])


    def list_drafts(self, user_id: str) -> str:
        """
        Lists all drafts for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Formatted list of drafts or message if none found
        """
        try:
            drafts = self.docs_tool.list_drafts(user_id)
            
            if not drafts:
                return "まだドラフトが作成されていません。「助成金申請書を書いて」とリクエストしてください。"
            
            result = f"📄 **保存済みドラフト一覧** ({len(drafts)}件)\n\n"
            for i, filename in enumerate(drafts, 1):
                result += f"{i}. `{filename}`\n"
            
            result += "\n💡 特定のドラフトを見るには「[ファイル名]を見せて」または「最新のドラフトを見せて」と送信してください。"
            
            return result
            
        except Exception as e:
            return f"ドラフト一覧取得エラー: {e}"

    def clear_drafts(self, user_id: str) -> str:
        """
        Clears all drafts for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Success message
        """
        try:
            return self.docs_tool.clear_drafts(user_id)
        except Exception as e:
            return f"ドラフトクリアエラー: {e}"

    def get_latest_draft(self, user_id: str) -> tuple[str, Optional[str]]:
        """
        Gets the latest draft for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Tuple of (message, content). If content is present, it should be sent as attachment.
        """
        try:
            drafts = self.docs_tool.list_drafts(user_id)
            
            if not drafts:
                return ("まだドラフトが作成されていません。", None)
            
            # Sort by filename (which includes timestamp)
            latest_draft = sorted(drafts)[-1]
            content = self.docs_tool.get_draft(user_id, latest_draft)
            
            if not content:
                return (f"ドラフト '{latest_draft}' が見つかりませんでした。", None)
            
            message = f"📄 **最新のドラフト**: `{latest_draft}`\n\n"
            
            # If content is short, include it in message
            if len(content) <= 1800:
                message += f"```markdown\n{content}\n```"
                return (message, None)
            else:
                # Return content for file attachment
                message += "（ファイルとして送信します）"
                return (message, content)
                
        except Exception as e:
            return (f"最新ドラフト取得エラー: {e}", None)

    def get_draft(self, user_id: str, filename: str) -> tuple[str, Optional[str]]:
        """
        Gets a specific draft by filename.
        
        Args:
            user_id: User ID
            filename: Draft filename
            
        Returns:
            Tuple of (message, content). If content is present, it should be sent as attachment.
        """
        try:
            content = self.docs_tool.get_draft(user_id, filename)
            
            if not content:
                # Try fuzzy match
                drafts = self.docs_tool.list_drafts(user_id)
                matches = [d for d in drafts if filename.lower() in d.lower()]
                
                if matches:
                    if len(matches) == 1:
                        # Use the matched file
                        filename = matches[0]
                        content = self.docs_tool.get_draft(user_id, filename)
                    else:
                        suggestion = "\n\n候補:\n" + "\n".join([f"- {m}" for m in matches])
                        return (f"ファイル名が曖昧です。{suggestion}", None)
                else:
                    return (f"ドラフト '{filename}' が見つかりませんでした。「ドラフト一覧」で確認してください。", None)
            
            message = f"📄 **ドラフト**: `{filename}`\n\n"
            
            # If content is short, include it in message
            if len(content) <= 1800:
                message += f"```markdown\n{content}\n```"
                return (message, None)
            else:
                # Return content for file attachment
                message += "（ファイルとして送信します）"
                return (message, content)
                
        except Exception as e:
            return (f"ドラフト取得エラー: {e}", None)

    def _generate_director_review(
        self, 
        grant_name: str, 
        field_values: Dict[str, Any],
        profile: str
    ) -> str:
        """
        事務局長の観点からドラフトをレビューし、コメントを生成する。
        
        Args:
            grant_name: 助成金名
            field_values: 入力されたフィールド値
            profile: NPOプロファイル
            
        Returns:
            Markdown形式の事務局長レビュー
        """
        if not self.client or not field_values:
            return ""
        
        try:
            # フィールド値をテキスト化
            fields_text = "\n".join([
                f"- **{data.get('field_name', fid)}**: {data.get('value', '')[:200]}..."
                if len(data.get('value', '')) > 200
                else f"- **{data.get('field_name', fid)}**: {data.get('value', '')}"
                for fid, data in field_values.items()
                if data.get('value')
            ])
            
            prompt = f"""あなたはNPOの事務局長として、助成金申請書のドラフトをレビューしてください。

# 対象助成金
{grant_name}

# NPOプロファイル概要
{profile[:2000]}

# 入力されたドラフト内容
{fields_text[:4000]}

# レビュー観点
1. **全体評価**: 申請書全体としての完成度を評価してください
2. **強み**: この申請書の良い点を挙げてください
3. **改善提案**: より説得力を高めるための具体的な改善提案をしてください
4. **確認事項**: 提出前に団体内で確認すべき事項を挙げてください

# 出力形式
事務局長としての簡潔なコメント（300字程度）を出力してください。
箇条書きではなく、自然な文章で記述してください。
"""
            
            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt
            )
            
            review_text = response.text.strip()
            
            if review_text:
                return f"## 📝 事務局長レビュー\n\n{review_text}"
            
            return ""
            
        except Exception as e:
            logging.warning(f"[DRAFTER] Director review generation failed: {e}")
            return ""
