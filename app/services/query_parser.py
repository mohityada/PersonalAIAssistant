"""Claude-powered natural-language query parser."""

import json
import logging

import anthropic

from app.config import get_settings
from app.models.schemas import ParsedIntent
from app.services.cache import CacheService
from app.utils.hashing import cache_key

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Extract query intent. Return ONLY raw JSON, no markdown, omit null fields:\n"
    '{"file_type":"pdf|docx|image|text|md","location":str,"keyword":str,'
    '"date_range":{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"},"tags":[str],'
    '"filename":str,"requires_reasoning":bool,"rephrased_query":str}\n'
    "requires_reasoning=true for WHO/WHAT/WHY/HOW/summarize/compare/explain/extract; "
    "false for simple find/show. filename=exact or partial. rephrased_query=short embedding-friendly rewrite."
)

_FALLBACK = {"requires_reasoning": False}


class QueryParser:
    """Parse natural-language queries into structured intents using Claude."""

    def __init__(self, cache: CacheService | None = None) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._cache = cache

    async def parse(self, query: str) -> ParsedIntent:
        """Parse a user query into a ``ParsedIntent``, with Redis caching."""
        ck = cache_key("intent", query) if self._cache else None

        if ck and (raw := await self._cache.get(ck)):
            logger.debug("Intent cache HIT: %.60s", query)
            return ParsedIntent(**json.loads(raw))

        logger.info("Parsing query with Claude: %.80s", query)

        message = self._client.messages.create(
            model=self._model,
            max_tokens=100,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
        )

        intent = self._parse_response(message.content[0].text, query)

        if ck:
            await self._cache.set(ck, intent.model_dump_json(exclude_none=True), ttl=3600)

        logger.info("Parsed intent: type=%s keyword=%s reasoning=%s",
                    intent.file_type, intent.keyword, intent.requires_reasoning)
        return intent

    def _parse_response(self, response_text: str, query: str) -> ParsedIntent:
        clean = response_text.strip().removeprefix("```json").removeprefix("```")
        if clean.endswith("```"):
            clean = clean[:-3]
        try:
            data = json.loads(clean.strip())
        except json.JSONDecodeError:
            logger.warning("Claude returned non-JSON: %.200s", response_text)
            data = {**_FALLBACK, "keyword": query, "rephrased_query": query}
        return ParsedIntent(**data)