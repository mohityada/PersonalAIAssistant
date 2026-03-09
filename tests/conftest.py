"""Shared test fixtures and configuration."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_cache():
    """Mock CacheService that always misses."""
    cache = AsyncMock()
    cache.get_cached_embedding.return_value = None
    cache.get_cached_query.return_value = None
    cache.get.return_value = None
    return cache


@pytest.fixture
def mock_vector_store():
    """Mock VectorStoreService."""
    vs = AsyncMock()
    vs.search.return_value = []
    vs.upsert_vectors.return_value = None
    return vs
