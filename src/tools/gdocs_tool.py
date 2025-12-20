import os
from datetime import datetime
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class GoogleDocsTool:
    """
    Google Docs Tool.
    Uses Google Docs API if credentials are available, otherwise falls back to local drafts.
    """
    def __init__(self, output_dir: str = "drafts"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        self.service = self._init_service()

    def _init_service(self):
        try:
            # Scopes for Google Docs
            SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
            creds, _ = google.auth.default(scopes=SCOPES)
            return build('docs', 'v1', credentials=creds)
        except Exception as e:
            print(f"Warning: Could not initialize Google Docs API ({e}). Using local fallback.")
            return None

    def create_document(self, title: str, content: str) -> str:
        """
        Creates a Google Doc if service is available, otherwise a local file.
        """
        if self.service:
            return self._create_cloud_doc(title, content)
        else:
            return self._create_local_doc(title, content)

    def _create_cloud_doc(self, title: str, content: str) -> str:
        try:
            # 1. Create blank doc
            doc_body = {'title': title}
            doc = self.service.documents().create(body=doc_body).execute()
            doc_id = doc.get('documentId')
            
            # 2. Insert content
            # Note: Index 1 is usually start of body
            requests = [
                {
                    'insertText': {
                        'location': {
                            'index': 1,
                        },
                        'text': content
                    }
                }
            ]
            self.service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
            
            url = f"https://docs.google.com/document/d/{doc_id}/edit"
            print(f"Google Doc created: {url}")
            return f"Google Doc created: {url}"
            
        except HttpError as err:
            print(f"An error occurred: {err}")
            return self._create_local_doc(title, content + "\n\n(Fallback: API Error)")

    def _create_local_doc(self, title: str, content: str) -> str:
        """
        Creates a local markdown file with the content.
        Returns the file path.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        filename = f"{safe_title}_{timestamp}.md"
        file_path = os.path.join(self.output_dir, filename)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n")
                f.write(content)
            return f"Draft saved locally: {file_path}"
        except Exception as e:
            print(f"Error creating document: {e}")
            return "Error creating draft."
