import re
import logging
from typing import List, Dict, Any, Optional
from google.genai.types import GenerateContentConfig
from src.tools.search_tool import SearchTool
from src.logic.grant_validator import GrantValidator
from src.utils.progress_notifier import get_progress_notifier, ProgressStage

class GrantFinder:
    """
    Handles grant search operations including query generation and official page lookup.
    """
    
    def __init__(self, client, model_name: str, config: Dict[str, Any]):
        self.client = client
        self.model_name = model_name
        self.config = config
        self.search_tool = SearchTool()
        self.validator = GrantValidator()
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
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=GenerateContentConfig(
                    tools=[tool_config]
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
        
        # Create a more targeted search query
        if org_name:
            search_hint = f"""
**検索戦略（重要）:**
以下の順序で検索してください：
1. 「{org_name} 助成金 募集 2025」または「{org_name} 助成金 募集 2026」
2. 「{org_name} 公式サイト 助成」
3. 組織の公式サイト内で助成金情報ページを探す

**注意:** 助成金名「{grant_name}」で直接検索すると古いページや関連ページがヒットしやすいため、
まず組織の助成金ポータルページを見つけ、そこから該当プログラムを特定してください。
"""
        else:
            search_hint = ""
        
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
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=GenerateContentConfig(
                    tools=[tool_config],
                    temperature=0.2
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
                quality_score, quality_reason = self.validator.evaluate_url_quality(result['official_url'], grant_name)
                result['url_quality_score'] = quality_score
                result['url_quality_reason'] = quality_reason
                
                if quality_score < 50:
                    logging.warning(f"[GRANT_FINDER] Low quality URL: {result['official_url']}")
                    result['is_valid'] = False
                
                is_accessible, access_status, final_url = self.validator.validate_url_accessible(result['official_url'])
                result['url_accessible'] = is_accessible
                result['url_access_status'] = access_status
                
                if is_accessible and final_url:
                    result['official_url'] = final_url
                else:
                    # Retry logic
                    return self._retry_find_official_page(grant_name, result, access_status)

            logging.info(f"[GRANT_FINDER] Result: URL={result['official_url'][:50]}..., Valid={result['is_valid']}")
            
        except Exception as e:
            logging.error(f"[GRANT_FINDER] Error finding official page: {e}")
        
        return result

    def _retry_find_official_page(self, grant_name: str, previous_result: Dict, failure_reason: str) -> Dict:
        """
        Retries finding the official page if the first attempt failed validation.
        Uses organization name + targeted keywords for better search accuracy.
        """
        logging.info(f"[GRANT_FINDER] Retrying for: {grant_name}")
        notifier = get_progress_notifier()
        notifier.notify_sync(ProgressStage.WARNING, f"URL検証失敗: {grant_name[:20]}...", f"代替URLを検索中... ({failure_reason})")
        
        # Extract organization name for targeted retry search
        org_name = self.validator.extract_organization_name(grant_name)
        
        if org_name:
            retry_prompt = f"""
助成金の公式申請ページを再検索してください。
前回見つけたURL ({previous_result['official_url']}) は無効でした（理由: {failure_reason}）。

**検索戦略（重要）:**
1. 「{org_name} 助成金 募集 2026」で検索
2. 「{org_name} 公式サイト」で組織のトップページを見つける
3. 組織サイト内の「助成金」「支援」「募集」ページを探す

**探している助成金:** {grant_name}

**重要条件:**
1. 財団・企業・行政の**公式サイトのみ**
2. 実際にアクセス可能なページ
3. .or.jp, .go.jp, .org, .co.jp など公式ドメイン

**出力形式:**
- **公式URL**: [正確なURL]
"""
        else:
            retry_prompt = f"""
助成金「{grant_name}」の公式申請ページを再検索してください。
前回見つけたURL ({previous_result['official_url']}) は無効でした（理由: {failure_reason}）。

**重要条件:**
1. 財団・企業・行政の公式サイトのみ
2. 実際にアクセス可能なページ
3. .or.jp, .go.jp, .org など公式ドメイン優先

**出力形式:**
- **公式URL**: [正確なURL]
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=retry_prompt,
                config=GenerateContentConfig(
                    tools=[self.search_tool.get_tool_config()],
                    temperature=0.1
                )
            )
            
            retry_url_match = re.search(r'\*\*公式URL\*\*:\s*(.+)', response.text)
            if retry_url_match:
                retry_url = retry_url_match.group(1).strip()
                retry_url = self.validator.resolve_redirect_url(retry_url)
                
                is_retry_accessible, retry_status, retry_final_url = self.validator.validate_url_accessible(retry_url)
                
                if is_retry_accessible and retry_final_url:
                    previous_result['official_url'] = retry_final_url
                    previous_result['url_accessible'] = True
                    previous_result['url_access_status'] = "リトライ成功"
                    logging.info(f"[GRANT_FINDER] Retry successful: {retry_final_url}")
                    return previous_result
                else:
                    previous_result['is_valid'] = False
                    previous_result['url_accessible'] = False
                    previous_result['url_access_status'] = f"リトライも失敗: {retry_status}"
                    previous_result['exclude_reason'] = f"URL検証失敗（初回: {failure_reason}, リトライ: {retry_status}）"
            else:
                 previous_result['is_valid'] = False
                 previous_result['exclude_reason'] = "代替URLが見つかりませんでした"
                 
        except Exception as retry_e:
            logging.error(f"[GRANT_FINDER] Retry error: {retry_e}")
            previous_result['is_valid'] = False
            previous_result['exclude_reason'] = "リトライ中にエラー発生"
            
        return previous_result
