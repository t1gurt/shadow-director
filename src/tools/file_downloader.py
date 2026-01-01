import os
import logging
import requests
from typing import Optional, Tuple
from pathlib import Path
import tempfile

class FileDownloader:
    """
    Helper class to download grant application format files from URLs.
    Supports PDF, Word, Excel, and other common file types.
    """
    
    # Discord file upload limit is 25MB (8MB for free servers, but we use 25MB as safer limit)
    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB in bytes
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.zip': 'application/zip',
        '.txt': 'text/plain',
    }
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize FileDownloader.
        
        Args:
            storage_path: Optional custom storage path. If None, uses temp directory.
        """
        self.logger = logging.getLogger(__name__)
        
        # Determine storage path
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            # Use system temp directory
            self.storage_path = Path(tempfile.gettempdir()) / "shadow_director_downloads"
        
        # Create storage directory if it doesn't exist
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"FileDownloader initialized with storage: {self.storage_path}")
    
    def validate_url(self, url: str) -> Tuple[bool, str]:
        """
        Validate URL using HTTP HEAD request before downloading.
        
        Args:
            url: URL to validate
            
        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if URL is accessible and valid, False otherwise
            - error_message: Error description if invalid, empty string if valid
        """
        try:
            # Basic URL format validation
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return (False, "無効なURL形式です")
            
            # Set headers to mimic a browser request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Send HEAD request to check without downloading
            self.logger.info(f"[VALIDATE] Checking URL: {url}")
            response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
            
            # Check status code
            if response.status_code == 404:
                return (False, f"URLが見つかりません (404)")
            elif response.status_code == 403:
                return (False, f"アクセスが拒否されました (403)")
            elif response.status_code >= 400:
                return (False, f"エラー: HTTPステータスコード {response.status_code}")
            
            # Check content type if available
            content_type = response.headers.get('content-type', '').lower()
            
            # If content-type is text/html, it might not be a file
            if 'text/html' in content_type:
                self.logger.warning(f"[VALIDATE] URL appears to be HTML page, not a file: {url}")
                # Don't reject entirely, some sites serve files with HTML content-type
            
            # Check content length if available
            content_length = response.headers.get('content-length')
            if content_length:
                size_mb = int(content_length) / 1024 / 1024
                if int(content_length) > self.MAX_FILE_SIZE:
                    return (False, f"ファイルが大きすぎます ({size_mb:.1f}MB > 25MB)")
            
            self.logger.info(f"[VALIDATE] URL is valid: {url}")
            return (True, "")
            
        except requests.exceptions.Timeout:
            return (False, "タイムアウトしました")
        except requests.exceptions.ConnectionError:
            return (False, "接続できませんでした")
        except requests.exceptions.RequestException as e:
            return (False, f"リクエストエラー: {str(e)}")
        except Exception as e:
            self.logger.error(f"[VALIDATE] Unexpected error: {e}", exc_info=True)
            return (False, f"予期しないエラー: {str(e)}")
    
    def download_file(self, url: str, user_id: str) -> Optional[Tuple[str, str]]:
        """
        Download a file from URL and save to storage.
        
        Args:
            url: URL of the file to download
            user_id: User ID for organizing files
            
        Returns:
            Tuple of (file_path, filename) if successful, None otherwise
        """
        try:
            self.logger.info(f"[DOWNLOAD] Starting download: {url}")
            
            # Pre-validate URL before attempting download
            is_valid, error_msg = self.validate_url(url)
            if not is_valid:
                self.logger.warning(f"[DOWNLOAD] URL validation failed: {error_msg}")
                return None
            
            # Set headers to mimic a browser request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Stream the request to check size before downloading
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            # Check content length
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > self.MAX_FILE_SIZE:
                self.logger.warning(f"[DOWNLOAD] File too large: {content_length} bytes > {self.MAX_FILE_SIZE} bytes")
                return None
            
            # Try to determine filename from Content-Disposition header or URL
            filename = self._extract_filename(response, url)
            
            # Validate file extension
            file_ext = Path(filename).suffix.lower()
            if file_ext not in self.SUPPORTED_EXTENSIONS:
                self.logger.warning(f"[DOWNLOAD] Unsupported file type: {file_ext}")
                return None
            
            # Create user-specific directory
            user_dir = self.storage_path / user_id
            user_dir.mkdir(parents=True, exist_ok=True)
            
            # Save file
            file_path = user_dir / filename
            
            # Download file in chunks
            total_size = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
                        
                        # Check size limit during download
                        if total_size > self.MAX_FILE_SIZE:
                            self.logger.warning(f"[DOWNLOAD] File size exceeded during download: {total_size} bytes")
                            # Clean up partial file
                            file_path.unlink(missing_ok=True)
                            return None
            
            self.logger.info(f"[DOWNLOAD] Successfully downloaded: {filename} ({total_size} bytes)")
            return (str(file_path), filename)
            
        except requests.exceptions.Timeout:
            self.logger.error(f"[DOWNLOAD] Timeout downloading: {url}")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"[DOWNLOAD] Request failed: {e}")
            return None
        except Exception as e:
            self.logger.error(f"[DOWNLOAD] Unexpected error: {e}", exc_info=True)
            return None
    
    def _extract_filename(self, response: requests.Response, url: str) -> str:
        """
        Extract filename from response headers or URL.
        
        Args:
            response: HTTP response object
            url: Original URL
            
        Returns:
            Extracted or generated filename
        """
        # Try Content-Disposition header first
        content_disposition = response.headers.get('content-disposition')
        if content_disposition:
            import re
            filename_match = re.findall(r'filename="?([^"]+)"?', content_disposition)
            if filename_match:
                return filename_match[0]
        
        # Try to extract from URL
        from urllib.parse import urlparse, unquote
        parsed_url = urlparse(url)
        url_filename = Path(unquote(parsed_url.path)).name
        
        if url_filename and '.' in url_filename:
            return url_filename
        
        # Generate filename based on content type
        content_type = response.headers.get('content-type', '')
        extension = '.pdf'  # Default to PDF
        
        for ext, mime_type in self.SUPPORTED_EXTENSIONS.items():
            if mime_type in content_type:
                extension = ext
                break
        
        return f"application_format{extension}"
    
    def cleanup_user_files(self, user_id: str) -> None:
        """
        Clean up downloaded files for a specific user.
        
        Args:
            user_id: User ID
        """
        user_dir = self.storage_path / user_id
        if user_dir.exists():
            import shutil
            shutil.rmtree(user_dir)
            self.logger.info(f"[CLEANUP] Cleaned up files for user: {user_id}")
    
    def get_file_info(self, file_path: str) -> Optional[dict]:
        """
        Get information about a downloaded file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with file information or None if file doesn't exist
        """
        path = Path(file_path)
        if not path.exists():
            return None
        
        return {
            'name': path.name,
            'size': path.stat().st_size,
            'extension': path.suffix.lower(),
            'path': str(path)
        }

    def find_files_in_page(self, page_url: str) -> list[str]:
        """
        Scrapes a webpage to find URLs of supported file types.
        
        Args:
            page_url: The URL of the webpage to scrape
            
        Returns:
            List of found file URLs (absolute URLs)
        """
        found_urls = set()
        
        try:
            self.logger.info(f"[FINDER] Scraping page for files: {page_url}")
            
            # Fetch page content
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(page_url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                self.logger.warning(f"[FINDER] Failed to fetch page: {response.status_code}")
                return []
                
            content = response.text
            
            # Simple regex to find href links with supported extensions
            # Matches href="val" or href='val'
            import re
            from urllib.parse import urljoin
            
            # Extensions regex pattern
            ext_pattern = '|'.join([re.escape(ext) for ext in self.SUPPORTED_EXTENSIONS.keys()])
            # Pattern: href=["']([^"']+\.(?:pdf|doc|docx|xls|xlsx|zip))["']
            link_pattern = r'href=["\']([^"\']+\.(?:' + ext_pattern.replace('.', '') + r'))["\']'
            
            matches = re.findall(link_pattern, content, re.IGNORECASE)
            
            for match in matches:
                # Convert to absolute URL
                absolute_url = urljoin(page_url, match)
                found_urls.add(absolute_url)
                
            self.logger.info(f"[FINDER] Found {len(found_urls)} potential files in {page_url}")
            return list(found_urls)
            
        except Exception as e:
            self.logger.error(f"[FINDER] Error scraping page: {e}")
            return []
