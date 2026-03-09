"""Tests for the query parser service."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.query_parser import QueryParser


class TestQueryParser:
    """Test suite for the Claude-powered query parser."""

    @pytest.fixture
    def parser(self, mock_cache):
        with patch("app.services.query_parser.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                anthropic_api_key="test-key",
                claude_model="claude-sonnet-4-20250514",
            )
            return QueryParser(cache=mock_cache)

    @pytest.mark.asyncio
    async def test_parse_image_query(self, parser):
        """Parsing an image query should detect file_type=image."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "file_type": "image",
                        "location": "Jaipur",
                        "keyword": "coffee shop",
                        "requires_reasoning": False,
                        "rephrased_query": "coffee shop photo Jaipur",
                    }
                )
            )
        ]
        with patch.object(parser._client.messages, "create", return_value=mock_response):
            intent = await parser.parse("show coffee shop photo in Jaipur")

        assert intent.file_type == "image"
        assert intent.location == "Jaipur"
        assert intent.keyword == "coffee shop"
        assert intent.requires_reasoning is False

    @pytest.mark.asyncio
    async def test_parse_reasoning_query(self, parser):
        """A reasoning query should set requires_reasoning=True."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "file_type": None,
                        "keyword": "project deadlines",
                        "requires_reasoning": True,
                        "rephrased_query": "summarize project deadlines",
                    }
                )
            )
        ]
        with patch.object(parser._client.messages, "create", return_value=mock_response):
            intent = await parser.parse("Summarize my project deadlines")

        assert intent.requires_reasoning is True

    @pytest.mark.asyncio
    async def test_parse_handles_invalid_json(self, parser):
        """Should gracefully handle non-JSON Claude output."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="I could not parse that.")]
        with patch.object(parser._client.messages, "create", return_value=mock_response):
            intent = await parser.parse("random gibberish query")

        # Should fall back gracefully
        assert intent.requires_reasoning is False
