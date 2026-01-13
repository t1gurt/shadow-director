import os
import subprocess
import logging
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

def convert_to_pdf(input_path: str, output_dir: Optional[str] = None) -> Optional[str]:
    """
    Converts an Office document (Word, Excel) to PDF using LibreOffice.
    Supports .doc, .docx, .xls, .xlsx.
    
    Args:
        input_path: Absolute path to the input file
        output_dir: Directory to save the PDF (default: same as input)
        
    Returns:
        Path to the generated PDF file, or None if conversion failed.
    """
    if not os.path.exists(input_path):
        logger.error(f"[OFFICE_UTILS] File not found: {input_path}")
        return None
        
    if output_dir is None:
        output_dir = os.path.dirname(input_path)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Check for LibreOffice command
    # Windows: likely 'soffice' or full path. On standard Windows installs it might not be in PATH.
    # We assume 'soffice' provided by the user in Docker/WSL or in PATH.
    # Note: If running on Windows host without LibreOffice in PATH, this will fail.
    # But user's environment seems to include WSL/Docker where it might be available.
    
    soffice_cmd = shutil.which("soffice") or shutil.which("libreoffice")
    
    # Try common Windows paths if not found
    if not soffice_cmd and os.name == 'nt':
        common_paths = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"
        ]
        for p in common_paths:
            if os.path.exists(p):
                soffice_cmd = p
                break
                
    if not soffice_cmd:
        logger.error("[OFFICE_UTILS] LibreOffice (soffice) not found. Please install LibreOffice.")
        return None

    try:
        # Construct command: soffice --headless --convert-to pdf --outdir <dir> <file>
        cmd = [
            soffice_cmd,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", output_dir,
            input_path
        ]
        
        logger.info(f"[OFFICE_UTILS] Running conversion: {' '.join(cmd)}")
        
        # On Windows, we might need shell=True for some command execution depending on how it's installed
        # But subprocess.run with list args usually works better without shell=True
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if result.returncode != 0:
            logger.error(f"[OFFICE_UTILS] Conversion failed with code {result.returncode}: {result.stderr}")
            return None
            
        # Expected output filename
        filename = os.path.basename(input_path)
        name_without_ext = os.path.splitext(filename)[0]
        pdf_path = os.path.join(output_dir, f"{name_without_ext}.pdf")
        
        if os.path.exists(pdf_path):
            logger.info(f"[OFFICE_UTILS] PDF generated: {pdf_path}")
            return pdf_path
        else:
            logger.error(f"[OFFICE_UTILS] PDF conversion reported success but file not found: {pdf_path}")
            return None
            
    except Exception as e:
        logger.error(f"[OFFICE_UTILS] Exception during PDF conversion: {e}")
        return None
