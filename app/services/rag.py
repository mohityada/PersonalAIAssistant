"""RAG orchestrator — ties together query parsing, search, and reasoning."""

import json
import logging

import anthropic

from app.config import get_settings
from app.models.schemas import (
    AskResponse,
    ParsedIntent,
    SearchResponse,
    SearchResult,
    SourceReference,
)
from app.services.cache import CacheService
from app.services.embedding import EmbeddingService
from app.services.query_parser import QueryParser
from app.services.vector_store import VectorStoreService

logger = logging.getLogger(__name__)

_RAG_SYSTEM_PROMPT = """\
You are a helpful personal AI assistant. Answer the user's question using ONLY the provided context.
If the context does not contain enough information, say so honestly.
Be concise but thorough. Cite the source filenames in your answer when relevant.
"""

# Maximum context chars sent to Claude to keep costs down
_MAX_CONTEXT_CHARS = 6000


class RAGService:
    """End-to-end Retrieval-Augmented Generation pipeline."""

    def __init__(
        self,
        query_parser: QueryParser,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreService,
        cache: CacheService | None = None,
    ) -> None:
        settings = get_settings()
        self._parser = query_parser
        self._embedder = embedding_service
        self._vector_store = vector_store
        self._cache = cache
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._top_k = settings.search_top_k

    # ── search (no LLM reasoning) ───────────────────

    async def search(
        self, query: str, user_id: str, filters: dict | None = None, top_k: int | None = None
    ) -> SearchResponse:
        """Semantic search: parse → embed → vector search → return results."""
        top_k = top_k or self._top_k

        # Cache check
        if self._cache:
            cached = await self._cache.get_cached_query(user_id, query, filters)
            if cached:
                cached["cached"] = True
                return SearchResponse(**cached)

        # 1. Parse intent to extract structured filters
        intent: ParsedIntent = await self._parser.parse(query)
        merged_filters = self._merge_filters(intent, filters)

        # 2. Embed query
        search_text = intent.rephrased_query or query
        query_vector = await self._embedder.embed_text(search_text)

        # 3. Vector search
        hits = await self._vector_store.search(
            query_vector=query_vector,
            user_id=user_id,
            filters=merged_filters,
            top_k=top_k,
        )

        # 4. Build response
        results = self._hits_to_results(hits)
        response = SearchResponse(query=query, results=results, total=len(results))

        # Cache store
        if self._cache:
            await self._cache.set_cached_query(
                user_id, query, filters, response.model_dump(mode="json")
            )

        return response

    # ── ask (with optional LLM reasoning) ───────────

    async def ask(
        self, question: str, user_id: str, filters: dict | None = None
    ) -> AskResponse:
        """Full RAG pipeline: parse → search → conditionally reason with Claude."""
        # 1. Parse intent
        intent: ParsedIntent = await self._parser.parse(question)
        merged_filters = self._merge_filters(intent, filters)

        # 2. Embed & search
        search_text = intent.rephrased_query or question
        query_vector = await self._embedder.embed_text(search_text)
        hits = await self._vector_store.search(
            query_vector=query_vector,
            user_id=user_id,
            filters=merged_filters,
            top_k=self._top_k,
        )
        results = self._hits_to_results(hits)

        # 3. Smart routing: simple retrieval vs. reasoning
        if not intent.requires_reasoning:
            # Return results directly without an LLM call
            summary_parts = []
            for r in results:
                chunk = r.chunk_text or r.caption or ""
                summary_parts.append(f"- **{r.filename}**: {chunk[:200]}")
            answer = "\n".join(summary_parts) if summary_parts else "No relevant results found."
            return AskResponse(
                question=question,
                answer=answer,
                sources=self._results_to_sources(results),
                reasoning_used=False,
            )

        # 4. Build context for Claude (truncate to stay within budget)
        context = self._build_context(results)

        # 5. Call Claude for reasoning
        logger.info("Calling Claude for RAG reasoning (%d chars context)", len(context))
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_RAG_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                }
            ],
        )
        answer = message.content[0].text.strip()

        return AskResponse(
            question=question,
            answer=answer,
            sources=self._results_to_sources(results),
            reasoning_used=True,
        )

    # ── private helpers ─────────────────────────────

    @staticmethod
    def _merge_filters(intent: ParsedIntent, explicit: dict | None) -> dict | None:
        """Merge intent-derived filters with explicitly provided ones."""
        merged: dict = {}
        if intent.file_type:
            merged["file_type"] = intent.file_type
        if intent.location:
            merged["location"] = intent.location
        if explicit:
            merged.update(explicit)
        return merged or None

    @staticmethod
    def _hits_to_results(hits: list[dict]) -> list[SearchResult]:
        """Convert raw Qdrant hits to ``SearchResult`` models."""
        results: list[SearchResult] = []
        seen_files: set[str] = set()
        for hit in hits:
            payload = hit.get("payload", {})
            file_id = payload.get("file_id", "")
            # Deduplicate by file_id
            if file_id in seen_files:
                continue
            seen_files.add(file_id)
            results.append(
                SearchResult(
                    file_id=file_id,
                    filename=payload.get("filename", "unknown"),
                    file_type=payload.get("file_type", "unknown"),
                    score=hit.get("score", 0.0),
                    chunk_text=payload.get("chunk_text"),
                    caption=payload.get("caption"),
                    location=payload.get("location"),
                    tags=payload.get("tags"),
                )
            )
        return results

    @staticmethod
    def _results_to_sources(results: list[SearchResult]) -> list[SourceReference]:
        return [
            SourceReference(
                file_id=r.file_id,
                filename=r.filename,
                chunk_text=r.chunk_text,
                score=r.score,
            )
            for r in results
        ]

    @staticmethod
    def _build_context(results: list[SearchResult]) -> str:
        """Assemble retrieved chunks into a context string, respecting the char budget."""
        parts: list[str] = []
        total = 0
        for r in results:
            text = r.chunk_text or r.caption or ""
            entry = f"[{r.filename}]\n{text}\n"
            if total + len(entry) > _MAX_CONTEXT_CHARS:
                break
            parts.append(entry)
            total += len(entry)
        return "\n".join(parts)
