"""Redis caching service for queries and embeddings."""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.utils.hashing import cache_key

logger = logging.getLogger(__name__)


class CacheService:
    """Async Redis wrapper for query-result and embedding caching."""

    def __init__(self) -> None:
        settings = get_settings()
        self._redis: aioredis.Redis = aioredis.from_url(
            settings.redis_url, decode_responses=True
        )
        self._query_ttl = settings.query_cache_ttl
        self._embedding_ttl = settings.embedding_cache_ttl

    async def close(self) -> None:
        await self._redis.aclose()

    # ── query cache ─────────────────────────────────

    async def get_cached_query(self, user_id: str, query: str, filters: dict | None = None) -> dict | None:
        """Return cached query response or None."""
        key = cache_key("query", user_id, query, json.dumps(filters or {}, sort_keys=True))
        raw = await self._redis.get(key)
        if raw:
            logger.debug("Query cache HIT: %s", key)
            return json.loads(raw)
        logger.debug("Query cache MISS: %s", key)
        return None

    async def set_cached_query(
        self, user_id: str, query: str, filters: dict | None, response: dict
    ) -> None:
        """Store a query response in cache."""
        key = cache_key("query", user_id, query, json.dumps(filters or {}, sort_keys=True))
        await self._redis.setex(key, self._query_ttl, json.dumps(response))
        logger.debug("Query cache SET: %s (ttl=%ds)", key, self._query_ttl)

    # ── embedding cache ─────────────────────────────

    async def get_cached_embedding(self, text: str) -> list[float] | None:
        """Return cached embedding vector or None."""
        key = cache_key("emb", text)
        raw = await self._redis.get(key)
        if raw:
            logger.debug("Embedding cache HIT: %s", key)
            return json.loads(raw)
        logger.debug("Embedding cache MISS: %s", key)
        return None

    async def set_cached_embedding(self, text: str, vector: list[float]) -> None:
        """Store an embedding vector in cache."""
        key = cache_key("emb", text)
        await self._redis.setex(key, self._embedding_ttl, json.dumps(vector))
        logger.debug("Embedding cache SET: %s (ttl=%ds)", key, self._embedding_ttl)

    # ── generic helpers ─────────────────────────────

    async def get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if ttl:
            await self._redis.setex(key, ttl, value)
        else:
            await self._redis.set(key, value)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)
