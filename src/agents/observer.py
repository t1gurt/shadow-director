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
                                        grounding_urls.append({
                                            'url': resolved_uri,
                                            'title': title or 'No title'
                                        })
                                        print(f"[DEBUG] Grounding URL: {uri[:50]}... -> {resolved_uri}")
            except Exception as e:
                print(f"[DEBUG] Error extracting grounding metadata: {e}")

            
            # Parse opportunities from response
            opportunities = self._parse_opportunities(response_text)
            
            # Update opportunities with grounding URLs and fix response text
            if grounding_urls and opportunities:
                for i, opp in enumerate(opportunities):
                    if i < len(grounding_urls):
                        old_url = opp.get('url', '')
                        new_url = grounding_urls[i]['url']
                        # Replace hallucinated URL with grounded URL in response text
                        if old_url and old_url != 'N/A' and old_url in response_text:
                            response_text = response_text.replace(old_url, new_url)
                        # Update opportunity dict
                        opp['url'] = new_url
                        opp['grounded'] = True
                        print(f"[DEBUG] Replaced URL for '{opp['title']}': {old_url} -> {new_url}")
            
            # Additionally, scan response text for any remaining redirect URLs and resolve them
            redirect_pattern = r'https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[^\s\)\]\"\'<>]+'
            remaining_redirects = re.findall(redirect_pattern, response_text)
            for redirect_url in remaining_redirects:
                resolved_url = resolve_redirect_url(redirect_url)
                if resolved_url != redirect_url:
                    response_text = response_text.replace(redirect_url, resolved_url)
                    print(f"[DEBUG] Resolved remaining redirect: {redirect_url[:50]}... -> {resolved_url}")
            
            return response_text, opportunities
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
