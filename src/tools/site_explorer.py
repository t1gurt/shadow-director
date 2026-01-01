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
    
    async def access_page(self, url: str, wait_for_load: bool = True) -> Optional[Any]:
        """
        Access a webpage and return the page object.
        
        Args:
            url: URL to access
            wait_for_load: Whether to wait for page load
            
        Returns:
            Playwright page object or None if failed
        """
        if not self.context:
            self.logger.error("[SITE_EXPLORER] Browser not started")
            return None
        
        try:
            page = await self.context.new_page()
            page.set_default_timeout(self.timeout)
            
            self.logger.info(f"[SITE_EXPLORER] Accessing: {url}")
            
            if wait_for_load:
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
