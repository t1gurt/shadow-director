"""
Vertex AI Memory Bank Storage Backend
Uses Vertex AI Agent Engine Memory Bank for persistent memory storage.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

try:
    from google.cloud import aiplatform
    from google.cloud.aiplatform_v1beta1 import (
        ReasoningEngineServiceClient,
        ReasoningEngineExecutionServiceClient,
    )
    from google.cloud.aiplatform_v1beta1.types import (
        reasoning_engine as reasoning_engine_types,
    )
    MEMORY_BANK_AVAILABLE = True
except ImportError:
    MEMORY_BANK_AVAILABLE = False
    logging.warning("[MEMORY_BANK] google-cloud-aiplatform not available for Memory Bank")


class MemoryBankStorage:
    """
    Stores memories using Vertex AI Agent Engine Memory Bank.
    Data is organized by channel_id (scope) for team collaboration.
    """
    
    def __init__(self, project_id: str = None, location: str = "us-central1", agent_engine_id: str = None):
        """
        Initialize Memory Bank storage.
        
        Args:
            project_id: Google Cloud project ID
            location: Vertex AI location (default: us-central1)
            agent_engine_id: Optional explicit Agent Engine ID
        """
        if not MEMORY_BANK_AVAILABLE:
            raise ImportError("google-cloud-aiplatform is required for MemoryBankStorage")
        
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self.agent_engine_id_override = agent_engine_id or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")
        
        # Initialize Vertex AI
        aiplatform.init(project=self.project_id, location=self.location)
        
        # Client for managing Agent Engine instances
        self.client = ReasoningEngineServiceClient()
        self.execution_client = ReasoningEngineExecutionServiceClient()
        
        # Parent path for API calls
        self.parent = f"projects/{self.project_id}/locations/{self.location}"
        
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
                # ID only
                name = f"{self.parent}/reasoningEngines/{self.agent_engine_id_override}"
            
            logging.info(f"[MEMORY_BANK] Using configured Agent Engine ID: {name}")
            return name

        # 2. List existing Agent Engines to find one for Shadow Director
        try:
            # Try using the direct method without request object (newer API)
            try:
                engines = list(self.client.list_reasoning_engines(parent=self.parent))
            except TypeError:
                # Fallback: try with request object (older API)
                try:
                    request = reasoning_engine_types.ListReasoningEnginesRequest(
                        parent=self.parent
                    )
                    engines = list(self.client.list_reasoning_engines(request=request))
                except AttributeError:
                    # ListReasoningEnginesRequest not available in this SDK version
                    logging.warning("[MEMORY_BANK] ListReasoningEnginesRequest not available, skipping list")
                    engines = []
            
            # Look for existing Shadow Director engine
            for engine in engines:
                if hasattr(engine, 'display_name') and "shadow-director" in engine.display_name.lower():
                    logging.info(f"[MEMORY_BANK] Found existing Agent Engine: {engine.name}")
                    return engine.name
            
            # Create new Agent Engine for Memory Bank
            return self._create_agent_engine()
            
        except Exception as e:
            logging.error(f"[MEMORY_BANK] Error listing Agent Engines: {e}")
            return self._create_agent_engine()
    
    def _create_agent_engine(self) -> str:
        """
        Create a new Agent Engine instance with Memory Bank configuration.
        
        Returns:
            Agent Engine resource name
        """
        try:
            # Check if required types are available
            if not hasattr(reasoning_engine_types, 'ReasoningEngine'):
                raise AttributeError("ReasoningEngine type not available in SDK")
            
            if not hasattr(reasoning_engine_types, 'ReasoningEngineSpec'):
                raise AttributeError("ReasoningEngineSpec type not available in SDK")
            
            # Create Agent Engine with Memory Bank config
            reasoning_engine = reasoning_engine_types.ReasoningEngine(
                display_name="shadow-director-memory-bank",
                spec=reasoning_engine_types.ReasoningEngineSpec(
                    # Memory Bank configuration - use empty dict if class_methods not supported
                    class_methods=[] if hasattr(reasoning_engine_types.ReasoningEngineSpec, 'class_methods') else None
                )
            )
            
            # Try direct method first (newer API)
            try:
                operation = self.client.create_reasoning_engine(
                    parent=self.parent,
                    reasoning_engine=reasoning_engine
                )
            except TypeError:
                # Fallback to request object
                request = reasoning_engine_types.CreateReasoningEngineRequest(
                    parent=self.parent,
                    reasoning_engine=reasoning_engine
                )
                operation = self.client.create_reasoning_engine(request=request)
            
            result = operation.result()
            
            logging.info(f"[MEMORY_BANK] Created new Agent Engine: {result.name}")
            return result.name
            
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
        Create a single memory in Memory Bank.
        
        Args:
            channel_id: Discord channel ID (scope)
            fact: The fact to store
        
        Returns:
            Memory resource name, or None if failed
        """
        try:
            # Use the Agent Engine to create memory
            request = {
                "scope": {
                    "channel_id": channel_id
                },
                "fact": fact
            }
            
            # Execute memory creation
            response = self.execution_client.query_reasoning_engine(
                name=self.agent_engine_name,
                input={"action": "create_memory", "data": request}
            )
            
            logging.info(f"[MEMORY_BANK] Created memory for channel {channel_id}")
            return response.output if hasattr(response, 'output') else None
            
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
            request = {
                "scope": {
                    "channel_id": channel_id
                },
                "limit": limit
            }
            
            if query:
                request["query"] = query
            
            response = self.execution_client.query_reasoning_engine(
                name=self.agent_engine_name,
                input={"action": "retrieve_memories", "data": request}
            )
            
            if hasattr(response, 'output'):
                return json.loads(response.output) if isinstance(response.output, str) else response.output
            return []
            
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
            # Format conversation for memory generation
            conversation_text = "\n".join([
                f"{entry['role']}: {entry['content']}"
                for entry in conversation
            ])
            
            request = {
                "scope": {
                    "channel_id": channel_id
                },
                "conversation": conversation_text
            }
            
            response = self.execution_client.query_reasoning_engine(
                name=self.agent_engine_name,
                input={"action": "generate_memories", "data": request}
            )
            
            if hasattr(response, 'output'):
                memories = json.loads(response.output) if isinstance(response.output, str) else response.output
                logging.info(f"[MEMORY_BANK] Generated {len(memories)} memories for channel {channel_id}")
                return memories
            return []
            
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
