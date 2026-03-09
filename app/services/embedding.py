"""Sentence-transformer embedding service with Redis caching."""

import logging

from sentence_transformers import SentenceTransformer

from app.config import get_settings
from app.services.cache import CacheService

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings using a local sentence-transformer model.

    Embeddings are cached in Redis to avoid re-computation.
    """

    def __init__(self, cache: CacheService | None = None) -> None:
        settings = get_settings()
        self._model_name = settings.embedding_model
        self._model: SentenceTransformer | None = None
        self._cache = cache

    def _load_model(self) -> SentenceTransformer:
        """Lazy-load the model on first use."""
        if self._model is None:
            logger.info("Loading embedding model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            logger.info("Embedding model loaded (dim=%d)", self._model.get_sentence_embedding_dimension())
        return self._model

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string.

        Checks the Redis cache first; computes and caches on miss.
        """
        # Cache lookup
        if self._cache:
            cached = await self._cache.get_cached_embedding(text)
            if cached is not None:
                return cached

        model = self._load_model()
        vector = model.encode(text, normalize_embeddings=True).tolist()

        # Cache store
        if self._cache:
            await self._cache.set_cached_embedding(text, vector)

        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single batch.

        Checks cache per-text; batch-encodes only the uncached ones.
        """
        results: list[list[float] | None] = [None] * len(texts)
        to_encode: list[tuple[int, str]] = []

        # Check cache for each text
        for i, text in enumerate(texts):
            if self._cache:
                cached = await self._cache.get_cached_embedding(text)
                if cached is not None:
                    results[i] = cached
                    continue
            to_encode.append((i, text))

        # Batch encode uncached texts
        if to_encode:
            model = self._load_model()
            uncached_texts = [t for _, t in to_encode]
            vectors = model.encode(uncached_texts, normalize_embeddings=True).tolist()
            for (orig_idx, text), vector in zip(to_encode, vectors):
                results[orig_idx] = vector
                if self._cache:
                    await self._cache.set_cached_embedding(text, vector)

        logger.info(
            "Embedded %d texts (cache hits: %d, computed: %d)",
            len(texts),
            len(texts) - len(to_encode),
            len(to_encode),
        )
        return results  # type: ignore[return-value]

    def get_dimension(self) -> int:
        """Return the embedding dimension of the loaded model."""
        return self._load_model().get_sentence_embedding_dimension()
