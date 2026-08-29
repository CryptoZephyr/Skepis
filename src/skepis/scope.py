"""Validation helpers for identifiers used to isolate Skepis state."""

from __future__ import annotations


def normalize_scope_identifier(value: str, *, label: str) -> str:
    """Return an identifier safe to use in the slash-delimited Sibyl key."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    normalized = value.strip()
    if any(char in normalized for char in "/\\\r\n\x00"):
        raise ValueError(f"{label} must not contain path separators or control characters")
    return normalized
