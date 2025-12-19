import sys
import time
from src.agents.orchestrator import Orchestrator

def main():
    print("=== NPO-SoulSync Agent: Mock Runner ===")
    print("Discordトークンなしでロジックを検証するためのCLIツールです。")
    print("終了するには 'exit' または 'quit' と入力してください。")
    print("=======================================\n")

    orchestrator = Orchestrator()
    
    # Mock User ID
    user_id = "mock_user_123"

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ['exit', 'quit']:
                print("Exiting...")
                break
            
            if not user_input.strip():
                continue

            print("\nThinking...", end="", flush=True)
            # Simulate latency
            time.sleep(0.5) 
            print("\r", end="")

            response = orchestrator.route_message(user_input, user_id)
            print(f"Agent: {response}\n")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}\n")

if __name__ == "__main__":
    main()
