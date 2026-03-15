"""Upload endpoint — accepts files, stores in S3, and queues ingestion."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models.database import File as FileModel, User
from app.models.schemas import UploadResponse
from app.services.storage import StorageService
from app.workers.tasks import ingest_file

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Upload"])

# Allowed file extensions
_ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".csv",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp",
}
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _get_file_type(filename: str) -> str:
    """Determine the file_type value from the filename extension."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    elif lower.endswith(".docx"):
        return "docx"
    elif lower.endswith((".txt", ".csv", ".md")):
        return "text"
    elif lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp")):
        return "image"
    return "unknown"


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    file: UploadFile = File(...),
    tags: str | None = Form(None, description="Comma-separated tags"),
    location: str | None = Form(None, description="Location metadata"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Upload a file for ingestion.

    The file is stored in S3, a database record is created,
    and a background Celery task is dispatched.
    """
    filename = file.filename or "untitled"

    # Validate extension
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {ext}. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    # Read file bytes
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {_MAX_FILE_SIZE // (1024*1024)} MB.",
        )

    file_type = _get_file_type(filename)
    parsed_tags = [t.strip() for t in tags.split(",")] if tags else None

    # Create database record
    file_record = FileModel(
        user_id=user.id,
        file_type=file_type,
        file_path="",  # Will be set after S3 upload
        original_filename=filename,
        location=location,
        tags=parsed_tags,
    )
    db.add(file_record)
    await db.flush()  # Get the generated ID

    # Upload to S3
    storage = StorageService()
    s3_key = await storage.upload_file(
        user_id=user.id,
        file_id=file_record.id,
        file_bytes=file_bytes,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
    )
    file_record.file_path = s3_key
    await db.commit()

    # Dispatch background ingestion
    task = ingest_file.delay(str(file_record.id))

    logger.info("Upload accepted: %s → %s (job_id=%s)", filename, s3_key, task.id)
    return UploadResponse(
        file_id=file_record.id,
        job_id=task.id,
        filename=filename,
        file_type=file_type,
    )
