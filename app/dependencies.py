"""FastAPI dependency injection for shared services."""

from functools import lru_cache

from app.services.cache import CacheService
from app.services.embedding import EmbeddingService
from app.services.query_parser import QueryParser
from app.services.rag import RAGService
from app.services.vector_store import VectorStoreService


@lru_cache
def _cache_service() -> CacheService:
    return CacheService()


@lru_cache
def _vector_store_service() -> VectorStoreService:
    return VectorStoreService()


@lru_cache
def _embedding_service() -> EmbeddingService:
    return EmbeddingService(cache=_cache_service())


@lru_cache
def _query_parser() -> QueryParser:
    return QueryParser(cache=_cache_service())


@lru_cache
def _rag_service() -> RAGService:
    return RAGService(
        query_parser=_query_parser(),
        embedding_service=_embedding_service(),
        vector_store=_vector_store_service(),
        cache=_cache_service(),
    )


def get_rag_service() -> RAGService:
    """FastAPI dependency for the RAG service."""
    return _rag_service()


def get_embedding_service() -> EmbeddingService:
    """FastAPI dependency for the embedding service."""
    return _embedding_service()


def get_vector_store() -> VectorStoreService:
    """FastAPI dependency for the vector store."""
    return _vector_store_service()


def get_cache() -> CacheService:
    """FastAPI dependency for the cache service."""
    return _cache_service()
