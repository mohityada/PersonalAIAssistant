"""Text extraction from various document formats."""

import io
import logging

from PyPDF2 import PdfReader
from docx import Document

logger = logging.getLogger(__name__)

# Supported text-based extensions
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"}


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from a document file.

    Supported formats: PDF, DOCX, TXT, MD, and other plain-text files.

    Returns:
        Extracted text content as a single string.

    Raises:
        ValueError: If the file format is not supported.
    """
    lower = filename.lower()

    if lower.endswith(".pdf"):
        return _extract_pdf(file_bytes)
    elif lower.endswith(".docx"):
        return _extract_docx(file_bytes)
    elif any(lower.endswith(ext) for ext in TEXT_EXTENSIONS):
        return _extract_plain(file_bytes)
    else:
        raise ValueError(f"Unsupported file format: {filename}")


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF file."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    result = "\n\n".join(pages)
    logger.info("Extracted %d chars from PDF (%d pages)", len(result), len(reader.pages))
    return result


def _extract_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX file."""
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    result = "\n\n".join(paragraphs)
    logger.info("Extracted %d chars from DOCX (%d paragraphs)", len(result), len(paragraphs))
    return result


def _extract_plain(file_bytes: bytes) -> str:
    """Read plain-text files as UTF-8."""
    result = file_bytes.decode("utf-8", errors="replace")
    logger.info("Read %d chars from plain-text file", len(result))
    return result
