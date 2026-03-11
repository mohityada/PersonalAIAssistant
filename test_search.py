import asyncio
from app.db.session import async_session_factory
from app.models.database import User
from app.services.rag import RAGService
from app.services.query_parser import QueryParser
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.services.cache import CacheService
from app.config import get_settings

async def main():
    settings = get_settings()
    parser = QueryParser()
    embedder = EmbeddingService()
    vector = VectorStoreService(host=settings.qdrant_host, port=settings.qdrant_port, collection=settings.qdrant_collection)
    cache = CacheService(redis_url=settings.redis_url)
    
    rag = RAGService(parser, embedder, vector, cache)
    
    try:
        res = await rag.search(query="test", user_id="123", top_k=5)
        print("SUCCESS:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
