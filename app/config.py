"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central configuration for the Personal AI Assistant."""

    # ── App ─────────────────────────────────────────
    app_name: str = "PersonalAIAssistant"
    debug: bool = False

    # ── PostgreSQL ──────────────────────────────────
    database_url: str = ""  # Set via DATABASE_URL in .env
    database_url_sync: str = ""  # Set via DATABASE_URL_SYNC in .env

    # ── Qdrant ──────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "personal_ai"

    # ── Redis ───────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── AWS S3 ──────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"
    s3_bucket_name: str = ""

    # ── Anthropic / Claude ──────────────────────────
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # ── Embedding ───────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_dimension: int = 384

    # ── Caching ─────────────────────────────────────
    query_cache_ttl: int = 3600       # 1 hour
    embedding_cache_ttl: int = 86400  # 24 hours

    # ── Search ──────────────────────────────────────
    search_top_k: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
