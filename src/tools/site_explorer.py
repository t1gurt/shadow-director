"""
Site Explorer - Playwright-based browser automation for site exploration.

This module provides a base class for exploring websites using Playwright,
enabling DOM-based analysis and deep site navigation.
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse


class SiteExplorer:
    """
    Base class for Playwright-based site exploration.
    Provides methods for page access, DOM analysis, and link extraction.
    """
    
    # Supported file extensions for grant format files
    FILE_EXTENSIONS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip']
    
    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Initialize SiteExplorer.
        
        Args:
            headless: Whether to run browser in headless mode
            timeout: Default timeout for operations in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.context = None
        self.logger = logging.getLogger(__name__)
    
    async def __aenter__(self):
        """Async context manager entry - starts browser."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes browser."""
        await self.close()
    
    async def start(self):
        """Start Playwright browser."""
        try:
            from playwright.async_api import async_playwright
            
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 720}
            )
            self.logger.info("[SITE_EXPLORER] Browser started")
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Failed to start browser: {e}")
            raise
    
    async def close(self):
        """Close Playwright browser and cleanup."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, '_playwright') and self._playwright:
                await self._playwright.stop()
            self.logger.info("[SITE_EXPLORER] Browser closed")
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Error closing browser: {e}")
    
    def _is_government_site(self, url: str) -> bool:
        """Check if URL is a government/public site requiring rate limiting."""
        gov_domains = ['go.jp', 'lg.jp', 'or.jp', 'ac.jp']
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            return any(domain.endswith(d) for d in gov_domains)
        except:
            return False
    
    async def access_page(
        self, 
        url: str, 
        wait_for_load: bool = True,
        use_progressive_wait: bool = True
    ) -> Optional[Any]:
        """
        Access a webpage and return the page object.
        Implements SGNA model: Progressive Wait and Rate Limiting.
        
        Args:
            url: URL to access
            wait_for_load: Whether to wait for page load
            use_progressive_wait: Use progressive wait strategy (SGNA model)
            
        Returns:
            Playwright page object or None if failed
        """
        if not self.context:
            self.logger.error("[SITE_EXPLORER] Browser not started")
            return None
        
        try:
            # Rate Limiting for government/public sites (SGNA model)
            if self._is_government_site(url):
                self.logger.info(f"[SITE_EXPLORER] Rate limiting: 1s delay for gov site")
                await asyncio.sleep(1.0)
            
            page = await self.context.new_page()
            page.set_default_timeout(self.timeout)
            
            self.logger.info(f"[SITE_EXPLORER] Accessing: {url}")
            
            if wait_for_load:
                if use_progressive_wait:
                    # Progressive Wait Strategy (SGNA model)
                    # Step 1: Try networkidle for dynamic content
                    try:
                        await page.goto(url, wait_until='networkidle', timeout=self.timeout)
                        self.logger.info(f"[SITE_EXPLORER] Loaded with networkidle")
                    except Exception as wait_error:
                        # Step 2: Fall back to domcontentloaded if networkidle fails
                        self.logger.warning(f"[SITE_EXPLORER] networkidle failed, trying domcontentloaded")
                        try:
                            await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
                        except Exception as dom_error:
                            # Step 3: Last resort - basic load
                            self.logger.warning(f"[SITE_EXPLORER] domcontentloaded failed, using load")
                            await page.goto(url, wait_until='load', timeout=self.timeout)
                else:
                    await page.goto(url, wait_until='domcontentloaded')
            else:
                await page.goto(url)
            
            return page
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Failed to access {url}: {e}")
            return None
    
    async def get_page_info(self, page: Any) -> Dict[str, Any]:
        """
        Get basic information about a page.
        
        Args:
            page: Playwright page object
            
        Returns:
            Dictionary with page title, URL, and basic metadata
        """
        try:
            title = await page.title()
            url = page.url
            
            # Get meta description if available
            meta_desc = await page.evaluate('''
                () => {
                    const meta = document.querySelector('meta[name="description"]');
                    return meta ? meta.content : null;
                }
            ''')
            
            return {
                'title': title,
                'url': url,
                'meta_description': meta_desc,
                'accessible': True
            }
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Error getting page info: {e}")
            return {'accessible': False, 'error': str(e)}
    
    async def extract_links(self, page: Any, base_url: str = None) -> List[Dict[str, str]]:
        """
        Extract all links from the page.
        
        Args:
            page: Playwright page object
            base_url: Base URL for resolving relative links
            
        Returns:
            List of dictionaries with 'href', 'text', and 'is_file' keys
        """
        if not base_url:
            base_url = page.url
        
        try:
            links = await page.evaluate('''
                () => {
                    const anchors = document.querySelectorAll('a[href]');
                    return Array.from(anchors).map(a => ({
                        href: a.href,
                        text: a.innerText.trim().substring(0, 100)
                    }));
                }
            ''')
            
            result = []
            for link in links:
                href = link.get('href', '')
                if not href or href.startswith('javascript:') or href.startswith('#'):
                    continue
                
                # Resolve relative URLs
                absolute_url = urljoin(base_url, href)
                
                # Check if it's a file link
                parsed = urlparse(absolute_url)
                path_lower = parsed.path.lower()
                is_file = any(path_lower.endswith(ext) for ext in self.FILE_EXTENSIONS)
                
                result.append({
                    'href': absolute_url,
                    'text': link.get('text', ''),
                    'is_file': is_file
                })
            
            self.logger.info(f"[SITE_EXPLORER] Found {len(result)} links on page")
            return result
            
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Error extracting links: {e}")
            return []
    
    async def extract_file_links(self, page: Any) -> List[Dict[str, str]]:
        """
        Extract only file links (PDF, DOC, XLS, etc.) from the page.
        
        Args:
            page: Playwright page object
            
        Returns:
            List of file link dictionaries
        """
        all_links = await self.extract_links(page)
        return [link for link in all_links if link.get('is_file')]
    
    async def find_text_content(self, page: Any, selector: str = 'body') -> str:
        """
        Get text content of the page or a specific element.
        
        Args:
            page: Playwright page object
            selector: CSS selector for the element
            
        Returns:
            Text content of the element
        """
        try:
            element = await page.query_selector(selector)
            if element:
                return await element.inner_text()
            return ''
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Error getting text content: {e}")
            return ''
    
    async def check_page_accessible(self, url: str) -> Dict[str, Any]:
        """
        Check if a page is accessible and get basic info.
        
        Args:
            url: URL to check
            
        Returns:
            Dictionary with accessibility status and info
        """
        page = None
        try:
            page = await self.access_page(url)
            if not page:
                return {'accessible': False, 'reason': 'ページにアクセスできません'}
            
            info = await self.get_page_info(page)
            
            # Check for error indicators in title
            title_lower = info.get('title', '').lower()
            error_indicators = ['404', 'not found', 'エラー', '見つかりません', '存在しません']
            
            for indicator in error_indicators:
                if indicator in title_lower:
                    return {
                        'accessible': False,
                        'reason': f'エラーページ: {info.get("title")}',
                        'url': info.get('url')
                    }
            
            return {
                'accessible': True,
                'title': info.get('title'),
                'url': info.get('url'),
                'meta_description': info.get('meta_description')
            }
            
        except Exception as e:
            return {'accessible': False, 'reason': str(e)}
        finally:
            if page:
                await page.close()
    
    async def take_screenshot(self, page: Any, path: str) -> bool:
        """
        Take a screenshot of the current page.
        
        Args:
            page: Playwright page object
            path: Path to save the screenshot
            
        Returns:
            True if successful
        """
        try:
            await page.screenshot(path=path, full_page=True)
            self.logger.info(f"[SITE_EXPLORER] Screenshot saved: {path}")
            return True
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Failed to take screenshot: {e}")
            return False
    
    # ====== SGNA Phase 3: Accessibility Tree Methods ======
    
    async def extract_accessibility_tree(self, page: Any, max_depth: int = 5) -> Dict[str, Any]:
        """
        Extract accessibility tree from page for semantic analysis (SGNA model).
        This provides a structured view of the page content without relying on CSS selectors.
        
        Args:
            page: Playwright page object
            max_depth: Maximum depth of tree to extract
            
        Returns:
            Dictionary with semantic structure (headings, links, buttons)
        """
        try:
            # Extract semantic elements using JavaScript
            accessibility_data = await page.evaluate('''
                () => {
                    const result = {
                        headings: [],
                        links: [],
                        buttons: [],
                        forms: []
                    };
                    
                    // Extract all headings (H1-H6)
                    document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach((el, idx) => {
                        result.headings.push({
                            level: parseInt(el.tagName[1]),
                            text: el.innerText.trim().substring(0, 200),
                            index: idx
                        });
                    });
                    
                    // Extract links with context
                    document.querySelectorAll('a[href]').forEach((el, idx) => {
                        if (idx < 100) {  // Limit to 100 links
                            result.links.push({
                                text: el.innerText.trim().substring(0, 100),
                                href: el.href,
                                ariaLabel: el.getAttribute('aria-label') || '',
                                index: idx
                            });
                        }
                    });
                    
                    // Extract buttons
                    document.querySelectorAll('button, input[type="submit"], input[type="button"]').forEach((el, idx) => {
                        if (idx < 20) {
                            result.buttons.push({
                                text: el.innerText || el.value || '',
                                type: el.type || 'button',
                                index: idx
                            });
                        }
                    });
                    
                    return result;
                }
            ''')
            
            self.logger.info(f"[SITE_EXPLORER] Extracted accessibility tree: {len(accessibility_data.get('headings', []))} headings, {len(accessibility_data.get('links', []))} links")
            return accessibility_data
            
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Error extracting accessibility tree: {e}")
            return {'headings': [], 'links': [], 'buttons': [], 'forms': []}
    
    async def find_heading_sections(self, page: Any) -> List[Dict[str, Any]]:
        """
        Find and structure page sections by headings (SGNA model).
        Useful for navigating complex government pages with hierarchical structure.
        
        Args:
            page: Playwright page object
            
        Returns:
            List of heading sections with their child content
        """
        try:
            accessibility = await self.extract_accessibility_tree(page)
            headings = accessibility.get('headings', [])
            
            # Build hierarchical structure
            sections = []
            current_section = None
            
            for heading in headings:
                section = {
                    'level': heading['level'],
                    'title': heading['text'],
                    'index': heading['index']
                }
                sections.append(section)
            
            return sections
            
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Error finding heading sections: {e}")
            return []
    
    async def find_links_by_text(
        self, 
        page: Any, 
        keywords: List[str],
        case_sensitive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Find links by text content matching keywords (SGNA model semantic search).
        More robust than CSS selector-based search.
        
        Args:
            page: Playwright page object
            keywords: List of keywords to search for
            case_sensitive: Whether to match case
            
        Returns:
            List of matching links
        """
        try:
            accessibility = await self.extract_accessibility_tree(page)
            links = accessibility.get('links', [])
            
            matching_links = []
            for link in links:
                link_text = link.get('text', '')
                aria_label = link.get('ariaLabel', '')
                combined_text = f"{link_text} {aria_label}"
                
                if not case_sensitive:
                    combined_text = combined_text.lower()
                    search_keywords = [k.lower() for k in keywords]
                else:
                    search_keywords = keywords
                
                # Check if any keyword matches
                for keyword in search_keywords:
                    if keyword in combined_text:
                        matching_links.append({
                            **link,
                            'matched_keyword': keyword
                        })
                        break
            
            self.logger.info(f"[SITE_EXPLORER] Found {len(matching_links)} links matching keywords")
            return matching_links
            
        except Exception as e:
            self.logger.error(f"[SITE_EXPLORER] Error finding links by text: {e}")
            return []


def run_sync(coro):
    """
    Utility to run async code synchronously.
    Creates a new event loop if needed.
    """
    try:
        loop = asyncio.get_running_loop()
        # If there's a running loop, we need to use a different approach
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop, we can use asyncio.run
        return asyncio.run(coro)
