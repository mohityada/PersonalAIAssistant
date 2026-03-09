"""Hashing utilities for API keys and cache keys."""

import hashlib
import secrets


def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA-256 for secure storage."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    return secrets.token_urlsafe(32)


def cache_key(*parts: str) -> str:
    """Build a deterministic cache key from variable parts.

    Example:
        cache_key("query", user_id, query_text) → "query:sha256(user_id+query_text)"
    """
    prefix = parts[0] if parts else "key"
    raw = ":".join(parts[1:])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"
