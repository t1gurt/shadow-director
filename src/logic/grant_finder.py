import re
import logging
import asyncio
from typing import List, Dict, Any, Optional
from google.genai.types import GenerateContentConfig, ThinkingConfig
from src.tools.search_tool import SearchTool
from src.logic.grant_validator import GrantValidator
from src.logic.grant_page_scraper import GrantPageScraper
from src.utils.progress_notifier import get_progress_notifier, ProgressStage

class GrantFinder:
    """
    Handles grant search operations including query generation and official page lookup.
    Uses Playwright-based GrantPageScraper for enhanced page verification.
    Implements SGNA (Search-Ground-Navigate-Act) model for improved accuracy.
    """
    
    # Trusted domains for grant information (SGNA model: Site Restrictions)
    TRUSTED_DOMAINS = [
        'go.jp',      # 政府機関
        'or.jp',      # 財団法人・NPO
        'lg.jp',      # 地方自治体
        'ac.jp',      # 学術機関
        'org',        # 非営利組織
        'co.jp',      # 企業（CSR助成金）
        'com',        # 国際企業
    ]
    
    def __init__(self, client, model_name: str, config: Dict[str, Any]):
        self.client = client
        self.model_name = model_name
        self.config = config
        self.search_tool = SearchTool()
        self.validator = GrantValidator()
        self.page_scraper = GrantPageScraper()
        self.system_prompt = self.config.get("system_prompts", {}).get("observer", "")

    def generate_queries(self, profile: str) -> List[str]:
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
現在 Soul Profile:
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
            logging.error(f"Error generating queries: {e}")
            return [f"NPO助成金 {profile[:50]}..."] # Fallback

    def parse_opportunities(self, text: str) -> List[Dict]:
        """
        Parse structured opportunity data from Observer response.
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
                
                logging.debug(f"[DEBUG] Parsed opportunity: {title} (Score: {score})")
            except Exception as e:
                logging.error(f"[ERROR] Failed to parse opportunity section: {e}")
                continue
        
        return opportunities

    def search_grants(self, profile: str, current_date: str, excluded_grants: str = None) -> tuple[str, List[Dict]]:
        """
        Executes first step of observation: Generates queries and searches for grants.
        Returns the raw response text and parsed opportunities.
        """
        queries = self.generate_queries(profile)
        logging.info(f"Generated Search Queries: {queries}")
        
        # Get prompt template from config
        prompt_template = self.config.get("system_prompts", {}).get("observer_search_task", "")
        
        full_prompt = ""
        if prompt_template:
            if "{current_date}" in prompt_template:
                full_prompt = prompt_template.format(
                    system_prompt=self.system_prompt,
                    profile=profile,
                    queries=', '.join(queries),
                    current_date=current_date,
                    excluded_grants=excluded_grants or "なし"
                )
            else:
                full_prompt = prompt_template.format(
                    system_prompt=self.system_prompt,
                    profile=profile,
                    queries=', '.join(queries)
                )
                full_prompt += f"\n\n**重要**: 本日は{current_date}です。現在募集中の助成金のみを報告してください。"
                if excluded_grants:
                    full_prompt += f"\n\n**除外リスト（ドラフト作成済み）**: {excluded_grants}"
        else:
             full_prompt = f"""
{self.system_prompt}

現在のSoul Profile:
{profile}

検索戦略:
以下の検索クエリを生成しました:
{', '.join(queries)}

タスク:
検索ツールを使用して、このプロファイルと共鳴する現在のNPO助成金やCSR資金調達機会を見つけてください。
クエリが示唆する戦略を使用してください。
見つかった上位3つの機会について報告してください。
"""

        try:
            # Enable Google Search Tool
            tool_config = self.search_tool.get_tool_config()
            
            # Gemini 3.0 Thinking Mode for grant discovery
            thinking_config = ThinkingConfig(thinking_level="high")
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=GenerateContentConfig(
                    tools=[tool_config],
                    thinking_config=thinking_config
                )
            )
            response_text = response.text
            
            # Here we could extract grounding metadata as before if needed, 
            # but for now we focus on the text response parsing.
            
            opportunities = self.parse_opportunities(response_text)
            return response_text, opportunities
            
        except Exception as e:
            logging.error(f"Error in search_grants: {e}")
            return f"検索エラー: {e}", []

    def find_official_page(self, grant_name: str, current_date: str) -> Dict:
        """
        Searches for the official grant page and verifies the application deadline.
        Uses organization name + targeted keywords for better search accuracy.
        """
        logging.info(f"[GRANT_FINDER] Finding official page for: {grant_name}")
        
        result = {
            'official_url': 'N/A',
            'domain': '',
            'deadline_start': '',
            'deadline_end': '',
            'status': '不明',
            'is_valid': False,
            'confidence': '低',
            'confidence_reason': ''
        }
        
        # Extract organization name for targeted search
        org_name = self.validator.extract_organization_name(grant_name)
        if org_name:
            logging.info(f"[GRANT_FINDER] Extracted org name: {org_name}")
        
        # Build improved search prompt
        prompt_template = self.config.get("system_prompts", {}).get("observer_find_official_page", "")
        
        # Extract current year from current_date for search optimization
        current_year = "2026"
        if current_date:
            year_match = re.search(r'(\d{4})', current_date)
            if year_match:
                current_year = year_match.group(1)
        
        # Build site restriction string for trusted domains (SGNA model)
        site_restriction = " OR ".join([f"site:{d}" for d in self.TRUSTED_DOMAINS])
        
        # Create a more targeted search query with SGNA model enhancements
        if org_name:
            search_hint = f"""
**検索戦略（SGNAモデル - 重要）:**

**Step 1: 信頼できるドメインから検索**
検索クエリに以下のサイト制限を含めてください：
`"{org_name} 助成金 募集 {current_year}" ({site_restriction})`

**Step 2: 着陸ページ優先**
- PDFへの直接リンクではなく、HTMLの「公募要領ページ」を探してください
- 直リンクはリンク切れリスクが高く、最新版かどうかの判断が困難です

**Step 3: 最新情報の確認**
- 「{current_year}年度」「第○回」「令和○年」などの表記を確認
- 古い年度のページを避けてください

**注意:** 助成金名「{grant_name}」で直接検索すると古いページがヒットしやすいため、
まず組織の助成金ポータルページを見つけ、そこから該当プログラムを特定してください。
"""
        else:
            search_hint = f"""
**検索戦略（SGNAモデル）:**
助成金「{grant_name}」の公式ページを以下の条件で検索してください：
- 信頼できるドメイン: {site_restriction}
- 年度: {current_year}年度または最新の公募
- HTMLページを優先（PDFへの直リンクより着陸ページを優先）
"""
        
        if prompt_template:
            full_prompt = prompt_template.format(
                grant_name=grant_name,
                current_date=current_date
            )
            # Append search strategy hint
            full_prompt = search_hint + "\n" + full_prompt
        else:
            full_prompt = f"""
{search_hint}

助成金「{grant_name}」の公式申請ページを見つけてください。

本日: {current_date}

**出力形式:**
- **公式URL**: [正確なURL]
- **ドメイン**: [ドメイン名]
- **募集開始日**: [日付]
- **募集終了日**: [日付]
- **募集状況**: [募集中/募集終了/今後募集予定/不明]
- **信頼度**: [高/中/低]
- **信頼度理由**: [理由]
"""
        
        try:
            tool_config = self.search_tool.get_tool_config()
            
            # Gemini 3.0 Thinking Mode for deep reasoning during page investigation
            thinking_config = ThinkingConfig(thinking_level="high")
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=GenerateContentConfig(
                    tools=[tool_config],
                    temperature=0.2,
                    thinking_config=thinking_config
                )
            )
            
            response_text = response.text
            logging.info(f"[GRANT_FINDER] Response: {response_text[:200]}...")
            
            # Parse response
            url_match = re.search(r'\*\*公式URL\*\*:\s*(.+)', response_text)
            if url_match:
                url = url_match.group(1).strip()
                result['official_url'] = self.validator.resolve_redirect_url(url)
            
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
            
            # Validation Step
            if result['official_url'] != 'N/A':
                notifier = get_progress_notifier()
                
                quality_score, quality_reason = self.validator.evaluate_url_quality(result['official_url'], grant_name)
                result['url_quality_score'] = quality_score
                result['url_quality_reason'] = quality_reason
                
                # Notify user about URL quality
                if quality_score >= 70:
                    notifier.notify_sync(ProgressStage.ANALYZING, f"✅ 信頼性評価: {quality_score}点", quality_reason)
                elif quality_score >= 50:
                    notifier.notify_sync(ProgressStage.ANALYZING, f"⚠️ 信頼性評価: {quality_score}点", quality_reason)
                else:
                    notifier.notify_sync(ProgressStage.WARNING, f"❌ 信頼性評価: {quality_score}点（低）", quality_reason)
                
                if quality_score < 50:
                    logging.warning(f"[GRANT_FINDER] Low quality URL: {result['official_url']}")
                    result['is_valid'] = False
                
                is_accessible, access_status, final_url = self.validator.validate_url_accessible(result['official_url'])
                result['url_accessible'] = is_accessible
                result['url_access_status'] = access_status
                
                # Notify user about accessibility
                if is_accessible:
                    notifier.notify_sync(ProgressStage.ANALYZING, "✅ 公式ページにアクセス可能", f"URL: {final_url[:60]}...")
                else:
                    notifier.notify_sync(ProgressStage.WARNING, "❌ 公式ページにアクセス不可", access_status)
                
                if is_accessible and final_url:
                    result['official_url'] = final_url
                    
                    # Enhanced verification with Playwright
                    try:
                        logging.info(f"[GRANT_FINDER] Running Playwright verification for: {final_url}")
                        notifier.notify_sync(ProgressStage.ANALYZING, "🔍 Playwrightで詳細検証中...", "ページ内容を解析しています")
                        
                        playwright_result = self._run_playwright_verification(final_url, grant_name)
                        
                        if playwright_result:
                            result['playwright_verified'] = True
                            result['playwright_confidence'] = playwright_result.get('confidence', 0)
                            result['format_files'] = playwright_result.get('format_files', [])
                            
                            # Notify Playwright results
                            file_count = len(result.get('format_files', []))
                            if file_count > 0:
                                notifier.notify_sync(ProgressStage.ANALYZING, f"📎 フォーマットファイル {file_count}件 発見", "申請書様式を検出しました")
                            
                            # Update deadline info if found
                            if playwright_result.get('deadline_info'):
                                deadline = playwright_result['deadline_info']
                                if deadline.get('date'):
                                    result['deadline_end'] = deadline['date']
                                    notifier.notify_sync(ProgressStage.ANALYZING, f"📅 締切日: {deadline['date']}", "ページから締切日を抽出しました")
                            
                            logging.info(f"[GRANT_FINDER] Playwright found {file_count} format files")
                        else:
                            notifier.notify_sync(ProgressStage.ANALYZING, "ℹ️ Playwright検証完了", "追加情報は見つかりませんでした")
                    except Exception as pw_error:
                        logging.warning(f"[GRANT_FINDER] Playwright verification failed: {pw_error}")
                        result['playwright_verified'] = False
                else:
                    # Retry logic
                    return self._retry_find_official_page(grant_name, result, access_status)

            logging.info(f"[GRANT_FINDER] Result: URL={result['official_url'][:50]}..., Valid={result['is_valid']}")
            
        except Exception as e:
            logging.error(f"[GRANT_FINDER] Error finding official page: {e}")
        
        return result
    
    def _run_playwright_verification(self, url: str, grant_name: str) -> Optional[Dict[str, Any]]:
        """
        Run Playwright-based page verification.
        Uses nest_asyncio to allow running async code within Discord.py's event loop.
        """
        try:
            import nest_asyncio
            nest_asyncio.apply()
            
            # Now we can safely run asyncio.run() within the existing event loop
            return asyncio.run(self._async_playwright_verification(url, grant_name))
        except Exception as e:
            logging.error(f"[GRANT_FINDER] Playwright verification error: {e}")
            return None
    
    async def _async_playwright_verification(self, url: str, grant_name: str) -> Optional[Dict[str, Any]]:
        """
        Async Playwright verification.
        """
        try:
            grant_info = await self.page_scraper.find_grant_info(url, grant_name)
            
            if not grant_info.get('accessible'):
                return None
            
            return {
                'verified': True,
                'confidence': 80 if grant_info.get('format_files') else 50,
                'format_files': grant_info.get('format_files', []),
                'deadline_info': grant_info.get('deadline_info'),
                'related_links': grant_info.get('related_links', [])
            }
        except Exception as e:
            logging.error(f"[GRANT_FINDER] Async Playwright error: {e}")
            return None

    def _retry_find_official_page(self, grant_name: str, previous_result: Dict, failure_reason: str) -> Dict:
        """
        Retries finding the official page if the first attempt failed validation.
        Enhanced with:
        1. Multiple search query variations
        2. Playwright-based site exploration
        3. Up to 3 retry attempts
        """
        logging.info(f"[GRANT_FINDER] Retrying for: {grant_name}")
        notifier = get_progress_notifier()
        notifier.notify_sync(ProgressStage.WARNING, f"URL検証失敗: {grant_name[:20]}...", f"代替URLを検索中... ({failure_reason})")
        
        # Extract organization name for targeted retry search
        org_name = self.validator.extract_organization_name(grant_name)
        
        # Define multiple search strategies
        search_queries = []
        if org_name:
            search_queries = [
                f"{org_name} 助成金 募集 2026",
                f"{org_name} 補助金 申請",
                f"{org_name} 支援 公募",
                f"{org_name} 公式サイト 助成",
            ]
        else:
            search_queries = [
                f"{grant_name} 公式",
                f"{grant_name} 申請",
            ]
        
        # Try up to 3 different search strategies
        max_retries = min(3, len(search_queries))
        
        for retry_num in range(max_retries):
            query = search_queries[retry_num]
            notifier.notify_sync(ProgressStage.SEARCHING, f"代替検索 ({retry_num + 1}/{max_retries})", f"検索: {query[:40]}...")
            logging.info(f"[GRANT_FINDER] Retry {retry_num + 1}: searching with '{query}'")
            
            # Build site restriction for retry (SGNA model)
            site_restriction = " OR ".join([f"site:{d}" for d in self.TRUSTED_DOMAINS])
            
            retry_prompt = f"""
助成金の公式申請ページを検索してください。

**検索クエリ（SGNAモデル）:** `"{query}" ({site_restriction})`

**探している助成金:** {grant_name}

**重要条件:**
1. 信頼できるドメインのみ: go.jp, or.jp, lg.jp, co.jp, org, com
2. **着陸ページ優先**: PDFへの直リンクではなく、HTMLの公募ページを選択
3. 最新の公募情報であること（年度を確認）

**出力形式:**
- **公式URL**: [正確なURL]
"""
            try:
                # Gemini 3.0 Thinking Mode for retry search
                thinking_config = ThinkingConfig(thinking_level="high")
                
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=retry_prompt,
                    config=GenerateContentConfig(
                        tools=[self.search_tool.get_tool_config()],
                        temperature=0.1,
                        thinking_config=thinking_config
                    )
                )
                
                retry_url_match = re.search(r'\*\*公式URL\*\*:\s*(.+)', response.text)
                if retry_url_match:
                    retry_url = retry_url_match.group(1).strip()
                    retry_url = self.validator.resolve_redirect_url(retry_url)
                    
                    # Skip if same as failed URL
                    if retry_url == previous_result.get('official_url'):
                        logging.info(f"[GRANT_FINDER] Same URL found, trying next query")
                        continue
                    
                    is_retry_accessible, retry_status, retry_final_url = self.validator.validate_url_accessible(retry_url)
                    
                    if is_retry_accessible and retry_final_url:
                        notifier.notify_sync(ProgressStage.ANALYZING, f"✅ 代替URL発見 (試行{retry_num + 1})", retry_final_url[:60])
                        
                        previous_result['official_url'] = retry_final_url
                        previous_result['url_accessible'] = True
                        previous_result['url_access_status'] = f"リトライ成功（試行{retry_num + 1}）"
                        logging.info(f"[GRANT_FINDER] Retry {retry_num + 1} successful: {retry_final_url}")
                        return previous_result
                    else:
                        logging.info(f"[GRANT_FINDER] Retry {retry_num + 1} URL not accessible: {retry_status}")
                        
            except Exception as retry_e:
                logging.error(f"[GRANT_FINDER] Retry {retry_num + 1} error: {retry_e}")
        
        # All LLM retries failed - try Playwright exploration as last resort
        if org_name:
            notifier.notify_sync(ProgressStage.SEARCHING, "🔍 Playwright深掘り検索中...", f"組織サイトを探索: {org_name}")
            playwright_url = self._playwright_find_grant_page(org_name, grant_name)
            
            if playwright_url:
                is_accessible, status, final_url = self.validator.validate_url_accessible(playwright_url)
                if is_accessible and final_url:
                    notifier.notify_sync(ProgressStage.ANALYZING, "✅ Playwrightで代替URL発見", final_url[:60])
                    previous_result['official_url'] = final_url
                    previous_result['url_accessible'] = True
                    previous_result['url_access_status'] = "Playwright検索で発見"
                    logging.info(f"[GRANT_FINDER] Playwright found: {final_url}")
                    return previous_result
        
        # All retries failed
        notifier.notify_sync(ProgressStage.WARNING, "❌ 代替URLが見つかりませんでした", f"{max_retries}回の検索とPlaywright探索で発見できず")
        previous_result['is_valid'] = False
        previous_result['url_accessible'] = False
        previous_result['exclude_reason'] = f"URL検証失敗（{max_retries}回リトライ + Playwright探索失敗）"
        
        return previous_result
    
    def _playwright_find_grant_page(self, org_name: str, grant_name: str) -> Optional[str]:
        """
        Use Playwright to find grant page by exploring organization's website.
        """
        try:
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(self._async_playwright_find_grant_page(org_name, grant_name))
        except Exception as e:
            logging.error(f"[GRANT_FINDER] Playwright search error: {e}")
            return None
    
    async def _async_playwright_find_grant_page(self, org_name: str, grant_name: str) -> Optional[str]:
        """
        Async Playwright search for grant page.
        Searches Google for organization site, then explores for grant pages.
        """
        try:
            # Search for organization's official site
            search_url = f"https://www.google.com/search?q={org_name}+公式サイト+助成金"
            
            grant_info = await self.page_scraper.find_grant_info(search_url, grant_name)
            
            if grant_info.get('accessible'):
                # Look for related links that might be grant pages
                related = grant_info.get('related_links', [])
                for link in related[:5]:
                    href = link.get('href', '')
                    text = link.get('text', '')
                    
                    # Check if link looks like a grant page
                    combined = (href + text).lower()
                    grant_keywords = ['助成', '補助', '支援', '募集', '公募', '申請']
                    
                    if any(kw in combined for kw in grant_keywords):
                        logging.info(f"[GRANT_FINDER] Playwright found potential grant page: {href}")
                        return href
            
            return None
            
        except Exception as e:
            logging.error(f"[GRANT_FINDER] Async Playwright search error: {e}")
            return None

