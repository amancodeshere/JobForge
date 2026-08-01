from __future__ import annotations

from pathlib import Path


class DocumentParseError(RuntimeError):
    pass


def extract_text(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise DocumentParseError(f"CV file not found: {path}")

    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        return _extract_pdf(file_path)
    if suffix == ".docx":
        return _extract_docx(file_path)

    raise DocumentParseError(f"Unsupported CV format: {suffix or 'no extension'}")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentParseError("Install pypdf to parse PDF files.") from exc

    reader = PdfReader(str(path))
    chunks = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(chunks).strip()
    if not text:
        raise DocumentParseError("PDF text extraction returned no content.")
    return text


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise DocumentParseError("Install python-docx to parse DOCX files.") from exc

    document = Document(str(path))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
    if not text:
        raise DocumentParseError("DOCX text extraction returned no content.")
    return text

