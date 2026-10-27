"""Validate and inspect CVs before starting an expensive search."""
from pathlib import Path
from tempfile import TemporaryDirectory

from app.tools.document_parser import extract_text

MAX_CV_BYTES = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def inspect_cv(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError("Choose a PDF, DOCX, TXT or Markdown CV.")
    if not content:
        raise ValueError("This file is empty. Choose a CV with readable text.")
    if len(content) > MAX_CV_BYTES:
        raise ValueError("This CV is larger than 10 MB. Export a smaller copy and try again.")
    try:
        with TemporaryDirectory(prefix="jobforge-inspect-") as temp:
            path = Path(temp) / f"cv{suffix}"
            path.write_bytes(content)
            text = extract_text(str(path)).strip()
    except Exception as exc:
        raise ValueError("We couldn't read this CV. Try a text-based PDF, DOCX or TXT file; scanned PDFs need OCR first.") from exc
    if len(text) < 40:
        raise ValueError("This CV has too little readable text. Upload a complete CV or a text-based export.")
    return text
