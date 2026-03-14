"""Files management endpoints — list, view, delete, status, and retry."""

import logging
import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.session import get_db
from app.dependencies import get_vector_store
from app.models.database import File as FileModel, User
from app.models.schemas import FileInfo
from app.services.storage import StorageService
from app.services.vector_store import VectorStoreService
from app.workers.tasks import ingest_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["Files"])


# ── FAQ helpers ───────────────────────────────────────

_FAQ_TEMPLATES: dict[str, list[str]] = {
    "pdf":   ["Summarize {name}", "What are the key points in {name}?", "What is {name} about?"],
    "docx":  ["What does {name} say?", "Extract key information from {name}"],
    "text":  ["What is in {name}?", "Summarize {name}"],
    "image": ["What is shown in {name}?", "Describe {name} in detail"],
}
_FALLBACK_FAQS = [
    "What are my uploaded files about?",
    "Summarize my most recent document",
    "Find files related to finance",
    "What images have I uploaded?",
    "Extract all email addresses from my files",
]


def _build_faq_suggestions(files: list) -> list[str]:
    """Generate contextual FAQ questions based on the user’s actual files."""
    suggestions: list[str] = []
    seen: set[str] = set()
    for f in files[:10]:
        stem = Path(f.original_filename).stem
        name = re.sub(r"[_\-]+", " ", stem).strip()[:40]
        for tmpl in _FAQ_TEMPLATES.get(f.file_type, []):
            q = tmpl.format(name=name)
            if q not in seen:
                seen.add(q)
                suggestions.append(q)
        if len(suggestions) >= 6:
            break
    return suggestions[:6] if suggestions else _FALLBACK_FAQS[:5]


# ── endpoints ──────────────────────────────────────────────────


@router.get("", response_model=list[FileInfo])
async def list_files(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FileInfo]:
    """Return all files uploaded by the authenticated user, newest first."""
    result = await db.execute(
        select(FileModel)
        .where(FileModel.user_id == user.id)
        .order_by(FileModel.created_at.desc())
    )
    files = result.scalars().all()
    return [
        FileInfo(
            id=f.id,
            filename=f.original_filename,
            file_type=f.file_type,
            tags=f.tags,
            location=f.location,
            caption=f.caption,
            created_at=f.created_at,
        )
        for f in files
    ]


@router.get("/faq-suggestions", response_model=list[str])
async def faq_suggestions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """Return contextual FAQ questions generated from the user’s uploaded files."""
    result = await db.execute(
        select(FileModel)
        .where(FileModel.user_id == user.id)
        .order_by(FileModel.created_at.desc())
        .limit(20)
    )
    files = result.scalars().all()
    return _build_faq_suggestions(files)


@router.get("/{file_id}/status")
async def file_status(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the ingestion status of a specific file."""
    file_record = await db.get(FileModel, file_id)
    if not file_record or file_record.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return {
        "file_id": str(file_record.id),
        "status": file_record.status or "processing",
        "error_message": file_record.error_message,
    }


@router.post("/{file_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_ingestion(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-queue ingestion for a file that previously failed."""
    file_record = await db.get(FileModel, file_id)
    if not file_record or file_record.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if file_record.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only files with status 'failed' can be retried",
        )
    file_record.status = "processing"
    file_record.error_message = None
    await db.commit()
    ingest_file.delay(str(file_id))
    logger.info("Retrying ingestion for file %s", file_id)
    return {"file_id": str(file_id), "status": "processing"}


@router.get("/{file_id}/view")
async def view_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate a short-lived pre-signed S3 URL to view/download the file."""
    file_record = await db.get(FileModel, file_id)
    if not file_record or file_record.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    storage = StorageService()
    url = await storage.generate_presigned_url(file_record.file_path, expires_in=900)
    return {
        "url": url,
        "filename": file_record.original_filename,
        "file_type": file_record.file_type,
    }


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_store: VectorStoreService = Depends(get_vector_store),
) -> None:
    """Delete a file from S3, Qdrant, and the database (cascades to chunks)."""
    file_record = await db.get(FileModel, file_id)
    if not file_record or file_record.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # 1. Delete vectors from Qdrant
    try:
        await vector_store.delete_by_file_id(str(file_id))
    except Exception:
        logger.warning("Failed to delete Qdrant vectors for file %s", file_id, exc_info=True)

    # 2. Delete object from S3
    try:
        storage = StorageService()
        await storage.delete_file(file_record.file_path)
    except Exception:
        logger.warning("Failed to delete S3 object for file %s", file_id, exc_info=True)

    # 3. Delete DB record (cascades to Chunk rows)
    await db.delete(file_record)
    await db.commit()
    logger.info("Deleted file %s (%s) for user %s", file_id, file_record.original_filename, user.id)
