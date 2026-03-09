"""Search endpoint — semantic search over ingested data."""

import logging

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.dependencies import get_rag_service
from app.models.database import User
from app.models.schemas import SearchRequest, SearchResponse
from app.services.rag import RAGService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    user: User = Depends(get_current_user),
    rag: RAGService = Depends(get_rag_service),
) -> SearchResponse:
    """Semantic search across all ingested files for the authenticated user."""
    logger.info("Search request from user=%s: %s", user.id, body.query[:80])
    return await rag.search(
        query=body.query,
        user_id=str(user.id),
        filters=body.filters,
        top_k=body.top_k,
    )
