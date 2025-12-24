from typing import Dict, Any, List, Optional, Tuple
import yaml
import os
import re
from google import genai
from google.genai.types import HttpOptions, GenerateContentConfig
from src.tools.search_tool import SearchTool
from src.memory.profile_manager import ProfileManager

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
        prompt = f"""
Current Soul Profile:
{profile}

Task:
Generate 3 distinct search queries to find the best funding opportunities (grants, CSR) for this NPO.
Focus on the mission, target issue, and unique strengths.
Output ONLY the queries, one per line.
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
            return [f"NPO grants {profile[:50]}..."] # Fallback
    
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
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()

        # Step 1: Autonomous Query Generation
        queries = self._generate_queries(profile)
        print(f"Generated Search Queries: {queries}")
        
        # Step 2: Search & Resonance Check
        # We combine queries or iterate. For simplicity/cost, we can combine or just use the best one + profile context in the prompt.
        # Here, we will let the model use the tool with the specific intent derived from queries.
        
        full_prompt = f"""
{self.system_prompt}

Current Soul Profile:
{profile}

Search Strategy:
I have generated these search queries to find opportunities:
{', '.join(queries)}

Task:
Using the search tool, find current NPO grants or CSR funding opportunities that resonate with this profile.
Use the strategies implied by the queries.
Report on the top 3 opportunities found.
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
            
            # Parse opportunities from response
            opportunities = self._parse_opportunities(response_text)
            
            return response_text, opportunities
        except Exception as e:
            error_msg = f"Error during observation: {e}"
            return error_msg, []
