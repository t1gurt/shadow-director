from typing import Dict, Any, Optional
import yaml
import os
from google import genai
from google.genai.types import HttpOptions
from src.tools.gdocs_tool import GoogleDocsTool
from src.memory.profile_manager import ProfileManager

class DrafterAgent:
    def __init__(self):
        self.config = self._load_config()
        self.system_prompt = self.config.get("system_prompts", {}).get("drafter", "")
        
        # Initialize Google Gen AI Client
        project_id = self.config.get("model_config", {}).get("project_id")
        location = self.config.get("model_config", {}).get("location", "us-central1")
        
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        
        try:
            self.client = genai.Client(http_options=HttpOptions(api_version="v1beta1"))
        except Exception as e:
            print(f"Failed to init GenAI client: {e}")
            self.client = None
            
        # Using Interviewer model (Pro) for drafting as it requires high reasoning/writing capability
        # Or we can define a separate drafter_model in config if needed. 
        # For now, reusing interviewer_model or defaulting to gemini-2.5-pro
        self.model_name = self.config.get("model_config", {}).get("interviewer_model")
        if not self.model_name:
             raise ValueError("interviewer_model (for drafter) not found in config")
        self.docs_tool = GoogleDocsTool()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def _research_grant_format(self, grant_name: str) -> str:
        """
        Researches the grant application format using Google Search Grounding.
        
        Args:
            grant_name: Name of the grant to research
            
        Returns:
            Application format information (questions, requirements, etc.)
        """
        import logging
        from google.genai.types import GenerateContentConfig, Tool, GoogleSearch
        
        logging.info(f"[DRAFTER] Researching format for: {grant_name}")
        
        research_prompt = f"""
以下の助成金の申請書フォーマット（質問項目・記入欄）を調査してください。

助成金名: {grant_name}

調査すべき内容:
1. 申請書の質問項目（例：団体概要、事業計画、予算など）
2. 各項目の文字数制限や記入例
3. 審査のポイント・評価基準
4. 必要な添付書類

出力形式:
## 申請書フォーマット

### 質問項目
1. [項目名] （文字数制限があれば記載）
2. [項目名] （文字数制限があれば記載）
...

### 審査ポイント
- [ポイント1]
- [ポイント2]

### 必要書類
- [書類1]
- [書類2]

※見つからない場合は一般的な助成金申請書の形式を想定してください。
"""
        
        try:
            # Use Google Search Grounding for format research
            google_search_tool = Tool(google_search=GoogleSearch())
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=research_prompt,
                config=GenerateContentConfig(
                    tools=[google_search_tool],
                    temperature=0.3
                )
            )
            
            format_info = response.text
            logging.info(f"[DRAFTER] Format research completed, length: {len(format_info)} chars")
            return format_info
            
        except Exception as e:
            logging.error(f"[DRAFTER] Format research failed: {e}")
            # Return generic format as fallback
            return """
## 申請書フォーマット（一般的な形式）

### 質問項目
1. 団体概要（400字程度）
2. 事業の目的と背景（600字程度）
3. 具体的な活動計画
4. 期待される成果・効果
5. 予算計画
6. 今後の展望

### 審査ポイント
- 社会的意義と必要性
- 実現可能性
- 団体の実績と信頼性
- 費用対効果
"""

    def create_draft(self, user_id: str, grant_info: str) -> tuple[str, str, str]:
        """
        Generates a grant application draft based on researched format.
        
        Returns:
            tuple: (message, draft_content, filename)
        """
        import logging
        logging.info(f"[DRAFTER] create_draft started for user: {user_id}")
        
        pm = ProfileManager(user_id=user_id)
        profile = pm.get_profile_context()
        
        logging.info(f"[DRAFTER] Profile loaded, length: {len(profile)} chars")
        
        # Extract grant name from grant_info for format research
        grant_name = grant_info.strip()
        # Try to extract just the grant name if it contains other info
        if "助成" in grant_name:
            # Find the grant name pattern
            import re
            match = re.search(r'[^\s]+助成[^\s]*', grant_name)
            if match:
                grant_name = match.group(0)
        
        # Step 1: Research the application format
        logging.info(f"[DRAFTER] Step 1: Researching format for '{grant_name}'")
        format_info = self._research_grant_format(grant_name)
        
        # Step 2: Generate draft based on format
        logging.info(f"[DRAFTER] Step 2: Generating format-aware draft")
        
        full_prompt = f"""
{self.system_prompt}

# Soul Profile（魂のプロファイル）
{profile}

# 対象助成金
{grant_info}

# 申請書フォーマット情報
{format_info}

# タスク
上記の申請書フォーマットに従って、各質問項目に対する回答を作成してください。

**重要な指示:**
1. フォーマット情報の質問項目ごとに見出しを付けて回答を作成
2. 文字数制限がある場合はそれに収まるように調整
3. Soul Profileの情報を最大限活用
4. 各回答の後に簡単な📝記入のポイントを追記

**出力形式:**
# [助成金名] 申請書ドラフト

## 1. [質問項目1]
[回答内容]
📝 ポイント: [この項目で強調すべき点]

## 2. [質問項目2]
[回答内容]
📝 ポイント: [この項目で強調すべき点]

...

---
## 📋 全体の考慮点
[申請全体で気をつけるべき点]

## 🌟 アピールポイント
[特に強調すべき団体の強み]

## ⚠️ 懸念点・改善提案
[申請で弱くなりそうな点と対策]
"""
        try:
            logging.info(f"[DRAFTER] Calling Gemini model: {self.model_name}")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            draft_content = response.text
            logging.info(f"[DRAFTER] Draft generated, length: {len(draft_content)} chars")
            
            # Extract a title (first line or generic)
            lines = draft_content.split('\n')
            title = "Grant_Draft"
            if lines and lines[0].startswith('# '):
                 title = lines[0].replace('# ', '').strip()
            
            logging.info(f"[DRAFTER] Title: {title}")
            
            file_path = self.docs_tool.create_document(title, draft_content, user_id=user_id)
            logging.info(f"[DRAFTER] Document saved: {file_path}")
            
            # Extract filename from path
            import os
            if 'gs://' in file_path:
                # GCS path: gs://bucket/drafts/user_id/filename.md
                filename = file_path.split('/')[-1]
            elif 'Google Doc' in file_path:
                # Google Docs: extract from message
                filename = f"{title}.md"
            else:
                # Local path
                filename = os.path.basename(file_path)
            
            logging.info(f"[DRAFTER] Filename: {filename}")
            
            message = f"ドラフトを作成しました: {file_path}"
            
            logging.info(f"[DRAFTER] create_draft completed successfully")
            return (message, draft_content, filename)
            
        except Exception as e:
            logging.error(f"[DRAFTER] Error in create_draft: {e}", exc_info=True)
            error_msg = f"ドラフト作成エラー: {e}"
            return (error_msg, "", "")


    def list_drafts(self, user_id: str) -> str:
        """
        Lists all drafts for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Formatted list of drafts or message if none found
        """
        try:
            drafts = self.docs_tool.list_drafts(user_id)
            
            if not drafts:
                return "まだドラフトが作成されていません。「助成金申請書を書いて」とリクエストしてください。"
            
            result = f"📄 **保存済みドラフト一覧** ({len(drafts)}件)\n\n"
            for i, filename in enumerate(drafts, 1):
                result += f"{i}. `{filename}`\n"
            
            result += "\n💡 特定のドラフトを見るには「[ファイル名]を見せて」または「最新のドラフトを見せて」と送信してください。"
            
            return result
            
        except Exception as e:
            return f"ドラフト一覧取得エラー: {e}"

    def clear_drafts(self, user_id: str) -> str:
        """
        Clears all drafts for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Success message
        """
        try:
            return self.docs_tool.clear_drafts(user_id)
        except Exception as e:
            return f"ドラフトクリアエラー: {e}"

    def get_latest_draft(self, user_id: str) -> tuple[str, Optional[str]]:
        """
        Gets the latest draft for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Tuple of (message, content). If content is present, it should be sent as attachment.
        """
        try:
            drafts = self.docs_tool.list_drafts(user_id)
            
            if not drafts:
                return ("まだドラフトが作成されていません。", None)
            
            # Sort by filename (which includes timestamp)
            latest_draft = sorted(drafts)[-1]
            content = self.docs_tool.get_draft(user_id, latest_draft)
            
            if not content:
                return (f"ドラフト '{latest_draft}' が見つかりませんでした。", None)
            
            message = f"📄 **最新のドラフト**: `{latest_draft}`\n\n"
            
            # If content is short, include it in message
            if len(content) <= 1800:
                message += f"```markdown\n{content}\n```"
                return (message, None)
            else:
                # Return content for file attachment
                message += "（ファイルとして送信します）"
                return (message, content)
                
        except Exception as e:
            return (f"最新ドラフト取得エラー: {e}", None)

    def get_draft(self, user_id: str, filename: str) -> tuple[str, Optional[str]]:
        """
        Gets a specific draft by filename.
        
        Args:
            user_id: User ID
            filename: Draft filename
            
        Returns:
            Tuple of (message, content). If content is present, it should be sent as attachment.
        """
        try:
            content = self.docs_tool.get_draft(user_id, filename)
            
            if not content:
                # Try fuzzy match
                drafts = self.docs_tool.list_drafts(user_id)
                matches = [d for d in drafts if filename.lower() in d.lower()]
                
                if matches:
                    if len(matches) == 1:
                        # Use the matched file
                        filename = matches[0]
                        content = self.docs_tool.get_draft(user_id, filename)
                    else:
                        suggestion = "\n\n候補:\n" + "\n".join([f"- {m}" for m in matches])
                        return (f"ファイル名が曖昧です。{suggestion}", None)
                else:
                    return (f"ドラフト '{filename}' が見つかりませんでした。「ドラフト一覧」で確認してください。", None)
            
            message = f"📄 **ドラフト**: `{filename}`\n\n"
            
            # If content is short, include it in message
            if len(content) <= 1800:
                message += f"```markdown\n{content}\n```"
                return (message, None)
            else:
                # Return content for file attachment
                message += "（ファイルとして送信します）"
                return (message, content)
                
        except Exception as e:
            return (f"ドラフト取得エラー: {e}", None)

