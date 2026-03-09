"""Tests for the embedding service."""

import pytest

from app.services.embedding import EmbeddingService


class TestEmbeddingService:
    """Test suite for EmbeddingService (uses real model — slow first run)."""

    @pytest.fixture
    def embedding_svc(self, mock_cache):
        return EmbeddingService(cache=mock_cache)

    @pytest.mark.asyncio
    async def test_embed_text_returns_correct_dimension(self, embedding_svc):
        """Embedding should return a 384-dim vector."""
        vector = await embedding_svc.embed_text("Hello world")
        assert isinstance(vector, list)
        assert len(vector) == 384

    @pytest.mark.asyncio
    async def test_embed_text_normalized(self, embedding_svc):
        """Embeddings should be roughly unit-normalized."""
        vector = await embedding_svc.embed_text("Hello world")
        import math
        magnitude = math.sqrt(sum(v ** 2 for v in vector))
        assert abs(magnitude - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_embed_batch(self, embedding_svc):
        """Batch embedding should return one vector per input text."""
        texts = ["Hello", "World", "Test sentence"]
        vectors = await embedding_svc.embed_batch(texts)
        assert len(vectors) == 3
        for v in vectors:
            assert len(v) == 384

    @pytest.mark.asyncio
    async def test_similar_texts_have_high_similarity(self, embedding_svc):
        """Semantically similar texts should have high cosine similarity."""
        v1 = await embedding_svc.embed_text("The cat sat on the mat")
        v2 = await embedding_svc.embed_text("A cat was sitting on a mat")
        v3 = await embedding_svc.embed_text("Quantum physics equations")

        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = sum(x ** 2 for x in a) ** 0.5
            mag_b = sum(x ** 2 for x in b) ** 0.5
            return dot / (mag_a * mag_b)

        sim_similar = cosine(v1, v2)
        sim_different = cosine(v1, v3)
        assert sim_similar > sim_different

    @pytest.mark.asyncio
    async def test_caching_stores_embedding(self, embedding_svc, mock_cache):
        """After embedding, the result should be cached."""
        await embedding_svc.embed_text("cache test")
        mock_cache.set_cached_embedding.assert_called_once()

    def test_get_dimension(self, embedding_svc):
        """Dimension property should return 384 for MiniLM."""
        assert embedding_svc.get_dimension() == 384
