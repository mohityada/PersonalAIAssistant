"""Celery tasks for asynchronous file ingestion (fully synchronous DB access)."""

import asyncio
import logging
import re
import uuid
from pathlib import Path

import boto3
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.database import Chunk, File
from app.services.chunking import chunk_text
from app.services.image_processing import process_image
from app.services.text_extraction import extract_text
from app.services.vector_store import VectorStoreService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Image extensions for routing
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"})

# Errors that should NOT be retried
NON_RETRYABLE_ERRORS = (ValueError, KeyError, TypeError)


# ---------------------------------------------------------------------------
# Singleton managers — one instance per worker process
# ---------------------------------------------------------------------------

class _SingletonMeta(type):
    """Thread-safe-ish singleton metaclass (one instance per Celery worker)."""
    _instances: dict = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class DBSessionManager(metaclass=_SingletonMeta):
    """Manages a single SQLAlchemy engine with connection pooling."""

    def __init__(self):
        settings = get_settings()
        self._engine = create_engine(
            settings.database_url_sync,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        self._session_factory = sessionmaker(bind=self._engine)

    def create_session(self):
        return self._session_factory()

    def dispose(self):
        self._engine.dispose()


class EmbeddingModelManager(metaclass=_SingletonMeta):
    """Caches the SentenceTransformer model for the worker lifetime."""

    def __init__(self):
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        self._model = SentenceTransformer(settings.embedding_model, device="cpu")
        logger.info("Loaded embedding model: %s", settings.embedding_model)

    @property
    def model(self):
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        ).tolist()


class S3ClientManager(metaclass=_SingletonMeta):
    """Reuses a single boto3 S3 client per worker."""

    def __init__(self):
        settings = get_settings()
        self._client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        self._bucket = settings.s3_bucket_name

    def download(self, s3_key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
        return response["Body"].read()


class VectorStoreManager(metaclass=_SingletonMeta):
    """Singleton wrapper around the async VectorStoreService."""

    def __init__(self):
        self._service = VectorStoreService()

    def upsert_vectors(self, points: list[dict]):
        """Run the async upsert in an isolated event loop."""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._service.upsert_vectors(points))
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _is_image(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return suffix in IMAGE_EXTENSIONS


def _clean_text(text: str) -> str:
    """Normalize extracted text for better embedding quality."""
    # Strip NUL bytes — PostgreSQL text columns reject \x00
    text = text.replace("\x00", "")
    # Collapse excessive whitespace / newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _humanize_filename(filename: str) -> str:
    """Convert 'sunset_beach-2024.jpg' → 'sunset beach 2024'."""
    stem = Path(filename).stem
    return re.sub(r"[_\-]+", " ", stem).strip()


def _build_document_chunk_payload(
    file_record: File,
    chunk_text_str: str,
    chunk_index: int,
    total_chunks: int,
) -> dict:
    """Build a rich Qdrant payload for a document chunk (improves RAG retrieval)."""
    return {
        "user_id": str(file_record.user_id),
        "file_id": str(file_record.id),
        "filename": file_record.original_filename,
        "filename_semantic": _humanize_filename(file_record.original_filename),
        "file_type": file_record.file_type,
        "chunk_text": chunk_text_str,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "location": file_record.location,
        "tags": file_record.tags or [],
    }


def _build_embedding_text_for_chunk(
    chunk_text_str: str,
    filename: str,
    tags: list[str] | None,
) -> str:
    """Prepend contextual prefix to chunk text for richer embeddings.

    Adding the filename and tags directly into the embedding input lets the
    model associate semantic meaning from the filename (e.g. "tax_return_2024")
    and user-assigned tags with the chunk content.
    """
    parts: list[str] = []
    humanized = _humanize_filename(filename)
    if humanized:
        parts.append(f"Document: {humanized}")
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")
    parts.append(chunk_text_str)
    return " | ".join(parts)


def _build_image_embed_text(
    caption: str | None,
    objects: list[str] | None,
    filename: str,
    location: str | None,
    tags: list[str] | None,
) -> str:
    """Build a semantically rich embedding string for an image."""
    parts: list[str] = []
    if caption:
        parts.append(caption)
    if objects:
        parts.append("Objects: " + ", ".join(objects))
    # Include original filename (often descriptive, e.g. "sunset_beach_2024.jpg")
    humanized = _humanize_filename(filename)
    if humanized:
        parts.append(f"Filename: {humanized}")
    if location:
        parts.append(f"Location: {location}")
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    return ". ".join(parts)


def _process_image_sync(file_bytes: bytes):
    """Run async image processing synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(process_image(file_bytes))
    finally:
        loop.close()


def _update_file_status(session, file_id: uuid.UUID, status: str, error_message: str | None = None):
    """Persist ingestion status back to the File record."""
    values = {"status": status}
    if error_message:
        values["error_message"] = error_message[:1000]  # truncate long traces
    try:
        session.execute(update(File).where(File.id == file_id).values(**values))
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to update file status for %s", file_id)


# ---------------------------------------------------------------------------
# Main Celery task
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def ingest_file(self, file_id: str) -> dict:
    """Ingest a file: download from S3, extract → embed → store in Qdrant."""
    session = None
    try:
        db = DBSessionManager()
        session = db.create_session()

        file_record = session.execute(
            select(File).where(File.id == uuid.UUID(file_id))
        ).scalar_one_or_none()

        if not file_record:
            raise ValueError(f"File not found: {file_id}")

        logger.info(
            "Ingesting: %s (%s, %s)",
            file_record.original_filename,
            file_record.file_type,
            file_id,
        )

        # Mark as processing
        _update_file_status(session, file_record.id, "processing")

        # Download from S3
        try:
            s3 = S3ClientManager()
            file_bytes = s3.download(file_record.file_path)
        except Exception as exc:
            _update_file_status(session, file_record.id, "failed", f"S3 download error: {exc}")
            raise

        vector_store = VectorStoreManager()

        if _is_image(file_record.original_filename):
            result = _ingest_image_sync(session, file_record, file_bytes, vector_store)
        else:
            result = _ingest_document_sync(session, file_record, file_bytes, vector_store)

        # Mark as complete
        _update_file_status(session, file_record.id, "complete")
        return result

    except NON_RETRYABLE_ERRORS as exc:
        logger.error("Non-retryable error for file_id=%s: %s", file_id, exc)
        if session:
            _update_file_status(session, uuid.UUID(file_id), "failed", str(exc))
        return {"file_id": file_id, "status": "failed", "error": str(exc)}

    except Exception as exc:
        logger.exception("Ingestion failed for file_id=%s (attempt %d/%d)", file_id, self.request.retries + 1, self.max_retries + 1)
        if session and self.request.retries >= self.max_retries:
            _update_file_status(session, uuid.UUID(file_id), "failed", str(exc))
        raise self.retry(exc=exc)

    finally:
        if session:
            session.close()


# ---------------------------------------------------------------------------
# Document ingestion
# ---------------------------------------------------------------------------


def _ingest_document_sync(session, file_record, file_bytes, vector_store: VectorStoreManager) -> dict:
    """Text document ingestion: extract → chunk → embed → store."""
    # --- Extraction ---
    try:
        text = extract_text(file_bytes, file_record.original_filename)
    except Exception as exc:
        logger.error("Text extraction failed for %s: %s", file_record.original_filename, exc)
        raise RuntimeError(f"Text extraction failed: {exc}") from exc

    text = _clean_text(text)
    if not text:
        logger.warning("No text extracted from %s", file_record.original_filename)
        return {"file_id": str(file_record.id), "status": "empty", "chunks": 0}

    # --- Chunking ---
    chunks = chunk_text(text)
    if not chunks:
        logger.warning("Chunking produced zero chunks for %s", file_record.original_filename)
        return {"file_id": str(file_record.id), "status": "empty", "chunks": 0}

    total_chunks = len(chunks)

    # Build enriched texts for embedding (filename + tags + chunk content)
    enriched_texts = [
        _build_embedding_text_for_chunk(
            c.text, file_record.original_filename, file_record.tags
        )
        for c in chunks
    ]

    # --- Embedding ---
    try:
        embedder = EmbeddingModelManager()
        vectors = embedder.encode(enriched_texts)
    except Exception as exc:
        logger.error("Embedding failed for %s: %s", file_record.original_filename, exc)
        raise RuntimeError(f"Embedding failed: {exc}") from exc

    if len(vectors) != total_chunks:
        raise RuntimeError(
            f"Vector count mismatch: {len(vectors)} vectors for {total_chunks} chunks"
        )

    # --- Persist to DB + Qdrant ---
    chunk_records: list[Chunk] = []
    qdrant_points: list[dict] = []

    for chunk_data, vector in zip(chunks, vectors):
        vector_id = uuid.uuid4()
        chunk_records.append(
            Chunk(
                file_id=file_record.id,
                chunk_text=chunk_data.text,
                vector_id=vector_id,
                chunk_index=chunk_data.index,
            )
        )
        qdrant_points.append({
            "id": str(vector_id),
            "vector": vector,
            "payload": _build_document_chunk_payload(
                file_record, chunk_data.text, chunk_data.index, total_chunks
            ),
        })

    try:
        session.add_all(chunk_records)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("DB commit failed for %s: %s", file_record.original_filename, exc)
        raise RuntimeError(f"Database commit failed: {exc}") from exc

    try:
        vector_store.upsert_vectors(qdrant_points)
    except Exception as exc:
        logger.error("Qdrant upsert failed for %s: %s", file_record.original_filename, exc)
        raise RuntimeError(f"Vector store upsert failed: {exc}") from exc

    logger.info(
        "Document ingestion complete: %s → %d chunks",
        file_record.original_filename,
        total_chunks,
    )
    return {"file_id": str(file_record.id), "status": "complete", "chunks": total_chunks}


# ---------------------------------------------------------------------------
# Image ingestion
# ---------------------------------------------------------------------------


def _ingest_image_sync(session, file_record, file_bytes, vector_store: VectorStoreManager) -> dict:
    """Image ingestion: BLIP caption + YOLO objects → embed → store in Qdrant."""
    # --- Image processing ---
    try:
        metadata = _process_image_sync(file_bytes)
    except Exception as exc:
        logger.error("Image processing failed for %s: %s", file_record.original_filename, exc)
        raise RuntimeError(f"Image processing failed: {exc}") from exc

    # Update File record with extracted metadata
    location = metadata.location or file_record.location
    try:
        session.execute(
            update(File).where(File.id == file_record.id).values(
                caption=metadata.caption,
                objects=metadata.objects,
                location=location,
            )
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("DB update failed for image %s: %s", file_record.original_filename, exc)
        raise RuntimeError(f"Database update failed: {exc}") from exc

    # Build rich embedding text: caption + objects + filename + location
    # This gives the embedding model much more to work with for semantic search.
    embed_text = _build_image_embed_text(
        caption=metadata.caption,
        objects=metadata.objects,
        filename=file_record.original_filename,
        location=location,
        tags=file_record.tags,
    )

    if not embed_text.strip():
        logger.warning("No meaningful embedding text for image %s", file_record.original_filename)
        return {"file_id": str(file_record.id), "status": "empty", "caption": None, "objects": []}

    # --- Embedding ---
    try:
        embedder = EmbeddingModelManager()
        vector = embedder.encode([embed_text])[0]
    except Exception as exc:
        logger.error("Embedding failed for image %s: %s", file_record.original_filename, exc)
        raise RuntimeError(f"Embedding failed: {exc}") from exc

    vector_id = uuid.uuid4()
    chunk_record = Chunk(
        file_id=file_record.id,
        chunk_text=embed_text,
        vector_id=vector_id,
        chunk_index=0,
    )

    try:
        session.add(chunk_record)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("DB commit failed for image %s: %s", file_record.original_filename, exc)
        raise RuntimeError(f"Database commit failed: {exc}") from exc

    try:
        vector_store.upsert_vectors([{
            "id": str(vector_id),
            "vector": vector,
            "payload": {
                "user_id": str(file_record.user_id),
                "file_id": str(file_record.id),
                "filename": file_record.original_filename,
                "filename_semantic": _humanize_filename(file_record.original_filename),
                "file_type": "image",
                "caption": metadata.caption,
                "chunk_text": embed_text,
                "objects": metadata.objects or [],
                "location": location,
                "tags": file_record.tags or [],
            },
        }])
    except Exception as exc:
        logger.error("Qdrant upsert failed for image %s: %s", file_record.original_filename, exc)
        raise RuntimeError(f"Vector store upsert failed: {exc}") from exc

    caption_preview = (metadata.caption or "")[:60]
    logger.info(
        "Image ingestion complete: %s (caption=%s)",
        file_record.original_filename,
        caption_preview,
    )
    return {
        "file_id": str(file_record.id),
        "status": "complete",
        "caption": metadata.caption,
        "objects": metadata.objects,
    }