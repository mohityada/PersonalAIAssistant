"""API-key based authentication middleware."""

import logging
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.database import User
from app.utils.hashing import hash_api_key

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    api_key: str | None = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate the API key and return the authenticated User.

    Raises 401 if the key is missing or invalid.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header.",
        )

    hashed = hash_api_key(api_key)
    result = await db.execute(select(User).where(User.api_key_hash == hashed))
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning("Auth failed: invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    logger.debug("Authenticated user: %s (%s)", user.name, user.id)
    return user
