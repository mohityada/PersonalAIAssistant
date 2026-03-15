"""Tests for the unified PDF ingestion pipeline."""

import uuid
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakeChunkData:
    text: str
    index: int


def _make_file_record(**overrides):
    """Build a minimal fake File ORM object."""
    defaults = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "original_filename": "report.pdf",
        "file_type": "pdf",
        "file_path": "uploads/report.pdf",
        "location": None,
        "tags": ["finance"],
        "status": "processing",
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# text_extraction — PDF visual layer helpers
# ---------------------------------------------------------------------------


class TestExtractPdfPagesAsImages:
    @patch("app.services.text_extraction.fitz")
    def test_renders_pages(self, mock_fitz):
        from app.services.text_extraction import extract_pdf_pages_as_images

        # Simulate a 2-page PDF
        mock_pix = MagicMock()
        mock_pix.width = 100
        mock_pix.height = 100
        mock_pix.samples = b"\x00" * (100 * 100 * 3)

        mock_page = MagicMock()
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)
        mock_doc.load_page.return_value = mock_page
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        images = extract_pdf_pages_as_images(b"fake-pdf-bytes", dpi=72)
        assert len(images) == 2
        mock_doc.close.assert_called_once()


class TestExtractPdfEmbeddedImages:
    @patch("app.services.text_extraction.fitz")
    def test_deduplicates_images(self, mock_fitz):
        from app.services.text_extraction import extract_pdf_embedded_images

        # Two pages returning the same image xref
        identical_bytes = b"\x89PNG" + b"\x00" * 500
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)

        mock_page = MagicMock()
        mock_page.get_images.return_value = [(1, 0, 0, 0, 0, 0, 0)]
        mock_doc.load_page.return_value = mock_page
        mock_doc.extract_image.return_value = {
            "image": identical_bytes,
            "ext": "png",
        }
        mock_fitz.open.return_value = mock_doc

        with patch("app.services.text_extraction.Image") as mock_image_mod:
            fake_img = MagicMock()
            fake_img.size = (200, 200)
            fake_img.convert.return_value = fake_img
            mock_image_mod.open.return_value = fake_img

            images = extract_pdf_embedded_images(b"fake-pdf")
            # Same image on 2 pages → deduplicated to 1
            assert len(images) == 1


# ---------------------------------------------------------------------------
# image_processing — OCR + PDF image pipeline
# ---------------------------------------------------------------------------


class TestRunOcrOnImage:
    @patch("app.services.image_processing._get_ocr_reader")
    def test_returns_text(self, mock_get_reader):
        from app.services.image_processing import run_ocr_on_image
        from PIL import Image

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = ["Hello", "World"]
        mock_get_reader.return_value = mock_reader

        img = Image.new("RGB", (100, 100), "white")
        result = run_ocr_on_image(img)
        assert "Hello" in result
        assert "World" in result

    @patch("app.services.image_processing._get_ocr_reader", side_effect=ImportError)
    def test_returns_empty_on_import_error(self, _):
        from app.services.image_processing import run_ocr_on_image
        from PIL import Image

        img = Image.new("RGB", (50, 50))
        assert run_ocr_on_image(img) == ""


class TestProcessPdfImage:
    @patch("app.services.image_processing.run_ocr_on_image", return_value="Invoice #123")
    @patch("app.services.image_processing._generate_blip_caption", return_value="A table with numbers")
    @patch("app.services.image_processing._detect_objects", return_value=["table"])
    def test_returns_all_fields(self, _det, _cap, _ocr):
        from app.services.image_processing import process_pdf_image
        from PIL import Image

        img = Image.new("RGB", (200, 200))
        result = process_pdf_image(img)
        assert result.caption == "A table with numbers"
        assert result.objects == ["table"]
        assert result.ocr_text == "Invoice #123"


# ---------------------------------------------------------------------------
# tasks — _ingest_pdf_sync routing
# ---------------------------------------------------------------------------


class TestPdfRouting:
    def test_is_pdf(self):
        from app.workers.tasks import _is_pdf

        assert _is_pdf("report.pdf") is True
        assert _is_pdf("Report.PDF") is True
        assert _is_pdf("doc.docx") is False
        assert _is_pdf("photo.jpg") is False

    def test_is_not_image(self):
        from app.workers.tasks import _is_image

        assert _is_image("report.pdf") is False


class TestIngestPdfSync:
    @patch("app.workers.tasks.VectorStoreManager")
    @patch("app.workers.tasks.EmbeddingModelManager")
    @patch("app.workers.tasks.run_ocr_on_image", return_value="")
    @patch("app.workers.tasks.detect_figures_and_crop", return_value=[])
    @patch("app.workers.tasks.extract_pdf_embedded_images", return_value=[])
    @patch("app.workers.tasks.extract_pdf_pages_as_images", return_value=[])
    @patch("app.workers.tasks.chunk_text")
    @patch("app.workers.tasks.extract_text", return_value="Hello world. This is a test document.")
    def test_text_only_pdf(
        self, mock_extract, mock_chunk, mock_pages, mock_embedded,
        mock_crops, mock_ocr, mock_embedder_cls, mock_vs_cls,
    ):
        from app.workers.tasks import _ingest_pdf_sync

        mock_chunk.return_value = [_FakeChunkData(text="Hello world.", index=0)]

        mock_embedder = MagicMock()
        mock_embedder.encode.return_value = [[0.1] * 384]
        mock_embedder_cls.return_value = mock_embedder

        mock_vs = MagicMock()
        session = MagicMock()
        file_record = _make_file_record()

        result = _ingest_pdf_sync(session, file_record, b"fake-pdf", mock_vs)

        assert result["status"] == "complete"
        assert result["chunks"] == 1
        assert result["text_chunks"] == 1
        assert result["ocr_chunks"] == 0
        assert result["caption_chunks"] == 0
        session.add_all.assert_called_once()
        session.commit.assert_called()
        mock_vs.upsert_vectors.assert_called_once()

    @patch("app.workers.tasks.VectorStoreManager")
    @patch("app.workers.tasks.EmbeddingModelManager")
    @patch("app.workers.tasks.process_pdf_image")
    @patch("app.workers.tasks.run_ocr_on_image", return_value="Scanned paragraph text")
    @patch("app.workers.tasks.detect_figures_and_crop", return_value=[])
    @patch("app.workers.tasks.extract_pdf_embedded_images", return_value=[])
    @patch("app.workers.tasks.extract_pdf_pages_as_images")
    @patch("app.workers.tasks.chunk_text")
    @patch("app.workers.tasks.extract_text", return_value="")
    def test_scanned_pdf_with_ocr(
        self, mock_extract, mock_chunk, mock_pages, mock_embedded,
        mock_crops, mock_ocr, mock_process, mock_embedder_cls, mock_vs_cls,
    ):
        """A scanned PDF with no text layer should still produce OCR chunks."""
        from PIL import Image
        from app.workers.tasks import _ingest_pdf_sync

        fake_page = Image.new("RGB", (100, 100))
        mock_pages.return_value = [fake_page]
        mock_chunk.return_value = []  # no text chunks from empty text

        mock_embedder = MagicMock()
        mock_embedder.encode.return_value = [[0.1] * 384]
        mock_embedder_cls.return_value = mock_embedder

        mock_vs = MagicMock()
        session = MagicMock()
        file_record = _make_file_record()

        result = _ingest_pdf_sync(session, file_record, b"fake-pdf", mock_vs)

        assert result["status"] == "complete"
        assert result["ocr_chunks"] >= 1
