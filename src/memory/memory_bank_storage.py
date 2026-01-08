"""
Vertex AI Memory Bank Storage Backend
Uses Vertex AI Agent Engine Memory Bank for persistent memory storage.

Updated to use client-based API per migration guide:
https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations/agent-engine-migration
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional

try:
    import vertexai
    MEMORY_BANK_AVAILABLE = True
except ImportError:
    MEMORY_BANK_AVAILABLE = False
    logging.warning("[MEMORY_BANK] vertexai not available for Memory Bank")


class MemoryBankStorage:
    """
    Stores memories using Vertex AI Agent Engine Memory Bank.
    Data is organized by channel_id (scope) for team collaboration.
    
    Uses the new client-based API (vertexai.Client).
    """
    
    def __init__(self, project_id: str = None, location: str = "us-central1", agent_engine_id: str = None):
        """
        Initialize Memory Bank storage.
        
        Args:
            project_id: Google Cloud project ID
            location: Vertex AI location (default: us-central1, must be a supported region)
            agent_engine_id: Optional explicit Agent Engine ID
        """
        if not MEMORY_BANK_AVAILABLE:
            raise ImportError("vertexai is required for MemoryBankStorage")
        
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self.agent_engine_id_override = agent_engine_id or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")
        
        # Initialize new Vertex AI Client (client-based API)
        # https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations/agent-engine-migration
        self.client = vertexai.Client(
            project=self.project_id,
            location=self.location
        )
        
        # Get or create Agent Engine instance
        self.agent_engine_name = self._get_or_create_agent_engine()
        
        logging.info(f"[MEMORY_BANK] Initialized with Agent Engine: {self.agent_engine_name}")
    
    def _get_or_create_agent_engine(self) -> str:
        """
        Get existing Agent Engine or create a new one for Memory Bank.
        
        Returns:
            Agent Engine resource name
        """
        # 1. Use explicit ID if provided
        if self.agent_engine_id_override:
            # Format: projects/{project}/locations/{location}/reasoningEngines/{id}
            if "/" in self.agent_engine_id_override:
                # Already a full resource name
                name = self.agent_engine_id_override
            else:
                # ID only - construct full name
                name = f"projects/{self.project_id}/locations/{self.location}/reasoningEngines/{self.agent_engine_id_override}"
            
            logging.info(f"[MEMORY_BANK] Using configured Agent Engine ID: {name}")
            return name

        # 2. List existing Agent Engines to find one for Shadow Director
        try:
            # Use new API: client.agent_engines.list()
            engines = list(self.client.agent_engines.list())
            
            # Look for existing Shadow Director engine
            for engine in engines:
                # Access display_name from the engine object
                display_name = getattr(engine, 'display_name', '') or ''
                if not display_name and hasattr(engine, 'api_resource'):
                    display_name = getattr(engine.api_resource, 'display_name', '') or ''
                
                if "shadow-director" in display_name.lower():
                    engine_name = getattr(engine, 'name', '') or getattr(engine.api_resource, 'name', '')
                    logging.info(f"[MEMORY_BANK] Found existing Agent Engine: {engine_name}")
                    return engine_name
            
            # Create new Agent Engine for Memory Bank
            return self._create_agent_engine()
            
        except Exception as e:
            logging.error(f"[MEMORY_BANK] Error listing Agent Engines: {e}")
            return self._create_agent_engine()
    
    def _create_agent_engine(self) -> str:
        """
        Create a new Agent Engine instance with Memory Bank configuration.
        Uses the new client-based API.
        
        Returns:
            Agent Engine resource name
        """
        try:
            # Create Agent Engine using new client-based API
            # https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations/agent-engine-migration
            # Format: client.agent_engines.create(agent=None, config={...})
            agent_engine = self.client.agent_engines.create(
                agent=None,  # No agent for memory-only engine
                config={
                    "display_name": "shadow-director-memory-bank",
                    "description": "Memory Bank for Shadow Director NPO assistant",
                    "context_spec": {
                        "memory_bank_config": {
                            # Default memory bank configuration - automatic memory generation
                        }
                    }
                }
            )
            
            # Get the resource name
            name = getattr(agent_engine, 'name', '') or getattr(agent_engine.api_resource, 'name', '')
            logging.info(f"[MEMORY_BANK] Created new Agent Engine: {name}")
            return name
            
        except Exception as e:
            logging.error(f"[MEMORY_BANK] Error creating Agent Engine: {e}")
            raise
    
    def load(self, channel_id: str) -> Dict[str, Any]:
        """
        Load profile data from Memory Bank.
        
        Args:
            channel_id: Discord channel ID (used as scope)
        
        Returns:
            Profile data dictionary
        """
        try:
            # Retrieve all memories for this channel scope
            memories = self.retrieve_memories(channel_id)
            
            if not memories:
                return {}
            
            # Reconstruct profile from memories
            profile = {
                "insights": {},
                "conversation_history": []
            }
            
            for memory in memories:
                fact = memory.get("fact", "")
                
                # Parse structured memories
                if fact.startswith("INSIGHT:"):
                    # Format: INSIGHT:category:content
                    parts = fact.split(":", 2)
                    if len(parts) >= 3:
                        profile["insights"][parts[1]] = parts[2]
                elif fact.startswith("HISTORY:"):
                    # Format: HISTORY:role:content
                    parts = fact.split(":", 2)
                    if len(parts) >= 3:
                        profile["conversation_history"].append({
                            "role": parts[1],
                            "content": parts[2]
                        })
            
            return profile
            
        except Exception as e:
            logging.error(f"[MEMORY_BANK] Error loading from Memory Bank: {e}")
            return {}
    
    def save(self, channel_id: str, data: Dict[str, Any]) -> None:
        """
        Save profile data to Memory Bank.
        
        Args:
            channel_id: Discord channel ID (used as scope)
            data: Profile data dictionary
        """
        try:
            # Save insights as individual memories
            insights = data.get("insights", {})
            for category, content in insights.items():
                fact = f"INSIGHT:{category}:{content}"
                self.create_memory(channel_id, fact)
            
            # Save conversation history
            history = data.get("conversation_history", [])
            for entry in history[-10:]:  # Only save last 10 entries
                fact = f"HISTORY:{entry['role']}:{entry['content']}"
                self.create_memory(channel_id, fact)
            
            logging.info(f"[MEMORY_BANK] Saved profile for channel: {channel_id}")
            
        except Exception as e:
            logging.error(f"[MEMORY_BANK] Error saving to Memory Bank: {e}")
    
    def create_memory(self, channel_id: str, fact: str) -> Optional[str]:
        """
        Create a single memory in Memory Bank using generate API.
        
        Args:
            channel_id: Discord channel ID (scope)
            fact: The fact to store
        
        Returns:
            Memory resource name, or None if failed
        """
        try:
            # Use new API: client.agent_engines.memories.generate()
            # scope is a dictionary for scoping memories
            result = self.client.agent_engines.memories.generate(
                name=self.agent_engine_name,
                scope={"channel_id": channel_id},
                messages=[{
                    "role": "user",
                    "content": fact
                }]
            )
            
            logging.info(f"[MEMORY_BANK] Created memory for channel {channel_id}")
            return str(result) if result else None
            
        except Exception as e:
            logging.error(f"[MEMORY_BANK] Error creating memory: {e}")
            return None
    
    def retrieve_memories(
        self, 
        channel_id: str, 
        query: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories from Memory Bank.
        
        Args:
            channel_id: Discord channel ID (scope)
            query: Optional query for similarity search
            limit: Maximum number of memories to retrieve
        
        Returns:
            List of memory dictionaries
        """
        try:
            # Use new API with scope parameter
            if query:
                # Similarity search with query
                result = self.client.agent_engines.memories.retrieve(
                    name=self.agent_engine_name,
                    scope={"channel_id": channel_id},
                    similarity_search_params={
                        "query": query,
                        "max_memories_to_return": min(limit, 100)
                    }
                )
            else:
                # Simple retrieval without query
                result = self.client.agent_engines.memories.retrieve(
                    name=self.agent_engine_name,
                    scope={"channel_id": channel_id},
                    simple_retrieval_params={
                        "max_memories_to_return": min(limit, 100)
                    }
                )
            
            # Parse result into list of memory dicts
            memories = []
            if result and hasattr(result, 'memories'):
                for memory in result.memories:
                    memories.append({
                        "fact": getattr(memory, 'fact', ''),
                        "memory_id": getattr(memory, 'name', '')
                    })
            
            return memories
            
        except Exception as e:
            logging.error(f"[MEMORY_BANK] Error retrieving memories: {e}")
            return []
    
    def generate_memories(self, channel_id: str, conversation: List[Dict]) -> List[str]:
        """
        Generate memories from conversation using LLM.
        
        Args:
            channel_id: Discord channel ID (scope)
            conversation: List of conversation entries
        
        Returns:
            List of generated memory facts
        """
        try:
            # Use new API: client.agent_engines.memories.generate()
            # Format conversation as messages for memory generation
            messages = [
                {
                    "role": entry.get('role', 'user'),
                    "content": entry.get('content', '')
                }
                for entry in conversation
            ]
            
            result = self.client.agent_engines.memories.generate(
                name=self.agent_engine_name,
                scope={"channel_id": channel_id},
                messages=messages
            )
            
            # Extract generated memories
            memories = []
            if result and hasattr(result, 'memories'):
                for memory in result.memories:
                    if hasattr(memory, 'fact'):
                        memories.append(memory.fact)
            
            logging.info(f"[MEMORY_BANK] Generated {len(memories)} memories for channel {channel_id}")
            return memories
            
        except Exception as e:
            logging.error(f"[MEMORY_BANK] Error generating memories: {e}")
            return []
    
    def search_memories(self, channel_id: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search memories by similarity.
        
        Args:
            channel_id: Discord channel ID (scope)
            query: Search query
            limit: Maximum results
        
        Returns:
            List of relevant memories
        """
        return self.retrieve_memories(channel_id, query=query, limit=limit)
