import os
import re
import tempfile
from typing import List, Dict, Any, Optional
from google import genai
import requests

class FileProcessor:
    """
    Handles file uploads to Gemini API and processing of attachments and URLs.
    """
    def __init__(self, client: genai.Client):
        self.client = client
    
    def extract_urls(self, text: str) -> List[str]:
        """
        Extract URLs from text using regex.
        """
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        return re.findall(url_pattern, text)
    
    async def download_discord_attachment(self, attachment_url: str) -> tuple[bytes, str]:
        """
        Download a Discord attachment and return content + filename.
        
        Args:
            attachment_url: Discord CDN URL
            
        Returns:
            (file_content, filename)
        """
        response = requests.get(attachment_url)
        response.raise_for_status()
        
        # Extract filename from URL or Content-Disposition header
        filename = attachment_url.split('/')[-1].split('?')[0]
        
        return response.content, filename
    
    def create_part_from_bytes(self, file_content: bytes, filename: str, mime_type: str):
        """
        Create a Part object from file content for Vertex AI.
        
        Args:
            file_content: File bytes
            filename: Original filename
            mime_type: MIME type (e.g., 'application/pdf')
            
        Returns:
            Part object with inline data
        """
        from google.genai.types import Part
        
        print(f"[DEBUG] Creating Part from file: {filename} ({mime_type}, {len(file_content)} bytes)")
        
        try:
            # For Vertex AI, create Part with inline_data
            part = Part(
                inline_data={
                    "mime_type": mime_type,
                    "data": file_content
                }
            )
            print(f"[DEBUG] Successfully created Part for: {filename}")
            return part
        except Exception as e:
            print(f"[ERROR] Failed to create Part: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def get_mime_type(self, filename: str) -> str:
        """
        Determine MIME type from filename extension.
        """
        ext = filename.lower().split('.')[-1]
        mime_types = {
            'pdf': 'application/pdf',
            'txt': 'text/plain',
            'md': 'text/markdown',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'webp': 'image/webp',
            'gif': 'image/gif',
        }
        return mime_types.get(ext, 'application/octet-stream')
    
    async def process_discord_attachments(self, attachments: List[Any]) -> List[Any]:
        """
        Process Discord message attachments and create Part objects for Vertex AI.
        
        Args:
            attachments: Discord message attachments list
            
        Returns:
            List of Part objects
        """
        uploaded_files = []
        
        print(f"[DEBUG] Processing {len(attachments)} Discord attachments")
        
        for i, attachment in enumerate(attachments, 1):
            try:
                print(f"[DEBUG] Processing attachment {i}/{len(attachments)}: {attachment.filename}")
                
                # Download from Discord CDN
                print(f"[DEBUG]   Downloading from: {attachment.url}")
                content, filename = await self.download_discord_attachment(attachment.url)
                print(f"[DEBUG]   Downloaded {len(content)} bytes")
                
                # Determine MIME type
                mime_type = self.get_mime_type(filename)
                print(f"[DEBUG]   MIME type: {mime_type}")
                
                # Create Part for Vertex AI
                part = self.create_part_from_bytes(content, filename, mime_type)
                uploaded_files.append(part)
                
                print(f"[DEBUG] ✓ Successfully processed: {filename}")
            except Exception as e:
                print(f"[ERROR] Failed to process attachment {attachment.filename}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"[DEBUG] Completed processing: {len(uploaded_files)}/{len(attachments)} files uploaded")
        return uploaded_files
