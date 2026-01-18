"""
URL Analyzer - Fetch and analyze web page content for interview context.

This module uses SiteExplorer to access URLs and extract relevant information
for the interviewer agent to understand organization details from websites.
"""

import logging
from typing import List, Dict, Any, Optional
from src.tools.site_explorer import SiteExplorer


class URLAnalyzer:
    """
    Analyzes URLs to extract organization information for interviews.
    Uses SiteExplorer (Playwright-based) to access and parse web content.
    """
    
    def __init__(self, timeout: int = 15000):
        """
        Initialize URLAnalyzer.
        
        Args:
            timeout: Timeout for page access in milliseconds (default 15 seconds)
        """
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
    
    async def analyze_url(self, url: str) -> Dict[str, Any]:
        """
        Analyze a single URL and extract content information.
        
        Args:
            url: URL to analyze
            
        Returns:
            Dictionary with:
                - url: Original URL
                - title: Page title
                - description: Meta description
                - content_summary: Summarized body text (max 500 chars)
                - success: Whether analysis succeeded
                - error: Error message (only if failed)
        """
        self.logger.info(f"[URL_ANALYZER] Analyzing URL: {url}")
        
        site_explorer = None
        page = None
        
        try:
            # Start SiteExplorer
            site_explorer = SiteExplorer(headless=True, timeout=self.timeout)
            await site_explorer.start()
            
            # Access the page
            page = await site_explorer.access_page(url)
            if not page:
                return {
                    'url': url,
                    'success': False,
                    'error': 'ページにアクセスできませんでした'
                }
            
            # Get page info
            page_info = await site_explorer.get_page_info(page)
            
            if not page_info.get('accessible'):
                return {
                    'url': url,
                    'success': False,
                    'error': page_info.get('error', 'ページ情報を取得できませんでした')
                }
            
            # Extract body text content
            body_text = await site_explorer.find_text_content(page, 'body')
            
            # Summarize content (first 500 characters, remove extra whitespace)
            content_summary = ' '.join(body_text.split())[:500]
            if len(body_text) > 500:
                content_summary += '...'
            
            self.logger.info(f"[URL_ANALYZER] Successfully analyzed: {page_info.get('title', 'No title')}")
            
            return {
                'url': page_info.get('url', url),
                'title': page_info.get('title', ''),
                'description': page_info.get('meta_description', ''),
                'content_summary': content_summary,
                'success': True
            }
            
        except Exception as e:
            self.logger.error(f"[URL_ANALYZER] Error analyzing {url}: {e}")
            return {
                'url': url,
                'success': False,
                'error': str(e)
            }
            
        finally:
            # Clean up
            if page:
                try:
                    await page.close()
                except:
                    pass
            
            if site_explorer:
                try:
                    await site_explorer.close()
                except:
                    pass
    
    async def analyze_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Analyze multiple URLs.
        
        Args:
            urls: List of URLs to analyze
            
        Returns:
            List of analysis results (same format as analyze_url)
        """
        self.logger.info(f"[URL_ANALYZER] Analyzing {len(urls)} URLs")
        
        results = []
        for url in urls:
            result = await self.analyze_url(url)
            results.append(result)
        
        successful_count = sum(1 for r in results if r.get('success'))
        self.logger.info(f"[URL_ANALYZER] Completed: {successful_count}/{len(urls)} successful")
        
        return results
