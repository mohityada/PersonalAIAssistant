"""API router aggregator — includes all endpoint routers."""

from fastapi import APIRouter

from app.api import upload, search, ask, auth, files

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(upload.router)
api_router.include_router(search.router)
api_router.include_router(ask.router)
api_router.include_router(files.router)
