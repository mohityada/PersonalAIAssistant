"""API endpoint tests (require running services or mocks)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a TestClient with mocked dependencies."""
    with patch("app.dependencies._cache_service") as mock_cache_fn, \
         patch("app.dependencies._vector_store_service") as mock_vs_fn, \
         patch("app.dependencies._embedding_service") as mock_emb_fn, \
         patch("app.dependencies._query_parser") as mock_qp_fn, \
         patch("app.dependencies._rag_service") as mock_rag_fn, \
         patch("app.main.get_vector_store") as mock_main_vs, \
         patch("app.main.get_cache") as mock_main_cache:

        # Mock services
        mock_cache = AsyncMock()
        mock_cache_fn.return_value = mock_cache
        mock_main_cache.return_value = mock_cache

        mock_vs = MagicMock()
        mock_vs.ensure_collection.return_value = None
        mock_vs_fn.return_value = mock_vs
        mock_main_vs.return_value = mock_vs

        from app.main import create_app
        from app.db.session import get_db

        app = create_app()

        # Override DB dependency with a mock session that returns no users
        async def mock_get_db():
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db
        yield TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestAuthMiddleware:
    def test_missing_api_key_returns_401(self, client):
        """Requests without X-API-Key should get 401."""
        response = client.post("/api/v1/search", json={"query": "test"})
        assert response.status_code == 401

    def test_invalid_api_key_returns_401(self, client):
        """Requests with invalid API key should get 401."""
        response = client.post(
            "/api/v1/search",
            json={"query": "test"},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401


class TestUploadEndpoint:
    def test_upload_without_auth_returns_401(self, client):
        """Upload without auth should fail."""
        response = client.post(
            "/api/v1/upload",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        assert response.status_code == 401
