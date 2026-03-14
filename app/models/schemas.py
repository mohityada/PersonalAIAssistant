"""Pydantic schemas for API requests and responses."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Upload ──────────────────────────────────────────────


class UploadResponse(BaseModel):
    file_id: UUID
    filename: str
    file_type: str
    status: str = "processing"
    message: str = "File uploaded and queued for ingestion."


# ── Files ────────────────────────────────────────────────


class FileInfo(BaseModel):
    id: UUID
    filename: str
    file_type: str
    tags: list[str] | None = None
    location: str | None = None
    caption: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Search ──────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    filters: dict | None = Field(
        default=None,
        description="Optional metadata filters, e.g. {'file_type': 'image', 'location': 'Jaipur'}",
    )
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    file_id: UUID
    filename: str
    file_type: str
    score: float
    chunk_text: str | None = None
    caption: str | None = None
    location: str | None = None
    tags: list[str] | None = None
    created_at: datetime | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    cached: bool = False


# ── Ask (RAG) ───────────────────────────────────────────


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    filters: dict | None = None


class SourceReference(BaseModel):
    file_id: UUID
    filename: str
    chunk_text: str | None = None
    score: float


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceReference]
    reasoning_used: bool = True
    cached: bool = False


# ── Query Parser ────────────────────────────────────────


class ParsedIntent(BaseModel):
    file_type: str | None = None
    location: str | None = None
    keyword: str | None = None
    date_range: dict | None = None
    tags: list[str] | None = None
    filename: str | None = None
    requires_reasoning: bool = False
    rephrased_query: str | None = None


# ── Health ──────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "healthy"
    services: dict[str, str] = {}
