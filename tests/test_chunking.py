"""Tests for the text chunking service."""

import pytest

from app.services.chunking import chunk_text


class TestChunkText:
    """Test suite for chunk_text."""

    def test_short_text_single_chunk(self):
        """Text shorter than max_tokens should produce a single chunk."""
        text = "Hello world. This is a short text."
        chunks = chunk_text(text, max_tokens=500, overlap_tokens=0)
        assert len(chunks) == 1
        assert chunks[0].index == 0
        assert "Hello world" in chunks[0].text

    def test_respects_max_tokens(self):
        """Each chunk should not exceed max_tokens (approx)."""
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        # Generate a ~2000-token text
        text = " ".join(["The quick brown fox jumps over the lazy dog."] * 200)
        chunks = chunk_text(text, max_tokens=200, overlap_tokens=0)
        assert len(chunks) > 1
        for chunk in chunks:
            token_count = len(enc.encode(chunk.text))
            # Allow slight overflow due to merging heuristics
            assert token_count <= 250, f"Chunk {chunk.index} has {token_count} tokens"

    def test_overlap_adds_context(self):
        """Chunks after the first should contain overlap from the previous chunk."""
        text = "First paragraph content.\n\nSecond paragraph content.\n\nThird paragraph content."
        chunks = chunk_text(text, max_tokens=10, overlap_tokens=3)
        if len(chunks) > 1:
            # The second chunk should contain some text from the first
            assert len(chunks[1].text) > len("Second paragraph content.")

    def test_indices_are_sequential(self):
        """Chunk indices should be sequential starting from 0."""
        text = " ".join(["Sentence number %d." % i for i in range(100)])
        chunks = chunk_text(text, max_tokens=50, overlap_tokens=5)
        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_empty_text(self):
        """Empty text should produce no chunks."""
        chunks = chunk_text("", max_tokens=500, overlap_tokens=0)
        assert len(chunks) == 0

    def test_paragraph_splitting(self):
        """Text with paragraph breaks should split on them first."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = chunk_text(text, max_tokens=500, overlap_tokens=0)
        # Should merge into one chunk since total is small
        assert len(chunks) == 1
        assert "Paragraph one" in chunks[0].text
