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
    
    def __init__(self, site_explorer=None):
        """
        Initialize GrantPageScraper.
        
        Args:
            site_explorer: SiteExplorer instance (will be created if not provided)
        """
        self.site_explorer = site_explorer
        self.logger = logging.getLogger(__name__)
    
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
                explorer = SiteExplorer(headless=True)
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
            result['title'] = page_info.get('title')
            result['url'] = page_info.get('url', url)  # May have been redirected
            
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
    
    async def deep_search_format_files(self, start_url: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Deep search for format files by following links up to max_depth levels.
        
        Args:
            start_url: Starting URL
            max_depth: Maximum depth of link following
            
        Returns:
            List of found format file information
        """
        from src.tools.site_explorer import SiteExplorer
        
        found_files = []
        visited_urls = set()
        urls_to_visit = [(start_url, 0)]  # (url, depth)
        
        async with SiteExplorer(headless=True) as explorer:
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
                    
                    # Find format files
                    format_files = await self._find_format_files(all_links, page)
                    for f in format_files:
                        f['found_at'] = current_url
                        f['depth'] = depth
                    found_files.extend(format_files)
                    
                    # Queue related links for further exploration
                    if depth < max_depth:
                        related = self._filter_grant_related_links(all_links)
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
        
        for link in links:
            if not link.get('is_file'):
                continue
            
            href = link.get('href', '')
            text = link.get('text', '')
            
            # Score relevance
            score = 0
            
            # Check link text for format keywords
            text_lower = text.lower()
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
                grant_name_parts = grant_name.split()[:3]
                for part in grant_name_parts:
                    if len(part) >= 2 and part.lower() in combined:
                        score += 5
            
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
