import re
import requests
from typing import Optional, Tuple, List

class GrantValidator:
    """
    Validates and evaluates grant URLs and information.
    """

    def resolve_redirect_url(self, url: str, timeout: int = 5) -> str:
        """
        Resolves a redirect URL to get the final destination URL.
        Used to convert vertexaisearch.cloud.google.com/grounding-api-redirect URLs
        to their actual destinations.
        """
        if not url or 'vertexaisearch.cloud.google.com/grounding-api-redirect' not in url:
            return url
        
        try:
            # Use HEAD request with allow_redirects=False to get the redirect location
            response = requests.head(url, allow_redirects=False, timeout=timeout)
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_url = response.headers.get('Location', url)
                print(f"[DEBUG] Resolved redirect: {url[:50]}... -> {redirect_url}")
                return redirect_url
            
            # If no redirect, try GET with follow
            response = requests.get(url, allow_redirects=True, timeout=timeout)
            final_url = response.url
            if final_url != url:
                print(f"[DEBUG] Resolved via GET: {url[:50]}... -> {final_url}")
                return final_url
            
            return url
        except Exception as e:
            print(f"[DEBUG] Failed to resolve redirect URL: {e}")
            return url

    def validate_url_accessible(self, url: str, timeout: int = 10) -> Tuple[bool, str, Optional[str]]:
        """
        Validates if a URL is accessible and returns a valid page.
        
        Returns:
            Tuple of (is_valid, status_message, final_url)
        """
        if not url or url == 'N/A':
            return (False, "URLが指定されていません", None)
        
        # Clean URL - remove markdown formatting if present
        clean_url = url.strip()
        if clean_url.startswith('[') and '](' in clean_url:
            # Extract URL from markdown link format [text](url)
            match = re.search(r'\]\(([^)]+)\)', clean_url)
            if match:
                clean_url = match.group(1)
        
        # Remove angle brackets if present
        clean_url = clean_url.strip('<>')
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            response = requests.get(clean_url, timeout=timeout, headers=headers, allow_redirects=True)
            final_url = response.url
            print(f"[DEBUG] clean URL: {clean_url}")
            
            # Check status code
            if response.status_code == 200:
                # Additional check: make sure it's not an error page
                content_lower = response.text.lower()
                error_indicators = ['404', 'not found', 'page not found', 'ページが見つかりません', '存在しません']
                
                for indicator in error_indicators:
                    if indicator in content_lower[:2000]:  # Check first 2000 chars
                        return (False, f"ページは存在するがエラー内容を含む({indicator})", final_url)
                
                return (True, "アクセス可能", final_url)
            elif response.status_code in (301, 302, 303, 307, 308):
                return (True, f"リダイレクト({response.status_code})", final_url)
            elif response.status_code == 403:
                return (False, "アクセス禁止(403)", final_url)
            elif response.status_code == 404:
                return (False, "ページが見つかりません(404)", None)
            else:
                return (False, f"HTTPエラー({response.status_code})", final_url)
                
        except requests.exceptions.Timeout:
            return (False, "タイムアウト", None)
        except requests.exceptions.ConnectionError:
            return (False, "接続エラー", None)
        except requests.exceptions.TooManyRedirects:
            return (False, "リダイレクトが多すぎます", None)
        except Exception as e:
            return (False, f"エラー: {str(e)[:50]}", None)

    def extract_organization_name(self, grant_name: str) -> Optional[str]:
        """
        Extract organization name from grant name.
        Removes common organizational prefixes and extracts the proper organization name.
        """
        if not grant_name:
            return None
        
        # Step 1: Remove common organizational prefixes
        # Remove these to get to the actual organization name
        cleaned = grant_name
        prefixes_to_remove = [
            '公益財団法人', '一般財団法人', '公益社団法人', '一般社団法人',
            '社会福祉法人', '特定非営利活動法人', 'NPO法人',
            '独立行政法人', '地方独立行政法人', '国立研究開発法人'
        ]
        
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        
        # Step 2: Extract organization name with improved patterns
        # Use [^\s　]+ instead of .+? to avoid matching prefixes only
        patterns = [
            r'([^\s　]+財団)',  # XX財団
            r'([^\s　]+基金)',  # XX基金
            r'([^\s　]+協会)',  # XX協会
            r'([^\s　]+会)',    # XX会
            r'([^\s　]+団体)',  # XX団体
            r'([^\s　]+機構)',  # XX機構
            r'([^\s　]+法人)',  # XX法人
            r'([^\s　]+株式会社)',  # XX株式会社
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if match:
                org_name = match.group(1)
                # Validation: skip if org_name is too generic
                generic_terms = ['公益', '一般', '社会', '福祉', '特定', '非営利']
                if not any(org_name.startswith(term) for term in generic_terms):
                    return org_name
        
        # Step 3: Fallback - take first meaningful word
        parts = re.split(r'[\s　]+', cleaned)
        if parts and len(parts[0]) > 1:
            # Additional check: avoid returning single-character or very generic terms
            first_part = parts[0]
            if len(first_part) >= 2:
                return first_part
        
        return None

    def check_copyright_similarity(self, url: str, grant_name: str, timeout: int = 5) -> Tuple[int, str]:
        """
        Check if the page copyright matches the grant organization name.
        """
        org_name = self.extract_organization_name(grant_name)
        if not org_name:
            return (0, "")
        
        try:
            # Fetch page content
            response = requests.get(url, timeout=timeout, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if response.status_code != 200:
                return (0, "")
            
            html_content = response.text.lower()
            org_name_variants = [
                org_name.lower(),
                org_name.replace('財団', '').lower(),
                org_name.replace('法人', '').lower(),
            ]
            
            # Check copyright section
            copyright_patterns = [
                r'copyright[^<]*?' + '|'.join(re.escape(v) for v in org_name_variants),
                r'©[^<]*?' + '|'.join(re.escape(v) for v in org_name_variants),
                r'&copy;[^<]*?' + '|'.join(re.escape(v) for v in org_name_variants),
            ]
            
            for pattern in copyright_patterns:
                if re.search(pattern, html_content, re.IGNORECASE):
                    return (20, f"コピーライトに組織名'{org_name}'を確認")
            
            return (0, "")
            
        except Exception as e:
            print(f"[DEBUG] Copyright check failed: {e}")
            return (0, "")

    def evaluate_url_quality(self, url: str, grant_name: Optional[str] = None) -> Tuple[int, str]:
        """
        Evaluates the trustworthiness and quality of a URL for grant information.
        """
        if not url or url == 'N/A':
            return (0, "No URL provided")
        
        score = 50  # Base score
        reasons = []
        
        # Extract domain from URL
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            path = parsed.path.lower()
        except Exception:
            return (0, "Invalid URL format")
        
        # Check grant name similarity with domain
        if grant_name:
            org_name = self.extract_organization_name(grant_name)
            if org_name:
                # Normalize organization name for comparison
                org_normalized = org_name.lower().replace('財団', '').replace('法人', '').replace('株式会社', '')
                
                # Check if organization name appears in domain
                if org_normalized and org_normalized in domain:
                    score += 25
                    reasons.append(f"ドメインに組織名'{org_name}'を含む")
                
                # Check copyright similarity (bonus points)
                copyright_bonus, copyright_reason = self.check_copyright_similarity(url, grant_name)
                if copyright_bonus > 0:
                    score += copyright_bonus
                    reasons.append(copyright_reason)
        
        # High trust domains (official organizations)
        if domain.endswith('.or.jp'):  # Japanese foundation/NPO
            score += 30
            reasons.append("公式財団ドメイン(.or.jp)")
        elif domain.endswith('.go.jp'):  # Japanese government
            score += 30
            reasons.append("政府公式ドメイン(.go.jp)")
        elif domain.endswith('.ac.jp'):  # Japanese academic
            score += 25
            reasons.append("学術機関ドメイン(.ac.jp)")
        elif domain.endswith('.lg.jp'):  # Japanese local government
            score += 30
            reasons.append("地方自治体ドメイン(.lg.jp)")
        elif domain.endswith('.org'):  # Non-profit organization (international)
            score += 25
            reasons.append("非営利組織ドメイン(.org)")
        
        # Corporate domains (medium trust)
        elif domain.endswith('.co.jp'):
            score += 10
            reasons.append("企業ドメイン(.co.jp)")
        
        # Known aggregator/summary sites (low trust)
        aggregator_keywords = ['matome', 'navi', 'info', 'guide', 'portal', 
                              'まとめ', 'ナビ', 'ガイド', 'ポータル']
        for keyword in aggregator_keywords:
            if keyword in domain or keyword in path:
                score -= 20
                reasons.append(f"まとめサイトの可能性({keyword})")
                break
        
        # News/blog sites (lower priority)
        news_keywords = ['news', 'blog', 'note', 'fc2', 'ameblo', 'hatenablog']
        for keyword in news_keywords:
            if keyword in domain:
                score -= 15
                reasons.append(f"ニュース/ブログサイト({keyword})")
                break
        
        # Positive path indicators (official grant pages)
        positive_path_keywords = ['boshu', 'kobo', 'josei', 'grant', 'application', 
                                 '募集', '公募', '助成', '申請']
        for keyword in positive_path_keywords:
            if keyword in path:
                score += 10
                reasons.append(f"申請関連パス({keyword})")
                break
        
        # Cap score at 100
        score = min(100, max(0, score))
        
        reason_text = ", ".join(reasons) if reasons else "標準ドメイン"
        return (score, reason_text)
