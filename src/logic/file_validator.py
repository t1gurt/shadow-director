"""
File Validator - Validates downloaded grant files (SGNA Phase 4).

This module provides validation for downloaded grant files including:
- PDF text extraction and content verification
- ZIP file structure validation
- File freshness checking based on year/round numbers
"""

import logging
import re
import zipfile
import tempfile
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path


class FileValidator:
    """
    Validates downloaded grant files to ensure they are the correct version.
    Implements SGNA model validation loop.
    """
    
    # Keywords indicating valid grant documents
    GRANT_DOCUMENT_KEYWORDS = [
        '助成金', '補助金', '公募', '募集要項', '申請書',
        '様式', 'フォーマット', '応募', '交付', '支援'
    ]
    
    # Expected file patterns in grant ZIP archives
    EXPECTED_ZIP_CONTENTS = [
        r'申請書',
        r'計画書',
        r'様式',
        r'フォーマット',
        r'application',
        r'form'
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_pdf_content(
        self, 
        file_path: str, 
        expected_grant_name: str = None,
        expected_year: str = None,
        expected_round: str = None
    ) -> Dict[str, Any]:
        """
        Validate PDF content by extracting text and checking for expected keywords.
        
        Args:
            file_path: Path to the PDF file
            expected_grant_name: Expected grant name to match
            expected_year: Expected year (e.g., "2026")
            expected_round: Expected round number (e.g., "第19回")
            
        Returns:
            Validation result with score and reasons
        """
        result = {
            'valid': False,
            'score': 0,
            'reasons': [],
            'extracted_info': {}
        }
        
        try:
            # Try to extract text from PDF
            text = self._extract_pdf_text(file_path)
            
            if not text:
                result['reasons'].append("PDFからテキストを抽出できませんでした")
                return result
            
            # Normalize text for matching
            text_lower = text.lower()
            text_first_pages = text[:5000]  # First ~3 pages
            
            # Check for grant document keywords
            keyword_count = 0
            for keyword in self.GRANT_DOCUMENT_KEYWORDS:
                if keyword in text_first_pages:
                    keyword_count += 1
            
            if keyword_count >= 2:
                result['score'] += 30
                result['reasons'].append(f"助成金関連キーワード{keyword_count}個検出")
            
            # Check for expected grant name
            if expected_grant_name:
                name_parts = expected_grant_name.split()[:3]
                matches = sum(1 for part in name_parts if part.lower() in text_lower)
                if matches >= len(name_parts) // 2:
                    result['score'] += 30
                    result['reasons'].append("助成金名が一致")
            
            # Check for expected year
            if expected_year and expected_year in text_first_pages:
                result['score'] += 20
                result['reasons'].append(f"{expected_year}年度の文書")
                result['extracted_info']['year'] = expected_year
            
            # Check for round number
            if expected_round and expected_round in text_first_pages:
                result['score'] += 20
                result['reasons'].append(f"{expected_round}の公募")
                result['extracted_info']['round'] = expected_round
            
            # Extract actual year/round from document
            year_match = re.search(r'(202[4-9])年', text_first_pages)
            if year_match:
                result['extracted_info']['detected_year'] = year_match.group(1)
            
            round_match = re.search(r'第(\d+)回', text_first_pages)
            if round_match:
                result['extracted_info']['detected_round'] = f"第{round_match.group(1)}回"
            
            # Determine validity
            result['valid'] = result['score'] >= 50
            
        except Exception as e:
            self.logger.error(f"[FILE_VALIDATOR] PDF validation error: {e}")
            result['reasons'].append(f"検証エラー: {str(e)[:50]}")
        
        return result
    
    def validate_zip_content(
        self, 
        file_path: str,
        expected_file_count: int = 1
    ) -> Dict[str, Any]:
        """
        Validate ZIP file contents.
        
        Args:
            file_path: Path to the ZIP file
            expected_file_count: Minimum expected file count
            
        Returns:
            Validation result with file list
        """
        result = {
            'valid': False,
            'score': 0,
            'reasons': [],
            'contents': []
        }
        
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                file_list = zf.namelist()
                result['contents'] = file_list
                
                if len(file_list) == 0:
                    result['reasons'].append("ZIPファイルが空です")
                    return result
                
                if len(file_list) >= expected_file_count:
                    result['score'] += 20
                    result['reasons'].append(f"{len(file_list)}個のファイルを含む")
                
                # Check for expected file patterns
                matched_patterns = 0
                for pattern in self.EXPECTED_ZIP_CONTENTS:
                    for filename in file_list:
                        if re.search(pattern, filename, re.IGNORECASE):
                            matched_patterns += 1
                            break
                
                if matched_patterns > 0:
                    result['score'] += 30 * matched_patterns
                    result['reasons'].append(f"申請関連ファイル{matched_patterns}種類検出")
                
                # Check for document files (not just images/etc)
                doc_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx']
                doc_count = sum(1 for f in file_list 
                               if any(f.lower().endswith(ext) for ext in doc_extensions))
                
                if doc_count > 0:
                    result['score'] += 30
                    result['reasons'].append(f"文書ファイル{doc_count}個")
                
                result['valid'] = result['score'] >= 50
                
        except zipfile.BadZipFile:
            result['reasons'].append("無効なZIPファイル")
        except Exception as e:
            self.logger.error(f"[FILE_VALIDATOR] ZIP validation error: {e}")
            result['reasons'].append(f"検証エラー: {str(e)[:50]}")
        
        return result
    
    def _extract_pdf_text(self, file_path: str, max_pages: int = 3) -> Optional[str]:
        """
        Extract text from PDF file.
        
        Args:
            file_path: Path to PDF file
            max_pages: Maximum pages to extract
            
        Returns:
            Extracted text or None
        """
        try:
            # Try PyMuPDF (fitz) first - usually installed with Playwright
            import fitz
            
            text_parts = []
            with fitz.open(file_path) as doc:
                for page_num in range(min(max_pages, len(doc))):
                    page = doc[page_num]
                    text_parts.append(page.get_text())
            
            return '\n'.join(text_parts)
            
        except ImportError:
            self.logger.warning("[FILE_VALIDATOR] PyMuPDF not installed, trying pdfplumber")
            
            try:
                import pdfplumber
                
                text_parts = []
                with pdfplumber.open(file_path) as pdf:
                    for page_num in range(min(max_pages, len(pdf.pages))):
                        page = pdf.pages[page_num]
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                
                return '\n'.join(text_parts)
                
            except ImportError:
                self.logger.warning("[FILE_VALIDATOR] No PDF library available")
                return None
                
        except Exception as e:
            self.logger.error(f"[FILE_VALIDATOR] PDF extraction error: {e}")
            return None
    
    def validate_file_freshness(
        self, 
        file_path: str, 
        expected_year: str = "2026"
    ) -> Dict[str, Any]:
        """
        Check if a file appears to be from the expected year/period.
        
        Args:
            file_path: Path to file
            expected_year: Expected year string
            
        Returns:
            Freshness validation result
        """
        result = {
            'is_fresh': False,
            'detected_year': None,
            'reason': ''
        }
        
        path = Path(file_path)
        
        # Check filename for year
        if expected_year in path.name:
            result['is_fresh'] = True
            result['detected_year'] = expected_year
            result['reason'] = f"ファイル名に{expected_year}を含む"
            return result
        
        # For PDFs, check content
        if path.suffix.lower() == '.pdf':
            pdf_result = self.validate_pdf_content(file_path, expected_year=expected_year)
            if pdf_result.get('extracted_info', {}).get('year'):
                detected = pdf_result['extracted_info']['year']
                result['detected_year'] = detected
                result['is_fresh'] = detected == expected_year
                result['reason'] = f"文書内に{detected}年度の記載"
        
        return result
