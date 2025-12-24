import os
from datetime import datetime
from typing import Optional

try:
    from google.cloud import storage
except ImportError:
    storage = None

try:
    import google.auth
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    google = None
    build = None
    HttpError = None


class GoogleDocsTool:
    """
    Google Docs Tool.
    Production: Saves to GCS (gs://bucket/drafts/user_id/...)
    Google Docs API: Uses Google Docs API if credentials are available
    Local: Falls back to local drafts folder
    """
    def __init__(self, output_dir: str = "drafts"):
        self.output_dir = output_dir
        self.env = os.getenv("APP_ENV", "local")
        
        # Initialize GCS for production
        self.gcs_bucket = None
        if self.env == "production":
            bucket_name = os.getenv("GCS_BUCKET_NAME")
            if bucket_name and storage:
                try:
                    client = storage.Client()
                    self.gcs_bucket = client.bucket(bucket_name)
                    print(f"GCS initialized for drafts: gs://{bucket_name}/drafts/")
                except Exception as e:
                    print(f"Warning: Could not initialize GCS ({e}). Falling back to local.")
        
        # Initialize Google Docs API (optional)
        self.docs_service = self._init_docs_service()
        
        # Ensure local output dir exists for fallback
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def _init_docs_service(self):
        """Initialize Google Docs API service if available."""
        if not build:
            return None
        try:
            SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
            creds, _ = google.auth.default(scopes=SCOPES)
            return build('docs', 'v1', credentials=creds)
        except Exception as e:
            print(f"Warning: Could not initialize Google Docs API ({e}).")
            return None

    def create_document(self, title: str, content: str, user_id: str = "default") -> str:
        """
        Creates a document using the best available method.
        Priority: GCS (production) > Google Docs API > Local file
        
        Args:
            title: Document title
            content: Document content (markdown)
            user_id: User ID for organizing drafts
            
        Returns:
            Success message with file location/URL
        """
        # Production: Use GCS
        if self.gcs_bucket:
            return self._create_gcs_doc(title, content, user_id)
        
        # Try Google Docs API
        if self.docs_service:
            return self._create_google_doc(title, content)
        
        # Fallback: Local file
        return self._create_local_doc(title, content)

    def _create_gcs_doc(self, title: str, content: str, user_id: str) -> str:
        """Creates a draft in Google Cloud Storage."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        filename = f"{safe_title}_{timestamp}.md"
        blob_path = f"drafts/{user_id}/{filename}"
        
        try:
            blob = self.gcs_bucket.blob(blob_path)
            full_content = f"# {title}\n\n{content}"
            blob.upload_from_string(full_content, content_type="text/markdown; charset=utf-8")
            
            gcs_url = f"gs://{self.gcs_bucket.name}/{blob_path}"
            print(f"Draft saved to GCS: {gcs_url}")
            return f"GCSに保存: {gcs_url}"
            
        except Exception as e:
            print(f"Error saving to GCS: {e}. Falling back to local.")
            return self._create_local_doc(title, content)

    def _create_google_doc(self, title: str, content: str) -> str:
        """Creates a Google Doc using the Docs API."""
        try:
            doc_body = {'title': title}
            doc = self.docs_service.documents().create(body=doc_body).execute()
            doc_id = doc.get('documentId')
            
            requests = [
                {
                    'insertText': {
                        'location': {'index': 1},
                        'text': content
                    }
                }
            ]
            self.docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
            
            url = f"https://docs.google.com/document/d/{doc_id}/edit"
            print(f"Google Doc created: {url}")
            return f"Google Docを作成: {url}"
            
        except Exception as err:
            print(f"Google Docs API error: {err}")
            return self._create_local_doc(title, content + "\n\n(Fallback: API Error)")

    def _create_local_doc(self, title: str, content: str) -> str:
        """Creates a local markdown file (fallback)."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        filename = f"{safe_title}_{timestamp}.md"
        file_path = os.path.join(self.output_dir, filename)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n")
                f.write(content)
            print(f"Draft saved locally: {file_path}")
            return f"ローカルに保存: {file_path}"
        except Exception as e:
            print(f"Error creating local document: {e}")
            return f"ドラフト作成エラー: {e}"

    def get_draft(self, user_id: str, filename: str) -> Optional[str]:
        """
        Retrieves a draft by filename.
        
        Args:
            user_id: User ID
            filename: Draft filename
            
        Returns:
            Draft content or None if not found
        """
        # Try GCS first
        if self.gcs_bucket:
            try:
                blob_path = f"drafts/{user_id}/{filename}"
                blob = self.gcs_bucket.blob(blob_path)
                if blob.exists():
                    return blob.download_as_text()
            except Exception as e:
                print(f"Error reading from GCS: {e}")
        
        # Fallback to local
        local_path = os.path.join(self.output_dir, filename)
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                return f.read()
        
        return None

    def list_drafts(self, user_id: str) -> list:
        """
        Lists all drafts for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of draft filenames
        """
        drafts = []
        
        # Try GCS first
        if self.gcs_bucket:
            try:
                prefix = f"drafts/{user_id}/"
                blobs = self.gcs_bucket.list_blobs(prefix=prefix)
                for blob in blobs:
                    # Extract filename from path
                    filename = blob.name.replace(prefix, "")
                    if filename:
                        drafts.append(filename)
            except Exception as e:
                print(f"Error listing GCS drafts: {e}")
        
        # Also check local (for development)
        if os.path.exists(self.output_dir):
            local_files = [f for f in os.listdir(self.output_dir) if f.endswith('.md')]
            for f in local_files:
                if f not in drafts:
                    drafts.append(f)
        
        return drafts
