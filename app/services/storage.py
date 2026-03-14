"""AWS S3 storage service for file uploads and downloads."""

import io
import logging
from uuid import UUID

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)


class StorageService:
    """Manages file upload/download to AWS S3."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        self._bucket = settings.s3_bucket_name

    # ── helpers ─────────────────────────────────────

    @staticmethod
    def _build_key(user_id: UUID, file_id: UUID, filename: str) -> str:
        """Build the S3 object key with proper category folder.

        Pattern: uploads/<category>/<user_id>/<file_id>/<filename>
        Categories: images | documents
        """
        from pathlib import Path
        _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}
        category = "images" if Path(filename).suffix.lower() in _IMAGE_EXTS else "documents"
        return f"uploads/{category}/{user_id}/{file_id}/{filename}"

    # ── public API ──────────────────────────────────

    async def upload_file(
        self,
        user_id: UUID,
        file_id: UUID,
        file_bytes: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file to S3 and return the object key.

        Returns:
            The S3 object key for the uploaded file.
        """
        key = self._build_key(user_id, file_id, filename)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )
            logger.info("Uploaded %s to s3://%s/%s", filename, self._bucket, key)
            return key
        except ClientError:
            logger.exception("Failed to upload %s to S3", filename)
            raise

    async def download_file(self, s3_key: str) -> bytes:
        """Download a file from S3 by its object key."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
            data = response["Body"].read()
            logger.info("Downloaded %s (%d bytes)", s3_key, len(data))
            return data
        except ClientError:
            logger.exception("Failed to download %s from S3", s3_key)
            raise

    async def delete_file(self, s3_key: str) -> None:
        """Delete a file from S3."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=s3_key)
            logger.info("Deleted %s from S3", s3_key)
        except ClientError:
            logger.exception("Failed to delete %s from S3", s3_key)
            raise

    async def generate_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
        """Generate a pre-signed URL for temporary access to a file."""
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": s3_key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError:
            logger.exception("Failed to generate presigned URL for %s", s3_key)
            raise
