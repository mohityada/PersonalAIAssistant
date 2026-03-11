"""Ask endpoint — RAG-powered question answering."""

import logging

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.dependencies import get_rag_service, get_cache
from app.models.database import User
from app.models.schemas import AskRequest, AskResponse
from app.services.rag import RAGService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Ask"])


@router.post("/ask", response_model=AskResponse)
async def ask(
    body: AskRequest,
    user: User = Depends(get_current_user),
    rag: RAGService = Depends(get_rag_service),
) -> AskResponse:
    """Answer a question using RAG over the user's ingested files.

    Simple retrieval queries return results directly.
    Complex questions trigger Claude for synthesis and reasoning.
    """
    logger.info("Ask request from user=%s: %s", user.email, body.question[:80])
    return await rag.ask(
        question=body.question,
        user_id=str(user.id),
        filters=body.filters,
    )

@router.get("/recent-asks", response_model=list[str])
async def get_recent_asks(
    user: User = Depends(get_current_user),
    cache = Depends(get_cache)
) -> list[str]:
    """Retrieve the user's recently asked questions."""
    logger.info("Fetching recent asks for user=%s", user.email)
    if cache:
        return await cache.get_recent_asks(str(user.id))
    return []
