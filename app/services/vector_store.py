"""Qdrant vector-store service for semantic search."""

import logging
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchText,
    MatchValue,
    PointStruct,
    TextIndexParams,
    VectorParams,
)

from app.config import get_settings

logger = logging.getLogger(__name__)


class VectorStoreService:
    """Wrapper around the Qdrant client for vector upsert/search/delete."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        self._collection = settings.qdrant_collection
        self._vector_size = settings.vector_dimension

    # ── collection management ───────────────────────

    def ensure_collection(self) -> None:
        """Create the collection if it does not already exist."""
        collections = [c.name for c in self._client.get_collections().collections]
        if self._collection not in collections:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                ),
            )
            self._client.create_payload_index(
                collection_name=self._collection,
                field_name="filename",
                field_schema=TextIndexParams(
                    type="text",
                    tokenizer="word",
                    min_token_len=2,
                    max_token_len=40,
                    lowercase=True,
                )
            )
            logger.info("Created Qdrant collection '%s'", self._collection)
        else:
            logger.info("Qdrant collection '%s' already exists", self._collection)

    # ── upsert ──────────────────────────────────────

    async def upsert_vectors(
        self,
        points: list[dict],
    ) -> None:
        """Batch-upsert points into Qdrant.

        Each dict in *points* must contain:
            id       – UUID (used as the Qdrant point ID)
            vector   – list[float]
            payload  – dict with at least 'user_id', 'file_id', plus any metadata
        """
        structs = [
            PointStruct(
                id=str(p["id"]),
                vector=p["vector"],
                payload=p["payload"],
            )
            for p in points
        ]
        self._client.upsert(
            collection_name=self._collection,
            points=structs,
        )
        logger.info("Upserted %d vectors into '%s'", len(structs), self._collection)

    # ── search ──────────────────────────────────────

    async def search(
        self,
        query_vector: list[float],
        user_id: str,
        filters: dict | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Semantic search scoped to a single user.

        Returns a list of dicts: {id, score, payload}.
        """
        must_conditions = [
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
        ]
        if filters:
            for key, value in filters.items():
                if key == "filename":
                    must_conditions.append(
                        FieldCondition(key=key, match=MatchText(text=value))
                    )
                else:
                    must_conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )

        response = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=top_k,
            query_filter=Filter(must=must_conditions),
        )

        results = [
            {"id": hit.id, "score": hit.score, "payload": hit.payload}
            for hit in response.points
        ]
        logger.info("Search returned %d results for user %s", len(results), user_id)
        return results

    # ── delete ──────────────────────────────────────

    async def delete_by_file_id(self, file_id: str) -> None:
        """Delete all vectors associated with a specific file."""
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[
                    FieldCondition(key="file_id", match=MatchValue(value=file_id)),
                ]
            ),
        )
        logger.info("Deleted vectors for file_id=%s", file_id)
