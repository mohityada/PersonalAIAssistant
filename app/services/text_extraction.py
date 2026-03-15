"""Text extraction from various document formats."""

import hashlib
import io
import logging

from pypdf import PdfReader
from docx import Document

logger = logging.getLogger(__name__)

# Supported text-based extensions
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"}

# Minimum pixel area for an extracted image to be worth processing
_MIN_IMAGE_AREA = 50 * 50


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


# ---------------------------------------------------------------------------
# PDF visual-layer helpers (pymupdf / fitz)
# ---------------------------------------------------------------------------


def extract_pdf_pages_as_images(file_bytes: bytes, dpi: int = 150) -> list:
    """Render each page of a PDF to a PIL Image using pymupdf (fitz).

    Args:
        file_bytes: Raw PDF bytes.
        dpi: Resolution for rendering. 150 balances quality vs. memory.

    Returns:
        List of PIL Images, one per page.
    """
    import fitz  # pymupdf
    from PIL import Image

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images: list = []
    zoom = dpi / 72  # fitz default is 72 DPI
    matrix = fitz.Matrix(zoom, zoom)

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        images.append(img)

    doc.close()
    logger.info("Rendered %d PDF pages as images (%d DPI)", len(images), dpi)
    return images


def extract_pdf_embedded_images(file_bytes: bytes) -> list:
    """Extract embedded images from a PDF via pymupdf xref objects.

    Deduplicates images by SHA-256 hash to avoid processing the same
    image multiple times (e.g. logos repeated on every page).

    Returns:
        List of unique PIL Images that exceed _MIN_IMAGE_AREA.
    """
    import fitz  # pymupdf
    from PIL import Image

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    seen_hashes: set[str] = set()
    images: list = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        image_list = page.get_images(full=True)

        for img_info in image_list:
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue
                img_bytes = base_image["image"]

                # Deduplicate
                digest = hashlib.sha256(img_bytes).hexdigest()
                if digest in seen_hashes:
                    continue
                seen_hashes.add(digest)

                img = Image.open(io.BytesIO(img_bytes))
                w, h = img.size
                if w * h < _MIN_IMAGE_AREA:
                    continue  # skip tiny icons / spacer pixels

                images.append(img.convert("RGB"))
            except Exception:
                logger.debug("Failed to extract image xref=%d on page %d", xref, page_num)
                continue

    doc.close()
    logger.info("Extracted %d unique embedded images from PDF", len(images))
    return images
