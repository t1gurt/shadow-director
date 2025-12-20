from typing import List, Dict, Any, Optional
from google.genai.types import Tool, GoogleSearch

class SearchTool:
    """
    Wrapper for Google Search Grounding using google-genai SDK.
    """
    def __init__(self):
        # In google-genai SDK, tools are passed to the generate_content calls.
        # This class mainly serves as a configuration holder or helper.
        pass

    def get_tool_config(self) -> Tool:
        """
        Returns the Tool configuration for Google Search.
        """
        return Tool(
            google_search=GoogleSearch()
        )
