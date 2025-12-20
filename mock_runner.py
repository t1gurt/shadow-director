import argparse
import sys
import time
from src.agents.orchestrator import Orchestrator
from src.agents.observer import ObserverAgent

def main():
    parser = argparse.ArgumentParser(description="Mock Runner for NPO-SoulSync")
    parser.add_argument("--mode", choices=["interviewer", "observer", "drafter", "routing_test"], default="interviewer", help="Agent mode to run")
    parser.add_argument("--user-id", default="mock_user_123", help="Mock User ID")
    parser.add_argument("--grant-info", default="", help="Grant info for drafter mode")
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
            # ... (rest of observer logic)
            print("Searching for funding opportunities based on Soul Profile...")
            time.sleep(1)
            result = observer.observe(user_id=args.user_id)
            print("\n[Observer Result]")
            print(result)
        except Exception as e:
            print(f"Error in Observer mode: {e}")
        return

    if args.mode == "drafter":
        print("Initializing Drafter Agent...")
        try:
            from src.agents.drafter import DrafterAgent
            drafter = DrafterAgent()
            print("Drafter initialized.")
            
            # Use provided grant info or a default mock
            grant_info = args.grant_info
            if not grant_info:
                grant_info = "Mock Grant: Innovation for Animal Welfare. Max Budget: 1M JPY. Requirement: New solution for stray cats."
            
            print(f"Creating draft for: {grant_info}")
            time.sleep(1)
            
            result = drafter.create_draft(user_id=args.user_id, grant_info=grant_info)
            print("\n[Drafter Result]")
            print(result)
        except Exception as e:
            print(f"Error in Drafter mode: {e}")
        return

    if args.mode == "routing_test":
        print("Initializing Orchestrator for Routing Test...")
        orchestrator = Orchestrator()
        
        test_inputs = [
            "こんにちは、調子はどう？",  # Interview
            "猫の保護活動をしています。", # Interview
            "この助成金の申請書を書いてください。", # Draft
            "Draft a proposal for the Innovation Grant.", # Draft
            "資金調達について相談したい" # Interview
        ]
        
        print("\n--- Starting Routing Test ---")
        for inp in test_inputs:
            print(f"\nUser Input: {inp}")
            # We peek into private method or just run route_message and check output
            # For test, we can just run route_message (which prints intent) or use _classify_intent directly if we want just label.
            # Let's use _classify_intent for clear verification output.
            intent = orchestrator._classify_intent(inp)
            print(f"Classified Intent: {intent}")
            
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
