"""Celery tasks for asynchronous file ingestion (fully synchronous DB access)."""

import logging
import uuid

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.database import Chunk, File
from app.services.chunking import chunk_text
from app.services.image_processing import process_image
from app.services.storage import StorageService
from app.services.text_extraction import extract_text
from app.services.vector_store import VectorStoreService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Image extensions for routing
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}


def _is_image(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)


def _get_sync_session():
    """Create a synchronous SQLAlchemy session using psycopg2."""
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    Session = sessionmaker(bind=engine)
    return Session(), engine


def _embed_text_sync(text: str) -> list[float]:
    """Embed text synchronously (no Redis cache in worker context)."""
    from sentence_transformers import SentenceTransformer
    from app.config import get_settings
    settings = get_settings()
    model = SentenceTransformer(settings.embedding_model)
    return model.encode(text, normalize_embeddings=True).tolist()


def _embed_batch_sync(texts: list[str]) -> list[list[float]]:
    """Batch embed texts synchronously."""
    from sentence_transformers import SentenceTransformer
    from app.config import get_settings
    settings = get_settings()
    model = SentenceTransformer(settings.embedding_model)
    return model.encode(texts, normalize_embeddings=True).tolist()


def _process_image_sync(file_bytes: bytes):
    """Run image processing synchronously."""
    import asyncio
    from app.services.image_processing import process_image
    # process_image is async but has no DB/Redis calls — safe to run in a tiny loop
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(process_image(file_bytes))
    finally:
        loop.close()


def _download_file_sync(s3_key: str) -> bytes:
    """Download file from S3 synchronously (boto3 is sync already)."""
    import boto3
    from app.config import get_settings
    settings = get_settings()
    client = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    response = client.get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
    return response["Body"].read()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def ingest_file(self, file_id: str) -> dict:
    """Ingest a file: download from S3, extract → embed → store in Qdrant."""
    session, engine = None, None
    try:
        session, engine = _get_sync_session()
        file_record = session.execute(
            select(File).where(File.id == uuid.UUID(file_id))
        ).scalar_one_or_none()

        if not file_record:
            raise ValueError(f"File not found: {file_id}")

        logger.info("Ingesting: %s (%s)", file_record.original_filename, file_record.file_type)

        # Download from S3
        file_bytes = _download_file_sync(file_record.file_path)

        vector_store = VectorStoreService()

        if _is_image(file_record.original_filename):
            return _ingest_image_sync(session, file_record, file_bytes, vector_store)
        else:
            return _ingest_document_sync(session, file_record, file_bytes, vector_store)

    except Exception as exc:
        logger.exception("Ingestion failed for file_id=%s", file_id)
        raise self.retry(exc=exc)
    finally:
        if session:
            session.close()
        if engine:
            engine.dispose()


def _ingest_document_sync(session, file_record, file_bytes, vector_store) -> dict:
    """Text document ingestion: extract → chunk → embed → store."""
    text = extract_text(file_bytes, file_record.original_filename)
    if not text.strip():
        logger.warning("No text extracted from %s", file_record.original_filename)
        return {"file_id": str(file_record.id), "status": "empty", "chunks": 0}

    chunks = chunk_text(text)
    chunk_texts = [c.text for c in chunks]
    vectors = _embed_batch_sync(chunk_texts)

    chunk_records = []
    qdrant_points = []
    for chunk_data, vector in zip(chunks, vectors):
        vector_id = uuid.uuid4()
        chunk_record = Chunk(
            file_id=file_record.id,
            chunk_text=chunk_data.text,
            vector_id=vector_id,
            chunk_index=chunk_data.index,
        )
        chunk_records.append(chunk_record)
        qdrant_points.append({
            "id": str(vector_id),
            "vector": vector,
            "payload": {
                "user_id": str(file_record.user_id),
                "file_id": str(file_record.id),
                "filename": file_record.original_filename,
                "file_type": file_record.file_type,
                "chunk_text": chunk_data.text,
                "chunk_index": chunk_data.index,
                "location": file_record.location,
                "tags": file_record.tags,
            },
        })

    session.add_all(chunk_records)
    session.commit()

    # Upsert into Qdrant (sync client call)
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(vector_store.upsert_vectors(qdrant_points))
    finally:
        loop.close()

    logger.info("Document ingestion complete: %s → %d chunks", file_record.original_filename, len(chunks))
    return {"file_id": str(file_record.id), "status": "complete", "chunks": len(chunks)}


def _ingest_image_sync(session, file_record, file_bytes, vector_store) -> dict:
    """Image ingestion: EXIF + YOLO → embed caption → store."""
    metadata = _process_image_sync(file_bytes)

    # Update File record
    session.execute(
        update(File).where(File.id == file_record.id).values(
            caption=metadata.caption,
            objects=metadata.objects,
            location=metadata.location or file_record.location,
        )
    )
    session.commit()

    embed_text = metadata.caption
    if metadata.objects:
        embed_text += " " + " ".join(metadata.objects)

    vector = _embed_text_sync(embed_text)
    vector_id = uuid.uuid4()

    chunk_record = Chunk(
        file_id=file_record.id,
        chunk_text=embed_text,
        vector_id=vector_id,
        chunk_index=0,
    )
    session.add(chunk_record)
    session.commit()

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(vector_store.upsert_vectors([{
            "id": str(vector_id),
            "vector": vector,
            "payload": {
                "user_id": str(file_record.user_id),
                "file_id": str(file_record.id),
                "filename": file_record.original_filename,
                "file_type": "image",
                "caption": metadata.caption,
                "chunk_text": embed_text,
                "objects": metadata.objects,
                "location": metadata.location or file_record.location,
                "tags": file_record.tags,
            },
        }]))
    finally:
        loop.close()

    logger.info("Image ingestion complete: %s", file_record.original_filename)
    return {
        "file_id": str(file_record.id),
        "status": "complete",
        "caption": metadata.caption,
        "objects": metadata.objects,
    }
