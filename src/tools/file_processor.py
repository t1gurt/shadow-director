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
        # Vertex AI supported MIME types
        # Reference: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini
        mime_types = {
            # Documents
            'pdf': 'application/pdf',
            'txt': 'text/plain',
            'md': 'text/markdown',
            'html': 'text/html',
            'htm': 'text/html',
            'css': 'text/css',
            'js': 'application/javascript',
            'py': 'text/x-python',
            'json': 'application/json',
            'xml': 'application/xml',
            'csv': 'text/csv',
            
            # Images
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'webp': 'image/webp',
            'gif': 'image/gif',
            'heic': 'image/heic',
            'heif': 'image/heif',
            
            # Audio
            'wav': 'audio/wav',
            'mp3': 'audio/mp3',
            'aiff': 'audio/aiff',
            'aac': 'audio/aac',
            'ogg': 'audio/ogg',
            'flac': 'audio/flac',
            
            # Video
            'mp4': 'video/mp4',
            'mpeg': 'video/mpeg',
            'mpg': 'video/mpeg',
            'mov': 'video/mov',
            'avi': 'video/avi',
            'flv': 'video/x-flv',
            'webm': 'video/webm',
            'wmv': 'video/x-ms-wmv',
            '3gp': 'video/3gpp',
            '3gpp': 'video/3gpp',
        }
        if ext not in mime_types:
            supported_formats = ', '.join(sorted(set(mime_types.keys())))
            raise ValueError(
                f"ファイル形式 '.{ext}' はサポートされていません。\n"
                f"サポートされている形式: {supported_formats}\n"
                f"ファイル名: {filename}"
            )
        
        return mime_types[ext]
    
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
