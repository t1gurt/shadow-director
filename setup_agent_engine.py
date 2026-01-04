
import os
import logging
from google.cloud import aiplatform
from google.cloud.aiplatform_v1beta1 import ReasoningEngineServiceClient
from google.cloud.aiplatform_v1beta1.types import reasoning_engine as reasoning_engine_types

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_agent_engine():
    """Creates or retrieves an Agent Engine for Shadow Director Memory Bank."""
    
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "zenn-shadow-director")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1") # Memory Bank usually in us-central1
    
    logging.info(f"Setting up Agent Engine for Project: {project_id}, Location: {location}")
    
    aiplatform.init(project=project_id, location=location)
    client = ReasoningEngineServiceClient()
    parent = f"projects/{project_id}/locations/{location}"
    
    # 1. Check for existing engines
    logging.info("Checking for existing Agent Engines...")
    try:
        try:
            engines = list(client.list_reasoning_engines(parent=parent))
        except TypeError:
             request = reasoning_engine_types.ListReasoningEnginesRequest(parent=parent)
             engines = list(client.list_reasoning_engines(request=request))

        for engine in engines:
            if hasattr(engine, 'display_name') and "shadow-director" in engine.display_name.lower():
                logging.info(f"✅ Found existing Agent Engine: {engine.name}")
                logging.info(f"ID: {engine.name.split('/')[-1]}")
                return engine.name
    except Exception as e:
        logging.warning(f"Error listing engines: {e}")

    # 2. Create new engine if not found
    logging.info("Creating NEW Agent Engine...")
    try:
        reasoning_engine = reasoning_engine_types.ReasoningEngine(
            display_name="shadow-director-memory-bank",
            description="Agent Engine for Shadow Director Memory Bank",
            spec=reasoning_engine_types.ReasoningEngineSpec(
                class_methods=[]
            )
        )

        try:
             operation = client.create_reasoning_engine(
                parent=parent,
                reasoning_engine=reasoning_engine
            )
        except TypeError:
            request = reasoning_engine_types.CreateReasoningEngineRequest(
                parent=parent,
                reasoning_engine=reasoning_engine
            )
            operation = client.create_reasoning_engine(request=request)
        
        result = operation.result()
        logging.info(f"✅ Created Agent Engine: {result.name}")
        logging.info(f"ID: {result.name.split('/')[-1]}")
        return result.name

    except Exception as e:
        logging.error(f"❌ Failed to create Agent Engine: {e}")
        return None

if __name__ == "__main__":
    setup_agent_engine()
