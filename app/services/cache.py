"""Redis caching service for queries and embeddings."""

import json
import logging

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.config import get_settings
from app.utils.hashing import cache_key

logger = logging.getLogger(__name__)

_EMPTY_FILTERS = "{}"


def _filters_str(filters: dict | None) -> str:
    """Serialize filters dict once for cache key construction."""
    return json.dumps(filters, sort_keys=True) if filters else _EMPTY_FILTERS


class CacheService:
    """Async Redis wrapper for query-result and embedding caching."""

    def __init__(self) -> None:
        settings = get_settings()
        self._redis: aioredis.Redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        self._query_ttl = settings.query_cache_ttl
        self._embedding_ttl = settings.embedding_cache_ttl

    async def close(self) -> None:
        await self._redis.aclose()

    # ── internal helpers ────────────────────────────

    async def _get_json(self, key: str) -> dict | list | None:
        """Fetch a key and deserialize JSON; return None on miss or error."""
        try:
            raw = await self._redis.get(key)
        except RedisError:
            logger.warning("Redis GET failed for key: %s", key, exc_info=True)
            return None
        if raw is None:
            logger.debug("Cache MISS: %s", key)
            return None
        logger.debug("Cache HIT: %s", key)
        return json.loads(raw)

    async def _set_json(self, key: str, value, ttl: int) -> None:
        """Serialize value to JSON and store with TTL."""
        try:
            await self._redis.setex(key, ttl, json.dumps(value))
        except RedisError:
            logger.warning("Redis SETEX failed for key: %s", key, exc_info=True)

    # ── query cache ─────────────────────────────────

    async def get_cached_query(self, user_id: str, query: str, filters: dict | None = None) -> dict | None:
        """Return cached query response or None."""
        key = cache_key("query", user_id, query, _filters_str(filters))
        return await self._get_json(key)

    async def set_cached_query(
        self, user_id: str, query: str, filters: dict | None, response: dict
    ) -> None:
        """Store a query response in cache."""
        key = cache_key("query", user_id, query, _filters_str(filters))
        await self._set_json(key, response, self._query_ttl)

    # ── embedding cache ─────────────────────────────

    async def get_cached_embedding(self, text: str) -> list[float] | None:
        """Return cached embedding vector or None."""
        key = cache_key("emb", text)
        return await self._get_json(key)

    async def set_cached_embedding(self, text: str, vector: list[float]) -> None:
        """Store an embedding vector in cache."""
        key = cache_key("emb", text)
        await self._set_json(key, vector, self._embedding_ttl)

    # ── ask cache & recent ──────────────────────────

    async def get_cached_ask(self, user_id: str, question: str, filters: dict | None = None) -> dict | None:
        """Return a cached RAG response payload or None."""
        key = cache_key("ask", user_id, question, _filters_str(filters))
        return await self._get_json(key)

    async def set_cached_ask(
        self, user_id: str, question: str, filters: dict | None, response: dict
    ) -> None:
        """Store the final generated ask payload."""
        key = cache_key("ask", user_id, question, _filters_str(filters))
        await self._set_json(key, response, self._query_ttl)

    async def add_recent_ask(self, user_id: str, question: str) -> None:
        """Add a question to the user's recent list (max 10, deduped, single round-trip)."""
        list_key = f"recent_asks:{user_id}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.lrem(list_key, 0, question)
                pipe.lpush(list_key, question)
                pipe.ltrim(list_key, 0, 9)
                await pipe.execute()
        except RedisError:
            logger.warning("Redis pipeline failed for add_recent_ask: %s", user_id, exc_info=True)

    async def get_recent_asks(self, user_id: str) -> list[str]:
        """Get the user's recent 10 questions."""
        list_key = f"recent_asks:{user_id}"
        try:
            return await self._redis.lrange(list_key, 0, 9)
        except RedisError:
            logger.warning("Redis LRANGE failed for recent_asks: %s", user_id, exc_info=True)
            return []

    # ── generic helpers ─────────────────────────────

    async def get(self, key: str) -> str | None:
        try:
            return await self._redis.get(key)
        except RedisError:
            logger.warning("Redis GET failed: %s", key, exc_info=True)
            return None

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        try:
            if ttl:
                await self._redis.setex(key, ttl, value)
            else:
                await self._redis.set(key, value)
        except RedisError:
            logger.warning("Redis SET failed: %s", key, exc_info=True)

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except RedisError:
            logger.warning("Redis DELETE failed: %s", key, exc_info=True)
