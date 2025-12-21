from typing import Dict, Any, List, Optional
import yaml
import os
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

    def observe(self, user_id: str) -> str:
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
            return response.text
        except Exception as e:
            return f"Error during observation: {e}"
