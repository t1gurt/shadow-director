"""
Gemini Client Factory - Centralized Vertex AI client initialization.

This module provides a factory function for creating Gemini API clients
configured to use the Vertex AI backend.
"""

import os
import logging
from typing import Optional


def create_gemini_client():
    """
    Create a Gemini API client configured to use Vertex AI backend.
    
    Environment variables:
        GCP_PROJECT or GOOGLE_CLOUD_PROJECT: GCP project ID
        GCP_LOCATION: GCP location (default: us-central1)
    
    Returns:
        genai.Client instance or None if initialization fails
    """
    try:
        from google import genai
        from google.genai.types import HttpOptions
        
        # Get project and location from environment
        project = os.environ.get("GCP_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
        location = os.environ.get("GCP_LOCATION", "us-central1")
        
        if not project:
            logging.warning("[GEMINI_CLIENT] GCP_PROJECT not set, attempting auto-detection")
        
        # Initialize client with Vertex AI backend
        client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=HttpOptions(api_version="v1beta1")
        )
        
        logging.info(f"[GEMINI_CLIENT] Initialized Vertex AI client (project={project}, location={location})")
        return client
        
    except Exception as e:
        logging.error(f"[GEMINI_CLIENT] Failed to initialize Vertex AI client: {e}")
        return None


# Singleton instance for shared access
_client_instance = None

def get_gemini_client():
    """
    Get or create the shared Gemini API client.
    
    Returns:
        Shared genai.Client instance
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = create_gemini_client()
    return _client_instance
