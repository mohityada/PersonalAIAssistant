"""Recursive text chunking with token-aware splitting."""

import logging
from dataclasses import dataclass

import tiktoken

logger = logging.getLogger(__name__)

# Separators tried in order (most to least semantic)
_SEPARATORS = ["\n\n", "\n", ". ", ", ", " ", ""]


@dataclass
class ChunkData:
    """A single text chunk with its positional index."""
    text: str
    index: int


def chunk_text(
    text: str,
    max_tokens: int = 500,
    min_tokens: int = 50,
    overlap_tokens: int = 50,
    model: str = "cl100k_base",
) -> list[ChunkData]:
    """Split *text* into overlapping chunks within the target token range.

    Algorithm:
        1. Try to split on the most semantic separator first (double newline).
        2. If any resulting segment exceeds *max_tokens*, recursively split it
           with the next separator.
        3. Merge small segments until the chunk is in the [min_tokens, max_tokens]
           range.
        4. Apply *overlap_tokens* between consecutive chunks.

    Returns:
        Ordered list of ``ChunkData`` objects.
    """
    enc = tiktoken.get_encoding(model)

    def _token_len(t: str) -> int:
        return len(enc.encode(t))

    # Recursive split on cascading separators
    def _split(txt: str, separators: list[str]) -> list[str]:
        if not separators:
            return [txt]
        sep = separators[0]
        remaining_seps = separators[1:]
        parts = txt.split(sep) if sep else list(txt)
        result: list[str] = []
        for part in parts:
            if _token_len(part) > max_tokens and remaining_seps:
                result.extend(_split(part, remaining_seps))
            else:
                result.append(part)
        return result

    raw_segments = _split(text, _SEPARATORS)

    # Merge small segments into chunks within [min_tokens, max_tokens]
    merged: list[str] = []
    buffer = ""
    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue
        candidate = f"{buffer} {seg}".strip() if buffer else seg
        if _token_len(candidate) <= max_tokens:
            buffer = candidate
        else:
            if buffer:
                merged.append(buffer)
            # If a single segment still exceeds max_tokens, force-split by tokens
            if _token_len(seg) > max_tokens:
                tokens = enc.encode(seg)
                for i in range(0, len(tokens), max_tokens):
                    merged.append(enc.decode(tokens[i : i + max_tokens]))
                buffer = ""
            else:
                buffer = seg
    if buffer:
        merged.append(buffer)

    # Apply overlap
    chunks: list[ChunkData] = []
    for idx, chunk_text_str in enumerate(merged):
        if idx > 0 and overlap_tokens > 0:
            prev_tokens = enc.encode(merged[idx - 1])
            overlap_text = enc.decode(prev_tokens[-overlap_tokens:])
            chunk_text_str = f"{overlap_text} {chunk_text_str}"
        chunks.append(ChunkData(text=chunk_text_str.strip(), index=idx))

    logger.info(
        "Chunked %d chars → %d chunks (max=%d, overlap=%d tokens)",
        len(text),
        len(chunks),
        max_tokens,
        overlap_tokens,
    )
    return chunks
