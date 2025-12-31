from typing import Dict, Any, List, Optional, Tuple
import yaml
import os
import re
import requests
from google import genai
from google.genai.types import HttpOptions, GenerateContentConfig
from src.tools.search_tool import SearchTool
from src.memory.profile_manager import ProfileManager


def resolve_redirect_url(url: str, timeout: int = 5) -> str:
    """
    Resolves a redirect URL to get the final destination URL.
    Used to convert vertexaisearch.cloud.google.com/grounding-api-redirect URLs
    to their actual destinations.
    
    Args:
        url: The URL to resolve
        timeout: Request timeout in seconds
        
    Returns:
        The final destination URL, or the original URL if resolution fails
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


def extract_organization_name(grant_name: str) -> Optional[str]:
    """
    Extract organization name from grant name.
    
    Args:
        grant_name: Full grant name (e.g., "トヨタ財団 国際助成プログラム")
        
    Returns:
        Organization name (e.g., "トヨタ財団") or None
    """
    if not grant_name:
        return None
    
    # Common patterns for organization names
    patterns = [
        r'(.+?財団)',  # XX財団
        r'(.+?基金)',  # XX基金
        r'(.+?協会)',  # XX協会
        r'(.+?会)',    # XX会
        r'(.+?団体)',  # XX団体
        r'(.+?機構)',  # XX機構
        r'(.+?法人)',  # XX法人
        r'([^\s]+株式会社)',  # XX株式会社
    ]
    
    for pattern in patterns:
        match = re.search(pattern, grant_name)
        if match:
            return match.group(1)
    
    # Fallback: take first word/phrase before space or special character
    parts = re.split(r'[\s　]+', grant_name)
    if parts:
        return parts[0]
    
    return None


def check_copyright_similarity(url: str, grant_name: str, timeout: int = 5) -> Tuple[int, str]:
    """
    Check if the page copyright matches the grant organization name.
    
    Args:
        url: URL to check
        grant_name: Grant name to match against
        timeout: Request timeout
        
    Returns:
        Tuple of (bonus_score, reason)
    """
    org_name = extract_organization_name(grant_name)
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


def evaluate_url_quality(url: str, grant_name: Optional[str] = None) -> Tuple[int, str]:
    """
    Evaluates the trustworthiness and quality of a URL for grant information.
    Prioritizes official organization pages over aggregator/news sites.
    
    Args:
        url: The URL to evaluate
        grant_name: Optional grant name to check similarity with URL/copyright
        
    Returns:
        Tuple of (score, reason)
        - score: Quality score (higher is better, 0-100 scale)
        - reason: Explanation of the score
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
        org_name = extract_organization_name(grant_name)
        if org_name:
            # Normalize organization name for comparison
            org_normalized = org_name.lower().replace('財団', '').replace('法人', '').replace('株式会社', '')
            
            # Check if organization name appears in domain
            if org_normalized and org_normalized in domain:
                score += 25
                reasons.append(f"ドメインに組織名'{org_name}'を含む")
            
            # Check copyright similarity (bonus points)
            copyright_bonus, copyright_reason = check_copyright_similarity(url, grant_name)
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


class ObserverAgent:
    def __init__(self):
        self.config = self._load_config()
        self.system_prompt = self.config.get("system_prompts", {}).get("observer", "")
        
        # Initialize Google Gen AI Client
        project_id = self.config.get("model_config", {}).get("project_id")
        if not project_id:
             # Fallback if config issues, though should ensure config exists
             pass

        location = self.config.get("model_config", {}).get("location", "us-central1")
        
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        
        try:
            self.client = genai.Client(http_options=HttpOptions(api_version="v1beta1"))
        except Exception as e:
            print(f"Failed to init GenAI client: {e}")
            self.client = None
            
        self.model_name = self.config.get("model_config", {}).get("observer_model")
        if not self.model_name:
            raise ValueError("observer_model not found in config")
        self.search_tool = SearchTool()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def _generate_queries(self, profile: str) -> List[str]:
        """
        Generates optimized search queries based on the Soul Profile.
        """
        # Get prompt template from config
        prompt_template = self.config.get("system_prompts", {}).get("observer_query_generator", "")
        if prompt_template:
            prompt = prompt_template.format(profile=profile)
        else:
            # Fallback to inline prompt if template not found
            prompt = f"""
現在のSoul Profile:
{profile}

タスク:
このNPOに最適な資金調達機会（助成金、CSR）を見つけるための3つの異なる検索クエリを生成してください。
ミッション、対象課題、独自の強みに焦点を当ててください。
クエリのみを出力してください。1行に1つのクエリ。
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            queries = [q.strip() for q in response.text.strip().split('\n') if q.strip()]
            return queries[:3] # Limit to top 3
        except Exception as e:
            print(f"Error generating queries: {e}")
            return [f"NPO助成金 {profile[:50]}..."] # Fallback
    
    def _parse_opportunities(self, text: str) -> List[Dict]:
        """
        Parse structured opportunity data from Observer response.
        Expected format:
        ### 機会 N: [助成金名]
        - **URL**: [URL]
        - **金額**: [金額]
        - **共鳴スコア**: [数値]
        - **共鳴理由**: [理由]
        
        Returns:
            List of opportunity dictionaries
        """
        opportunities = []
        
        # Split by ### 機会 pattern
        sections = re.split(r'###\s*機会\s*\d+:', text)
        
        for section in sections[1:]:  # Skip first empty section
            try:
                # Extract title (first line)
                lines = section.strip().split('\n')
                title = lines[0].strip() if lines else "不明"
                
                # Extract URL
                url_match = re.search(r'\*\*URL\*\*:\s*(.+)', section)
                url = url_match.group(1).strip() if url_match else "N/A"
                
                # Extract amount
                amount_match = re.search(r'\*\*金額\*\*:\s*(.+)', section)
                amount = amount_match.group(1).strip() if amount_match else "N/A"
                
                # Extract resonance score
                score_match = re.search(r'\*\*共鳴スコア\*\*:\s*(\d+)', section)
                score = int(score_match.group(1)) if score_match else 0
                
                # Extract reason
                reason_match = re.search(r'\*\*共鳴理由\*\*:\s*(.+)', section)
                reason = reason_match.group(1).strip() if reason_match else "理由不明"
                
                opportunities.append({
                    "title": title,
                    "url": url,
                    "amount": amount,
                    "resonance_score": score,
                    "reason": reason
                })
                
                print(f"[DEBUG] Parsed opportunity: {title} (Score: {score})")
            except Exception as e:
                print(f"[ERROR] Failed to parse opportunity section: {e}")
                continue
        
        return opportunities

    def _find_official_page(self, grant_name: str, current_date: str) -> Dict:
        """
        Step 2: Searches for the official grant page and verifies the application deadline.
        
        Args:
            grant_name: Name of the grant to search for
            current_date: Current date string for deadline comparison
            
        Returns:
            Dictionary with official URL, deadline, and verification status
        """
        import logging
        logging.info(f"[OBSERVER Step2] Finding official page for: {grant_name}")
        
        result = {
            'official_url': 'N/A',
            'domain': '',
            'deadline_start': '',
            'deadline_end': '',
            'status': '不明',  # 募集中/募集終了/今後募集予定/不明
            'is_valid': False,  # True if currently open or future
            'confidence': '低',
            'confidence_reason': ''
        }
        
        # Get prompt template
        prompt_template = self.config.get("system_prompts", {}).get("observer_find_official_page", "")
        if not prompt_template:
            logging.warning("[OBSERVER Step2] Prompt template not found")
            return result
        
        full_prompt = prompt_template.format(
            grant_name=grant_name,
            current_date=current_date
        )
        
        try:
            # Use Google Search for grounding
            tool_config = self.search_tool.get_tool_config()
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=GenerateContentConfig(
                    tools=[tool_config],
                    temperature=0.2  # Low temperature for more accurate results
                )
            )
            
            response_text = response.text
            logging.info(f"[OBSERVER Step2] Response: {response_text[:200]}...")
            
            # Parse response
            url_match = re.search(r'\*\*公式URL\*\*:\s*(.+)', response_text)
            if url_match:
                url = url_match.group(1).strip()
                # Resolve redirect if needed
                result['official_url'] = resolve_redirect_url(url)
            
            domain_match = re.search(r'\*\*ドメイン\*\*:\s*(.+)', response_text)
            if domain_match:
                result['domain'] = domain_match.group(1).strip()
            
            start_match = re.search(r'\*\*募集開始日\*\*:\s*(.+)', response_text)
            if start_match:
                result['deadline_start'] = start_match.group(1).strip()
            
            end_match = re.search(r'\*\*募集終了日\*\*:\s*(.+)', response_text)
            if end_match:
                result['deadline_end'] = end_match.group(1).strip()
            
            status_match = re.search(r'\*\*募集状況\*\*:\s*(.+)', response_text)
            if status_match:
                status = status_match.group(1).strip()
                result['status'] = status
                # Determine if valid (currently open or future)
                if '募集中' in status or '今後' in status or '予定' in status:
                    result['is_valid'] = True
                elif '終了' in status or '締切' in status:
                    result['is_valid'] = False
            
            confidence_match = re.search(r'\*\*信頼度\*\*:\s*(.+)', response_text)
            if confidence_match:
                result['confidence'] = confidence_match.group(1).strip()
            
            reason_match = re.search(r'\*\*信頼度理由\*\*:\s*(.+)', response_text)
            if reason_match:
                result['confidence_reason'] = reason_match.group(1).strip()
            
            # Evaluate URL quality with grant name
            if result['official_url'] != 'N/A':
                quality_score, quality_reason = evaluate_url_quality(result['official_url'], grant_name)
                result['url_quality_score'] = quality_score
                result['url_quality_reason'] = quality_reason
                
                # If URL quality is low, mark as invalid
                if quality_score < 50:
                    logging.warning(f"[OBSERVER Step2] Low quality URL (score {quality_score}): {result['official_url']}")
                    result['is_valid'] = False
            
            logging.info(f"[OBSERVER Step2] Result for '{grant_name}': URL={result['official_url'][:50]}..., Status={result['status']}, Valid={result['is_valid']}")
            
        except Exception as e:
            logging.error(f"[OBSERVER Step2] Error finding official page: {e}")
        
        return result

    def observe(self, user_id: str) -> Tuple[str, List[Dict]]:
        """
        Executes the observation logic:
        1. Reads Soul Profile to understand what to look for.
        2. Generates autonomous search queries.
        3. Uses Google Search Grounding to find info.
        4. Evaluates resonance.
        """
        from datetime import datetime
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()
        
        # Get current date for search context
        current_date = datetime.now().strftime("%Y年%m月%d日")
        print(f"[DEBUG] Current date for search: {current_date}")
        
        # Get drafts to exclude (already drafted grants)
        from src.agents.drafter import DrafterAgent
        drafter = DrafterAgent()
        drafts_list = drafter.docs_tool.list_drafts(user_id)
        excluded_grants = ", ".join(drafts_list[:10]) if drafts_list else "なし"
        print(f"[DEBUG] Excluding already drafted grants: {excluded_grants}")

        # Step 1: Autonomous Query Generation
        queries = self._generate_queries(profile)
        print(f"Generated Search Queries: {queries}")
        
        # Step 2: Search & Resonance Check
        # Get prompt template from config
        prompt_template = self.config.get("system_prompts", {}).get("observer_search_task", "")
        if prompt_template:
            # Check if template supports new variables
            if "{current_date}" in prompt_template:
                full_prompt = prompt_template.format(
                    system_prompt=self.system_prompt,
                    profile=profile,
                    queries=', '.join(queries),
                    current_date=current_date,
                    excluded_grants=excluded_grants
                )
            else:
                # Fallback: add current date manually
                full_prompt = prompt_template.format(
                    system_prompt=self.system_prompt,
                    profile=profile,
                    queries=', '.join(queries)
                )
                full_prompt += f"\n\n**重要**: 本日は{current_date}です。現在募集中の助成金のみを報告してください。"
                if drafts_list:
                    full_prompt += f"\n\n**除外リスト（ドラフト作成済み）**: {excluded_grants}"
        else:
            # Fallback to inline prompt if template not found
            full_prompt = f"""
{self.system_prompt}

現在のSoul Profile:
{profile}

検索戦略:
以下の検索クエリを生成しました：
{', '.join(queries)}

タスク:
検索ツールを使用して、このプロファイルと共鳴する現在のNPO助成金やCSR資金調達機会を見つけてください。
クエリが示唆する戦略を使用してください。
見つかった上位3つの機会について報告してください。
"""
        try:
            # Enable Google Search Tool
            tool_config = self.search_tool.get_tool_config()
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=GenerateContentConfig(
                    tools=[tool_config]
                )
            )
            response_text = response.text
            
            # Extract grounding metadata (actual URLs from Google Search)
            grounding_urls = []
            try:
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                        metadata = candidate.grounding_metadata
                        # Extract URLs from grounding_chunks
                        if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                            for chunk in metadata.grounding_chunks:
                                if hasattr(chunk, 'web') and chunk.web:
                                    uri = chunk.web.uri if hasattr(chunk.web, 'uri') else None
                                    title = chunk.web.title if hasattr(chunk.web, 'title') else None
                                    if uri:
                                        # Resolve redirect URL to get actual destination
                                        resolved_uri = resolve_redirect_url(uri)
                                        
                                        # Evaluate URL quality
                                        quality_score, quality_reason = evaluate_url_quality(resolved_uri)
                                        
                                        print(f"[DEBUG] URL quality: {resolved_uri[:60]}...")
                                        print(f"[DEBUG]   Score: {quality_score}/100, Reason: {quality_reason}")
                                        
                                        # Only include URLs with quality score >= 40
                                        if quality_score >= 40:
                                            grounding_urls.append({
                                                'url': resolved_uri,
                                                'title': title or 'No title',
                                                'quality_score': quality_score,
                                                'quality_reason': quality_reason
                                            })
                                            print(f"[DEBUG] Grounding URL accepted: {uri[:50]}... -> {resolved_uri}")
                                        else:
                                            print(f"[DEBUG] URL filtered out (score {quality_score}): {resolved_uri[:60]}...")
                            
                            # Sort by quality score (highest first)
                            grounding_urls.sort(key=lambda x: x['quality_score'], reverse=True)
                            print(f"[DEBUG] Total grounding URLs: {len(grounding_urls)} (after filtering)")
            except Exception as e:
                print(f"[DEBUG] Error extracting grounding metadata: {e}")

            
            # Parse opportunities from response (Step 1 results)
            opportunities = self._parse_opportunities(response_text)
            print(f"[OBSERVER Step1] Found {len(opportunities)} grant candidates")
            
            # ============================================
            # Step 2: Find official pages and verify deadlines
            # ============================================
            verified_opportunities = []
            skipped_expired = 0
            skipped_low_quality = 0
            
            for opp in opportunities:
                grant_name = opp.get('title', '')
                if not grant_name or grant_name == '不明':
                    continue
                
                print(f"\n[OBSERVER Step2] Processing: {grant_name}")
                
                # Find official page and verify deadline
                page_info = self._find_official_page(grant_name, current_date)
                
                # Check if valid (open or future)
                if not page_info['is_valid']:
                    if '終了' in page_info['status'] or '締切' in page_info['status']:
                        print(f"[OBSERVER Step2] SKIPPED (expired): {grant_name}")
                        skipped_expired += 1
                        continue
                    elif page_info.get('url_quality_score', 100) < 50:
                        print(f"[OBSERVER Step2] SKIPPED (low quality URL): {grant_name}")
                        skipped_low_quality += 1
                        continue
                
                # Update opportunity with verified info
                opp['url'] = page_info['official_url']
                opp['deadline_start'] = page_info['deadline_start']
                opp['deadline_end'] = page_info['deadline_end']
                opp['deadline_status'] = page_info['status']
                opp['url_verified'] = True
                opp['url_confidence'] = page_info['confidence']
                opp['url_quality_score'] = page_info.get('url_quality_score', 0)
                
                verified_opportunities.append(opp)
                print(f"[OBSERVER Step2] VERIFIED: {grant_name} -> {page_info['official_url'][:50]}...")
            
            print(f"\n[OBSERVER] Summary: {len(verified_opportunities)} verified, {skipped_expired} expired, {skipped_low_quality} low quality")
            
            # Build final response text with verified info
            if verified_opportunities:
                result_text = "## 🔍 助成金検索結果\n\n"
                result_text += f"**検索日**: {current_date}\n"
                result_text += f"**発見数**: {len(opportunities)}件 → **有効**: {len(verified_opportunities)}件\n"
                
                if skipped_expired > 0:
                    result_text += f"⏰ *{skipped_expired}件は募集終了のためスキップしました*\n"
                if skipped_low_quality > 0:
                    result_text += f"⚠️ *{skipped_low_quality}件は公式サイトが特定できませんでした*\n"
                
                result_text += "\n---\n\n"
                
                for i, opp in enumerate(verified_opportunities, 1):
                    result_text += f"### 機会 {i}: {opp['title']}\n"
                    result_text += f"- **公式URL**: {opp['url']}\n"
                    result_text += f"- **金額**: {opp['amount']}\n"
                    
                    if opp.get('deadline_start') and opp.get('deadline_end'):
                        result_text += f"- **募集期間**: {opp['deadline_start']} 〜 {opp['deadline_end']}\n"
                    
                    result_text += f"- **募集状況**: ✅ {opp['deadline_status']}\n"
                    result_text += f"- **共鳴スコア**: {opp['resonance_score']}/100\n"
                    result_text += f"- **共鳴理由**: {opp['reason']}\n"
                    result_text += f"- **URL信頼度**: {opp.get('url_confidence', '確認中')}\n\n"
                
                return result_text, verified_opportunities
            else:
                # No valid opportunities found
                result_text = "## 🔍 助成金検索結果\n\n"
                result_text += f"**検索日**: {current_date}\n\n"
                result_text += "現在募集中または今後募集予定の助成金は見つかりませんでした。\n"
                result_text += "しばらく時間をおいて再度お試しください。\n"
                return result_text, []
        except Exception as e:
            error_msg = f"Error during observation: {e}"
            return error_msg, []

    def investigate_grant(self, user_id: str, grant_name: str) -> str:
        """
        Investigates a specific grant in detail.
        
        Args:
            user_id: User identifier for profile context
            grant_name: Name of the grant to investigate
            
        Returns:
            Detailed investigation report with 5-axis resonance evaluation
        """
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()
        
        # Get prompt template from config
        prompt_template = self.config.get("system_prompts", {}).get("observer_detail_investigation", "")
        if prompt_template:
            full_prompt = prompt_template.format(
                profile=profile,
                grant_name=grant_name
            )
        else:
            # Fallback prompt
            full_prompt = f"""
助成金「{grant_name}」について詳しく調査してください。

NPOプロファイル:
{profile}

以下の情報を収集し報告してください：
1. 助成金の詳細情報（目的、金額、申請要件）
2. 過去の採択事例
3. 5軸での共鳴度評価（ミッション適合度、活動実績合致度、申請要件適合性、過去採択傾向類似性、成功見込み）
"""
        
        try:
            # Enable Google Search Tool for grounding
            tool_config = self.search_tool.get_tool_config()
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=GenerateContentConfig(
                    tools=[tool_config]
                )
            )
            response_text = response.text
            
            # Resolve redirect URLs
            redirect_pattern = r'https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[^\s\)\]\"\'\<\>]+'
            remaining_redirects = re.findall(redirect_pattern, response_text)
            for redirect_url in remaining_redirects:
                resolved_url = resolve_redirect_url(redirect_url)
                if resolved_url != redirect_url:
                    response_text = response_text.replace(redirect_url, resolved_url)
                    print(f"[DEBUG] Resolved redirect: {redirect_url[:50]}... -> {resolved_url}")
            
            return response_text
            
        except Exception as e:
            error_msg = f"詳細調査エラー: {e}"
            print(f"[ERROR] Grant investigation failed: {e}")
            return error_msg
