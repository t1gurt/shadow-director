"""
VERSION intent認識のデバッグテスト
"""
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agents.orchestrator import Orchestrator

def test_version_intent():
    """バージョンコマンドのintent認識をテスト"""
    
    print("=== VERSION Intent Debug Test ===\n")
    
    # Orchestratorを初期化
    try:
        orchestrator = Orchestrator()
        print("✅ Orchestrator initialized\n")
    except Exception as e:
        print(f"❌ Orchestrator initialization failed: {e}")
        return
    
    # テストメッセージ
    test_messages = [
        "バージョン",
        "あなたのバージョンを教えて",
        "version",
        "最新機能",
        "アップデート情報",
        "バージョン情報"
    ]
    
    print("Testing intent classification:\n")
    for msg in test_messages:
        try:
            intent = orchestrator._classify_intent(msg)
            print(f"Message: '{msg}'")
            print(f"  → Intent: {intent}")
            
            # 実際のルーティング結果も確認
            response = orchestrator.route_message(msg, "test_user_id")
            
            # レスポンスの最初の50文字を表示
            preview = response[:80].replace('\n', ' ')
            print(f"  → Response preview: {preview}...")
            print()
            
        except Exception as e:
            print(f"❌ Error for '{msg}': {e}\n")

if __name__ == "__main__":
    test_version_intent()
