"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.dependencies import get_cache, get_vector_store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle events."""
    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    # Ensure Qdrant collection exists
    vector_store = get_vector_store()
    vector_store.ensure_collection()
    logger.info("Qdrant collection ready: %s", settings.qdrant_collection)

    logger.info("🚀 %s started", settings.app_name)
    yield

    # Shutdown: close Redis pool
    cache = get_cache()
    await cache.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Personal AI Assistant with multimodal storage, semantic search, and RAG.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(api_router)

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


app = create_app()
