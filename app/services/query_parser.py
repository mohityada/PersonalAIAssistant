"""Claude-powered natural-language query parser."""

import json
import logging

import anthropic

from app.config import get_settings
from app.models.schemas import ParsedIntent
from app.services.cache import CacheService
from app.utils.hashing import cache_key

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a query parser for a personal AI assistant. Your job is to extract structured intent from a user's natural-language query.

Respond ONLY with a JSON object matching this schema (no markdown, no extra text):
{
  "file_type": "text|pdf|docx|image|md|null",
  "location": "string or null",
  "keyword": "string or null",
  "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"} or null,
  "tags": ["tag1", "tag2"] or null,
  "requires_reasoning": true/false,
  "rephrased_query": "a clean version of the query for embedding search"
}

Rules:
- "requires_reasoning" = true when the user asks WHY, HOW, to SUMMARIZE, COMPARE, or EXPLAIN.
- "requires_reasoning" = false for simple retrieval (find, show, list, get).
- "file_type" should only be set if the query clearly implies a specific type.
- "rephrased_query" should be a clear, concise rewording optimised for semantic search.
"""


class QueryParser:
    """Parse natural-language queries into structured intents using Claude."""

    def __init__(self, cache: CacheService | None = None) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._cache = cache

    async def parse(self, query: str) -> ParsedIntent:
        """Parse a user query into a ``ParsedIntent``.

        Results are cached in Redis to avoid duplicate API calls.
        """
        # Cache check
        if self._cache:
            ck = cache_key("intent", query)
            raw = await self._cache.get(ck)
            if raw:
                logger.debug("Intent cache HIT for: %s", query[:60])
                return ParsedIntent(**json.loads(raw))

        # Call Claude
        logger.info("Parsing query with Claude: %s", query[:80])
        message = self._client.messages.create(
            model=self._model,
            max_tokens=300,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
        )
        response_text = message.content[0].text.strip()

        # Parse JSON response
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning("Claude returned non-JSON: %s", response_text[:200])
            data = {"keyword": query, "requires_reasoning": False, "rephrased_query": query}

        intent = ParsedIntent(**data)

        # Cache store
        if self._cache:
            ck = cache_key("intent", query)
            await self._cache.set(ck, intent.model_dump_json(), ttl=3600)

        logger.info("Parsed intent: type=%s, keyword=%s, reasoning=%s",
                     intent.file_type, intent.keyword, intent.requires_reasoning)
        return intent
