import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents.observer import ObserverAgent
from src.logic.grant_validator import GrantValidator

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_validator():
    print("\n--- Testing GrantValidator ---")
    validator = GrantValidator()
    
    # Test Organization Name Extraction
    test_names = [
        ("トヨタ財団 研究助成", "トヨタ財団"),
        ("日本財団 助成プログラム", "日本財団"),
        ("KDDI財団 寄付", "KDDI財団"),
        ("NPO法人ソーシャルイノベーション 支援", "NPO法人ソーシャルイノベーション"),
        ("株式会社リコー 環境保全活動", "株式会社リコー"),
    ]
    
    for input_name, expected in test_names:
        result = validator.extract_organization_name(input_name)
        status = "✅" if result == expected else f"❌ (Expected: {expected}, Got: {result})"
        print(f"Extract '{input_name}': {status}")

    # Test URL Accessibility (Lightweight)
    # Use a known stable URL like google.com
    print("\nTesting URL check (google.com)...")
    valid, msg, url = validator.validate_url_accessible("https://www.google.com")
    print(f"Result: {valid}, {msg}, {url}")

def test_observer_init():
    print("\n--- Testing ObserverAgent Initialization ---")
    try:
        agent = ObserverAgent()
        print(f"ObserverAgent initialized successfully.")
        print(f"Agent Model: {agent.model_name}")
        print(f"Finder initialized: {agent.finder is not None}")
        return agent
    except Exception as e:
        print(f"❌ Failed to initialize ObserverAgent: {e}")
        return None

if __name__ == "__main__":
    print("Starting Verification...")
    test_validator()
    
    agent = test_observer_init()
    if agent:
        print("\n✅ Basic initialization checks passed.")
        print("To run full observation, calling agent.observe('test_user') would require API keys and might cost money.")
        print("Skipping full observation run in this script.")
    else:
        print("\n❌ Initialization failed.")
