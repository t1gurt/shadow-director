"""
Grant Page Scraper - Specialized scraping logic for grant/subsidy pages.

This module provides functionality to explore grant websites, find application forms,
detect format files, and extract deadline information using Playwright-based DOM analysis.
"""

import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse


class GrantPageScraper:
    """
    Specialized scraper for grant/subsidy websites.
    Uses SiteExplorer for DOM-based analysis to find grant information.
    """
    
    # Keywords indicating grant application pages
    GRANT_PAGE_KEYWORDS = [
        '募集', '公募', '応募', '申請', '助成', 
        '補助金', '支援', '交付', 'grant', 'application',
        '要項', '要綱', '様式', 'フォーマット'
    ]
    
    # Keywords for format/application files (A: 拡充版)
    FORMAT_FILE_KEYWORDS = [
        # 申請書類系
        '申請書', '応募書', '申込書', '届出書', '調書',
        # 様式・フォーマット系
        '様式', 'フォーマット', 'テンプレート', '書式', '雛形', 'ひな形',
        # 募集要項系（追加）
        '募集要項', '公募要領', '応募要項', '交付要綱', '実施要領',
        '募集案内', 'ガイドライン', 'guidelines', '公募要項',
        # ダウンロード系
        'ダウンロード', 'download', 'DL', '取得', '入手',
        # ファイル種別系
        'Word', 'Excel', 'PDF', 'ワード', 'エクセル',
        # 記入系
        '記入例', '記載例', '作成例', '見本',
        # その他
        'application', 'form', 'template', 'format',
        '書類', '資料', '用紙', '別紙', '別記'
    ]
    
    # Keywords for deadline detection
    DEADLINE_KEYWORDS = [
        '締切', '締め切り', '期限', '期日', '終了',
        'deadline', '〆切', '必着', '消印有効'
    ]
    
    # Keywords for navigation to file download pages (D: 複数ページ探索用)
    DOWNLOAD_PAGE_KEYWORDS = [
        '申請書類', '提出書類', '様式ダウンロード', '書類ダウンロード',
        'ダウンロード', '申請様式', '申請方法', '応募方法',
        '書類一覧', '必要書類', '提出資料', '申請に必要な書類',
        '関連ファイル', '添付資料'
    ]
    
    # SGNA Phase 5: Popup close keywords for auto-dismissal
    POPUP_CLOSE_KEYWORDS = [
        '閉じる', 'close', '×', 'キャンセル', 'cancel',
        'いいえ', 'no', 'skip', 'スキップ', '後で', 'later'
    ]
    
    # Debug configuration
    DEBUG_SCREENSHOT_DIR = '/tmp/grant_scraper_debug'
    
    def __init__(self, site_explorer=None, gemini_client=None, model_name: str = "gemini-3.0-pro", timeout: int = 15000):
        """
        Initialize GrantPageScraper.
        
        Args:
            site_explorer: SiteExplorer instance (will be created if not provided)
            gemini_client: Gemini API client for visual reasoning fallback
            model_name: Gemini model name for visual analysis
            timeout: Playwright timeout in milliseconds (default 15000ms = 15 seconds)
        """
        self.site_explorer = site_explorer
        self.gemini_client = gemini_client
        self.model_name = model_name
        self.timeout = timeout
        self.visual_analyzer = None
        self.logger = logging.getLogger(__name__)
        
        # Initialize visual analyzer if client provided
        if gemini_client:
            from src.logic.visual_analyzer import VisualAnalyzer
            self.visual_analyzer = VisualAnalyzer(gemini_client, model_name)
    
    async def find_grant_info(self, url: str, grant_name: str = None) -> Dict[str, Any]:
        """
        Find grant information from a URL - main entry point.
        
        Args:
            url: Starting URL to explore
            grant_name: Name of the grant to find (optional, for better matching)
            
        Returns:
            Dictionary with grant information including files, deadlines, etc.
        """
        from src.tools.site_explorer import SiteExplorer
        
        result = {
            'url': url,
            'accessible': False,
            'title': None,
            'format_files': [],
            'deadline_info': None,
            'related_links': [],
            'error': None
        }
        
        explorer = self.site_explorer
        created_explorer = False
        
        try:
            if not explorer:
                explorer = SiteExplorer(headless=True, timeout=self.timeout)
                await explorer.start()
                created_explorer = True
            
            # Access the main page
            page = await explorer.access_page(url)
            if not page:
                result['error'] = 'ページにアクセスできませんでした'
                return result
            
            result['accessible'] = True
            
            # Get page info
            page_info = await explorer.get_page_info(page)
            title = page_info.get('title', '')
            result['title'] = title
            result['url'] = page_info.get('url', url)  # May have been redirected
            
            # 障害パターン検知（ログイン壁、404、アクセス拒否など）
            obstacle_type = self._detect_obstacle(title)
            if obstacle_type:
                result['obstacle_detected'] = True
                result['obstacle_type'] = obstacle_type
                self.logger.info(f"[GRANT_SCRAPER] 障害検知: {obstacle_type} (title: {title})")
            
            # Extract all links
            all_links = await explorer.extract_links(page)
            
            # Find format files from current page
            format_files = await self._find_format_files(all_links, page, grant_name)
            
            # Extract page text for analysis
            page_text = await explorer.find_text_content(page)
            
            # (C) Text analysis: Look for download instructions in text
            if len(format_files) == 0:
                text_found_urls = self._extract_urls_from_text(page_text, all_links)
                for url_info in text_found_urls:
                    format_files.append(url_info)
                self.logger.info(f"[GRANT_SCRAPER] Text analysis found {len(text_found_urls)} additional URLs")
            
            # (D) Multi-page exploration: Follow download-related links
            if len(format_files) < 3:
                download_pages = self._find_download_page_links(all_links)
                self.logger.info(f"[GRANT_SCRAPER] Found {len(download_pages)} download page links to explore")
                
                for dl_link in download_pages[:3]:  # Explore up to 3 download pages
                    dl_url = dl_link.get('href')
                    if not dl_url:
                        continue
                    
                    try:
                        self.logger.info(f"[GRANT_SCRAPER] Exploring download page: {dl_url}")
                        dl_page = await explorer.access_page(dl_url)
                        if dl_page:
                            dl_links = await explorer.extract_links(dl_page)
                            dl_files = await self._find_format_files(dl_links, dl_page, grant_name)
                            
                            for f in dl_files:
                                f['found_at'] = dl_url
                                # Avoid duplicates
                                if not any(existing.get('url') == f.get('url') for existing in format_files):
                                    format_files.append(f)
                            
                            await dl_page.close()
                            self.logger.info(f"[GRANT_SCRAPER] Found {len(dl_files)} files on download page")
                    except Exception as dl_e:
                        self.logger.warning(f"[GRANT_SCRAPER] Error exploring download page {dl_url}: {dl_e}")
            
            result['format_files'] = format_files
            
            # Extract deadline information from page text
            deadline_info = self._extract_deadline(page_text)
            result['deadline_info'] = deadline_info
            
            # Find related grant pages for deeper exploration
            related_links = self._filter_grant_related_links(all_links, grant_name)
            result['related_links'] = related_links[:10]  # Limit to 10 most relevant
            
            await page.close()
            
        except Exception as e:
            self.logger.error(f"[GRANT_SCRAPER] Error exploring {url}: {e}")
            result['error'] = str(e)
        finally:
            if created_explorer and explorer:
                await explorer.close()
        
        return result
    
    async def deep_search_format_files(self, start_url: str, max_depth: int = 2, grant_name: str = None) -> List[Dict[str, Any]]:
        """
        Deep search for format files by following links up to max_depth levels.
        
        Args:
            start_url: Starting URL
            max_depth: Maximum depth of link following
            grant_name: Grant name for relevance filtering (optional but recommended)
            
        Returns:
            List of found format file information
        """
        from src.tools.site_explorer import SiteExplorer
        
        found_files = []
        visited_urls = set()
        urls_to_visit = [(start_url, 0)]  # (url, depth)
        
        # Log if grant_name is missing for debugging
        if not grant_name:
            self.logger.warning("[GRANT_SCRAPER] deep_search_format_files called without grant_name - relevance filtering will be limited")
        
        async with SiteExplorer(headless=True, timeout=self.timeout) as explorer:
            while urls_to_visit:
                current_url, depth = urls_to_visit.pop(0)
                
                if current_url in visited_urls or depth > max_depth:
                    continue
                
                visited_urls.add(current_url)
                self.logger.info(f"[GRANT_SCRAPER] Deep search depth {depth}: {current_url}")
                
                page = await explorer.access_page(current_url)
                if not page:
                    continue
                
                try:
                    # Extract links
                    all_links = await explorer.extract_links(page)
                    
                    # Find format files (pass grant_name for relevance scoring)
                    format_files = await self._find_format_files(all_links, page, grant_name)
                    for f in format_files:
                        f['found_at'] = current_url
                        f['depth'] = depth
                    found_files.extend(format_files)
                    
                    # Queue related links for further exploration (with grant_name for better filtering)
                    if depth < max_depth:
                        related = self._filter_grant_related_links(all_links, grant_name)
                        for link in related[:5]:  # Limit to 5 links per page
                            link_url = link.get('href')
                            if link_url and link_url not in visited_urls:
                                urls_to_visit.append((link_url, depth + 1))
                    
                    await page.close()
                    
                except Exception as e:
                    self.logger.error(f"[GRANT_SCRAPER] Error in deep search at {current_url}: {e}")
        
        # Remove duplicates by URL
        unique_files = {}
        for f in found_files:
            url = f.get('url')
            if url and url not in unique_files:
                unique_files[url] = f
        
        return list(unique_files.values())
    
    async def _find_format_files(
        self, 
        links: List[Dict[str, str]], 
        page: Any = None,
        grant_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Find format files from a list of links.
        
        Args:
            links: List of link dictionaries
            page: Playwright page object (for additional analysis)
            grant_name: Grant name for relevance scoring
            
        Returns:
            List of format file info dictionaries
        """
        format_files = []
        
        # Keywords that indicate a file download link (even without file extension in URL)
        FILE_INDICATOR_KEYWORDS = [
            'word', 'excel', 'pdf', 'ワード', 'エクセル',
            '申請書', '様式', 'ダウンロード', 'download', '.doc', '.xls', '.pdf'
        ]
        
        for link in links:
            href = link.get('href', '')
            text = link.get('text', '')
            is_file = link.get('is_file', False)
            
            # Check if this looks like a file link (by extension OR by keywords in text)
            text_lower = text.lower()
            is_likely_file = is_file
            
            # Also check link text for file-related keywords
            if not is_likely_file:
                for indicator in FILE_INDICATOR_KEYWORDS:
                    if indicator in text_lower or indicator in href.lower():
                        is_likely_file = True
                        break
            
            if not is_likely_file:
                continue
            
            # Score relevance
            score = 0
            
            # Check link text for format keywords (text_lower already defined above)
            for keyword in self.FORMAT_FILE_KEYWORDS:
                if keyword.lower() in text_lower:
                    score += 10
            
            # Check if grant name appears in filename or link text
            if grant_name:
                grant_name_parts = grant_name.split()[:3]  # First 3 words
                for part in grant_name_parts:
                    if len(part) >= 2 and part.lower() in (href.lower() + text_lower):
                        score += 5
            
            # Determine file type
            parsed = urlparse(href)
            path_lower = parsed.path.lower()
            file_type = 'unknown'
            if path_lower.endswith('.pdf'):
                file_type = 'pdf'
            elif path_lower.endswith(('.doc', '.docx')):
                file_type = 'word'
            elif path_lower.endswith(('.xls', '.xlsx')):
                file_type = 'excel'
            elif path_lower.endswith('.zip'):
                file_type = 'zip'
            
            # Extract filename
            filename = parsed.path.split('/')[-1] if parsed.path else 'unknown'
            
            format_files.append({
                'url': href,
                'text': text,
                'filename': filename,
                'file_type': file_type,
                'relevance_score': score
            })
        
        # Sort by relevance score
        format_files.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        self.logger.info(f"[GRANT_SCRAPER] Found {len(format_files)} format files")
        return format_files
    
    def _filter_grant_related_links(
        self, 
        links: List[Dict[str, str]], 
        grant_name: str = None
    ) -> List[Dict[str, str]]:
        """
        Filter links to find those related to grant applications.
        
        Args:
            links: List of link dictionaries
            grant_name: Grant name for relevance scoring
            
        Returns:
            Filtered and scored list of links
        """
        scored_links = []
        
        for link in links:
            if link.get('is_file'):
                continue  # Skip file links
            
            href = link.get('href', '')
            text = link.get('text', '')
            
            # Skip empty or non-navigable links
            if not href or len(text) < 2:
                continue
            
            # Score relevance
            score = 0
            combined = (href + ' ' + text).lower()
            
            for keyword in self.GRANT_PAGE_KEYWORDS:
                if keyword.lower() in combined:
                    score += 10
            
            if grant_name:
                # Improved splitting for Japanese names (handle dots and full-width spaces)
                import re
                grant_name_parts = re.split(r'[・\s　]+', grant_name)
                # Filter out short parts and usage of parens
                valid_parts = [p for p in grant_name_parts if len(p) >= 2]
                
                # Check for matches
                matches = 0
                for part in valid_parts:
                    # Remove tokens inside parentheses for cleaner matching
                    clean_part = re.sub(r'[（(【「].*?([)）】」]|$)', '', part)
                    if len(clean_part) >= 2 and clean_part.lower() in combined:
                        score += 5
                        matches += 1
                
                # Bonus if multiple parts match (high confidence)
                if matches >= 2:
                    score += 10
            
            if score > 0:
                scored_links.append({
                    **link,
                    'relevance_score': score
                })
        
        # Sort by score
        scored_links.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return scored_links
    
    def _find_download_page_links(self, links: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Find links that lead to download/application file pages (D: Multi-page exploration).
        
        Args:
            links: List of link dictionaries
            
        Returns:
            List of links to download pages, sorted by relevance
        """
        download_links = []
        
        for link in links:
            if link.get('is_file'):
                continue  # Skip direct file links
            
            href = link.get('href', '')
            text = link.get('text', '')
            
            if not href or len(text) < 2:
                continue
            
            combined = (href + ' ' + text).lower()
            score = 0
            
            # Check for download page keywords
            for keyword in self.DOWNLOAD_PAGE_KEYWORDS:
                if keyword.lower() in combined:
                    score += 15
            
            # Check for format file keywords in link text
            for keyword in self.FORMAT_FILE_KEYWORDS:
                if keyword.lower() in combined:
                    score += 10
            
            if score > 0:
                download_links.append({
                    **link,
                    'download_score': score
                })
        
        download_links.sort(key=lambda x: x.get('download_score', 0), reverse=True)
        return download_links
    
    def _extract_urls_from_text(self, text: str, existing_links: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Extract URLs mentioned in text that may not be clickable links (C: Text analysis).
        Also finds references like "様式は○○からダウンロードしてください".
        
        Args:
            text: Page text content
            existing_links: Already found links to avoid duplicates
            
        Returns:
            List of additional file URLs found in text
        """
        found_urls = []
        existing_hrefs = {link.get('href', '') for link in existing_links}
        
        # Pattern 1: Direct URLs in text
        url_pattern = r'https?://[^\s<>"\')\]]+\.(?:pdf|doc|docx|xls|xlsx|zip)'
        url_matches = re.findall(url_pattern, text, re.IGNORECASE)
        
        for url in url_matches:
            if url not in existing_hrefs:
                found_urls.append({
                    'url': url,
                    'text': 'テキスト内URL',
                    'filename': url.split('/')[-1],
                    'file_type': self._get_file_type(url),
                    'relevance_score': 5,
                    'source': 'text_analysis'
                })
        
        # Pattern 2: Look for download instructions mentioning file names
        # e.g., "申請書様式（Word）をダウンロード"
        instruction_patterns = [
            r'(申請書|様式|フォーマット)[^。\n]{0,30}(ダウンロード|取得|入手)',
            r'(ダウンロード|取得|入手)[^。\n]{0,30}(申請書|様式|フォーマット)',
        ]
        
        has_download_instruction = False
        for pattern in instruction_patterns:
            if re.search(pattern, text):
                has_download_instruction = True
                break
        
        # If download instructions exist but no files found, log for debugging
        if has_download_instruction and len(found_urls) == 0 and len(existing_links) == 0:
            self.logger.info("[GRANT_SCRAPER] Download instructions found in text but no file URLs detected")
        
        return found_urls
    
    def _get_file_type(self, url: str) -> str:
        """Get file type from URL."""
        url_lower = url.lower()
        if url_lower.endswith('.pdf'):
            return 'pdf'
        elif url_lower.endswith(('.doc', '.docx')):
            return 'word'
        elif url_lower.endswith(('.xls', '.xlsx')):
            return 'excel'
        elif url_lower.endswith('.zip'):
            return 'zip'
        return 'unknown'
    
    def _extract_deadline(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract deadline information from page text.
        
        Args:
            text: Page text content
            
        Returns:
            Dictionary with deadline info or None
        """
        if not text:
            return None
        
        # Common date patterns
        date_patterns = [
            # 2026年1月31日
            r'(\d{4})年(\d{1,2})月(\d{1,2})日',
            # 令和8年1月31日
            r'令和(\d{1,2})年(\d{1,2})月(\d{1,2})日',
            # 2026/1/31 or 2026-01-31
            r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})',
        ]
        
        deadlines = []
        
        for keyword in self.DEADLINE_KEYWORDS:
            # Find keyword position
            keyword_pos = text.lower().find(keyword.lower())
            if keyword_pos == -1:
                continue
            
            # Look for dates near the keyword (within 100 chars)
            search_area = text[max(0, keyword_pos-50):keyword_pos+150]
            
            for pattern in date_patterns:
                matches = re.findall(pattern, search_area)
                for match in matches:
                    if len(match) == 3:
                        year, month, day = match
                        # Handle Reiwa year conversion
                        if int(year) < 100:  # Likely Reiwa or other era
                            year = str(2018 + int(year))  # Convert Reiwa to Western
                        
                        deadlines.append({
                            'date': f"{year}-{month.zfill(2)}-{day.zfill(2)}",
                            'context': search_area.strip()[:100],
                            'keyword': keyword
                        })
        
        if deadlines:
            # Return the first (most likely) deadline
            return deadlines[0]
        
        return None
    
    async def verify_grant_page(self, url: str, grant_name: str) -> Dict[str, Any]:
        """
        Verify if a URL is the correct official grant page.
        
        Args:
            url: URL to verify
            grant_name: Expected grant name
            
        Returns:
            Verification result with confidence score
        """
        from src.tools.site_explorer import SiteExplorer
        
        result = {
            'url': url,
            'is_valid': False,
            'confidence': 0,
            'reasons': [],
            'title': None
        }
        
        async with SiteExplorer(headless=True) as explorer:
            page = await explorer.access_page(url)
            if not page:
                result['reasons'].append('ページにアクセスできません')
                return result
            
            try:
                # Get page info
                page_info = await explorer.get_page_info(page)
                title = page_info.get('title', '')
                result['title'] = title
                result['url'] = page_info.get('url', url)
                
                # Get page content
                page_text = await explorer.find_text_content(page)
                combined = (title + ' ' + page_text[:2000]).lower()
                
                # Check for grant keywords
                grant_keyword_count = 0
                for keyword in self.GRANT_PAGE_KEYWORDS:
                    if keyword.lower() in combined:
                        grant_keyword_count += 1
                
                if grant_keyword_count >= 2:
                    result['confidence'] += 30
                    result['reasons'].append(f'助成金関連キーワードを{grant_keyword_count}個検出')
                
                # Check for grant name match
                grant_name_parts = grant_name.split()[:4]
                match_count = 0
                for part in grant_name_parts:
                    if len(part) >= 2 and part.lower() in combined:
                        match_count += 1
                
                if match_count >= len(grant_name_parts) // 2:
                    result['confidence'] += 40
                    result['reasons'].append('助成金名と一致')
                
                # Check domain trustworthiness
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                
                if domain.endswith('.go.jp'):
                    result['confidence'] += 20
                    result['reasons'].append('政府ドメイン')
                elif domain.endswith('.or.jp'):
                    result['confidence'] += 15
                    result['reasons'].append('財団ドメイン')
                elif domain.endswith('.lg.jp'):
                    result['confidence'] += 15
                    result['reasons'].append('地方自治体ドメイン')
                
                # Check for error page indicators
                error_indicators = ['404', 'not found', 'エラー', '見つかりません']
                for indicator in error_indicators:
                    if indicator in title.lower():
                        result['confidence'] = 0
                        result['reasons'] = ['エラーページ']
                        break
                
                result['is_valid'] = result['confidence'] >= 50
                
                await page.close()
                
            except Exception as e:
                result['reasons'].append(f'検証エラー: {str(e)}')
        
        return result
    
    # ====== SGNA Phase 5: Error Handling Methods ======
    
    async def dismiss_popups(self, page: Any, max_attempts: int = 3) -> bool:
        """
        Attempt to dismiss popups/overlays that may block content (SGNA Phase 5).
        
        Args:
            page: Playwright page object
            max_attempts: Maximum dismiss attempts
            
        Returns:
            True if any popup was dismissed
        """
        dismissed = False
        
        for attempt in range(max_attempts):
            try:
                # Find and click close buttons using keywords
                for keyword in self.POPUP_CLOSE_KEYWORDS:
                    try:
                        # Try to find button/link with matching text
                        selector = f'button:has-text("{keyword}"), a:has-text("{keyword}"), [aria-label*="{keyword}"]'
                        element = await page.query_selector(selector)
                        
                        if element:
                            await element.click()
                            self.logger.info(f"[GRANT_SCRAPER] Dismissed popup with '{keyword}'")
                            dismissed = True
                            await page.wait_for_timeout(500)  # Wait for animation
                            break
                    except:
                        continue
                
                # Try clicking overlay backgrounds to dismiss
                try:
                    overlay = await page.query_selector('.modal-backdrop, .overlay, [class*="modal-bg"]')
                    if overlay:
                        await overlay.click()
                        dismissed = True
                except:
                    pass
                    
            except Exception as e:
                self.logger.warning(f"[GRANT_SCRAPER] Popup dismiss attempt {attempt + 1} failed: {e}")
        
        return dismissed
    
    async def take_debug_screenshot(self, page: Any, name: str = "debug") -> Optional[str]:
        """
        Take a debug screenshot for error analysis (SGNA Phase 5).
        
        Args:
            page: Playwright page object
            name: Name for the screenshot
            
        Returns:
            Path to screenshot or None
        """
        import os
        from datetime import datetime
        
        try:
            # Ensure debug directory exists
            os.makedirs(self.DEBUG_SCREENSHOT_DIR, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.DEBUG_SCREENSHOT_DIR, f"{name}_{timestamp}.png")
            
            await page.screenshot(path=path, full_page=True)
            self.logger.info(f"[GRANT_SCRAPER] Debug screenshot saved: {path}")
            return path
            
        except Exception as e:
            self.logger.error(f"[GRANT_SCRAPER] Failed to take debug screenshot: {e}")
            return None
    
    async def try_alternative_links(
        self, 
        page: Any, 
        explorer: Any,
        failed_url: str,
        alternative_links: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        Try alternative URLs when a link fails (SGNA Phase 5 error recovery).
        
        Args:
            page: Current page (will be closed)
            explorer: SiteExplorer instance
            failed_url: URL that failed
            alternative_links: List of alternative links to try
            
        Returns:
            Working URL or None
        """
        self.logger.info(f"[GRANT_SCRAPER] Trying {len(alternative_links)} alternative links")
        
        for link in alternative_links[:5]:  # Try up to 5 alternatives
            alt_url = link.get('href')
            if not alt_url or alt_url == failed_url:
                continue
            
            try:
                alt_page = await explorer.access_page(alt_url)
                if alt_page:
                    info = await explorer.get_page_info(alt_page)
                    title = info.get('title', '').lower()
                    
                    # Check if it's not an error page
                    error_indicators = ['404', 'not found', 'エラー']
                    is_error = any(ind in title for ind in error_indicators)
                    
                    if not is_error:
                        self.logger.info(f"[GRANT_SCRAPER] Found working alternative: {alt_url}")
                        await alt_page.close()
                        return alt_url
                    
                    await alt_page.close()
                    
            except Exception as e:
                self.logger.warning(f"[GRANT_SCRAPER] Alternative link failed: {alt_url}: {e}")
                continue
        
        return None
    
    # ====== Visual Reasoning Fallback Methods ======
    
    async def find_files_visually(
        self, 
        page: Any,
        explorer: Any = None
    ) -> List[Dict[str, Any]]:
        """
        Find download files using visual analysis when DOM-based search fails.
        Fallback method using Gemini 3.0 multimodal capabilities.
        
        Args:
            page: Playwright page object
            explorer: SiteExplorer instance (optional)
            
        Returns:
            List of found download elements
        """
        if not self.visual_analyzer:
            self.logger.warning("[GRANT_SCRAPER] Visual analyzer not available (no Gemini client)")
            return []
        
        self.logger.info("[GRANT_SCRAPER] Attempting visual analysis fallback for file detection")
        
        try:
            elements = await self.visual_analyzer.find_download_elements_visually(page, explorer)
            
            if elements:
                self.logger.info(f"[GRANT_SCRAPER] Visual analysis found {len(elements)} download elements")
            else:
                self.logger.info("[GRANT_SCRAPER] Visual analysis did not find any download elements")
            
            return elements
            
        except Exception as e:
            self.logger.error(f"[GRANT_SCRAPER] Visual analysis failed: {e}")
            return []
    
    async def verify_page_visually(self, page: Any) -> Dict[str, Any]:
        """
        Verify page type using visual analysis when DOM-based checks are unreliable.
        Fallback method using Gemini 3.0 multimodal capabilities.
        
        Args:
            page: Playwright page object
            
        Returns:
            Page verification result with type and confidence
        """
        if not self.visual_analyzer:
            self.logger.warning("[GRANT_SCRAPER] Visual analyzer not available (no Gemini client)")
            return {"success": False, "reason": "Visual analyzer not configured"}
        
        self.logger.info("[GRANT_SCRAPER] Attempting visual page verification")
        
        try:
            result = await self.visual_analyzer.verify_page_type(page)
            
            if result.get("success"):
                page_type = result.get("ページ種類", "Unknown")
                confidence = result.get("信頼度", "Unknown")
                self.logger.info(f"[GRANT_SCRAPER] Visual verification: {page_type} (confidence: {confidence})")
            
            return result
            
        except Exception as e:
            self.logger.error(f"[GRANT_SCRAPER] Visual page verification failed: {e}")
            return {"success": False, "reason": str(e)}
    
    async def analyze_with_visual_fallback(
        self,
        page: Any,
        explorer: Any,
        dom_files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Analyze page with visual fallback if DOM-based analysis finds few files.
        Combines DOM and visual analysis for best results.
        
        Args:
            page: Playwright page object
            explorer: SiteExplorer instance
            dom_files: Files found by DOM-based analysis
            
        Returns:
            Combined list of found files (DOM + visual)
        """
        # If DOM analysis found sufficient files, return as-is
        if len(dom_files) >= 3:
            self.logger.info(f"[GRANT_SCRAPER] DOM analysis found {len(dom_files)} files, skipping visual fallback")
            return dom_files
        
        # Try visual fallback if DOM found few or no files
        if self.visual_analyzer:
            self.logger.info("[GRANT_SCRAPER] DOM analysis found few files, trying visual fallback")
            
            visual_elements = await self.find_files_visually(page, explorer)
            
            # If visual found elements with coordinates, attempt to extract URLs
            for element in visual_elements:
                if element.get("coordinates"):
                    try:
                        # Click at coordinates to potentially reveal download link
                        coords = element["coordinates"]
                        self.logger.info(f"[GRANT_SCRAPER] Visual element found at ({coords['x']}, {coords['y']})")
                        
                        # Note: Actual coordinate clicking would be:
                        # await page.mouse.click(coords['x'], coords['y'])
                        # For safety, we just log the finding for now
                        
                    except Exception as e:
                        self.logger.warning(f"[GRANT_SCRAPER] Failed to process visual element: {e}")
            
            # Merge results (DOM files + visual findings as metadata)
            if visual_elements:
                dom_files.append({
                    "type": "visual_analysis",
                    "text": "ビジュアル分析で検出された要素あり",
                    "elements": visual_elements,
                    "note": "座標クリックによる取得が必要"
                })
        
        return dom_files
    
    # ====== 障害検知メソッド ======
    
    # 障害パターン定義（タイトルに含まれるキーワード -> 障害タイプ）
    OBSTACLE_PATTERNS = {
        'sign in': 'ログイン壁',
        'login': 'ログイン壁',
        'ログイン': 'ログイン壁',
        'サインイン': 'ログイン壁',
        '404': 'ページ未発見',
        'not found': 'ページ未発見',
        '見つかりません': 'ページ未発見',
        'ページが見つかりません': 'ページ未発見',
        'access denied': 'アクセス拒否',
        'forbidden': 'アクセス拒否',
        'アクセスが拒否': 'アクセス拒否',
        '403': 'アクセス拒否',
        'error': 'エラーページ',
        'エラー': 'エラーページ',
    }
    
    def _detect_obstacle(self, title: str) -> str:
        """
        ページタイトルから障害パターンを検出する。
        
        Args:
            title: ページタイトル
            
        Returns:
            障害タイプ（例: "ログイン壁", "ページ未発見"）、検出されなければ空文字列
        """
        if not title:
            return ""
        
        title_lower = title.lower()
        
        for pattern, obstacle_type in self.OBSTACLE_PATTERNS.items():
            if pattern.lower() in title_lower:
                return obstacle_type
        
        return ""
