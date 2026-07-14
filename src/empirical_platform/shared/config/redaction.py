"""Secret redaction helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SENSITIVE_TOKENS = ("secret", "token", "password", "key", "credential")
REDACTION_TEXT = "[REDACTED]"


def is_sensitive_key(key: str) -> bool:
    """Return whether a key name should be redacted."""
    lowered = key.lower()
    return any(token in lowered for token in SENSITIVE_TOKENS)


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow-redacted copy of a mapping."""
    return {
        key: REDACTION_TEXT if is_sensitive_key(key) and value is not None else value
        for key, value in values.items()
    }
