import argparse
import sys
import time
from src.agents.orchestrator import Orchestrator
from src.agents.observer import ObserverAgent

def main():
    parser = argparse.ArgumentParser(description="Mock Runner for NPO-SoulSync")
    parser.add_argument("--mode", choices=["interviewer", "observer"], default="interviewer", help="Agent mode to run")
    parser.add_argument("--user-id", default="mock_user_123", help="Mock User ID")
    args = parser.parse_args()

    print("=== NPO-SoulSync Agent: Mock Runner ===")
    print("Discordトークンなしでロジックを検証するためのCLIツールです。")
    print(f"Mode: {args.mode}")
    print(f"User ID: {args.user_id}")
    print("=======================================\n")

    if args.mode == "observer":
        print("Initializing Observer Agent...")
        try:
            observer = ObserverAgent()
            print("Observer initialized. Running observation task...")
            print("Searching for funding opportunities based on Soul Profile...")
            
            # Simulate processing time
            time.sleep(1)
            
            result = observer.observe(user_id=args.user_id)
            print("\n[Observer Result]")
            print(result)
        except Exception as e:
            print(f"Error in Observer mode: {e}")
        return

    # Interviewer Mode (via Orchestrator)
    orchestrator = Orchestrator()
    print("Agent: こんにちは。NPO-SoulSyncです。壁打ちを始めましょう。（'quit'で終了）")

    turn_count = 1
    max_turns = 15

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ["quit", "exit", "終了"]:
                print("Exiting...")
                break
            
            if not user_input.strip():
                continue

            print(f"Thinking... (Turn {turn_count}/{max_turns})", end="", flush=True)
            time.sleep(0.5) 
            print("\r", end="")

            # Orchestrator uses process_message (or route_message depending on implementation, checking file now)
            # Based on previous context, it seems to be process_message or similar.
            # I will use process_message as it is standard. If orchestrator has route_message, I will find out.
            # The orchestrator.py view in next step will confirm.
            
            # Orchestrator uses route_message based on src/agents/orchestrator.py
            response = orchestrator.route_message(user_input, args.user_id, turn_count=turn_count)
            print(f"Agent: {response}\n")
            
            turn_count += 1

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}\n")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
