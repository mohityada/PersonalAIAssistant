"""API router aggregator — includes all endpoint routers."""

from fastapi import APIRouter

from app.api import upload, search, ask

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(upload.router)
api_router.include_router(search.router)
api_router.include_router(ask.router)
