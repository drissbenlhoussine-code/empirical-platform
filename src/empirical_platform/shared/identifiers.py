"""Opaque runtime identifiers without governance namespace prefixes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory


@dataclass(frozen=True, slots=True)
class RuntimeIdentifier:
    """Opaque runtime identifier carrying no domain meaning."""

    value: str

    def __post_init__(self) -> None:
        try:
            parsed = uuid.UUID(self.value, version=4)
        except ValueError as exc:
            raise ValueError("runtime identifier must be a UUIDv4 value") from exc
        if str(parsed) != self.value or parsed.version != 4:
            raise ValueError("runtime identifier must be a canonical UUIDv4 value")

    def __str__(self) -> str:
        return self.value


class RuntimeIdentifierGenerator(Protocol):
    """Runtime identifier generation contract."""

    def generate(self) -> RuntimeIdentifier:
        """Generate an opaque runtime identifier."""
        ...


class UuidRuntimeIdentifierGenerator:
    """Collision-resistant UUIDv4 runtime identifier generator."""

    def generate(self) -> RuntimeIdentifier:
        """Generate an opaque runtime identifier."""
        try:
            return RuntimeIdentifier(str(uuid.uuid4()))
        except Exception as exc:
            raise FoundationError.wrap(
                exc,
                category=FoundationErrorCategory.TIME_IDENTIFIER,
                message="Runtime identifier generation failed",
                layer="identifier",
                operation="generate",
            ) from exc


class DeterministicRuntimeIdentifierGenerator:
    """Deterministic test substitute for runtime identifiers."""

    def __init__(self, values: list[str]) -> None:
        self._values = list(values)

    def generate(self) -> RuntimeIdentifier:
        """Return the next configured identifier."""
        if not self._values:
            raise FoundationError(
                category=FoundationErrorCategory.TIME_IDENTIFIER,
                message="No deterministic runtime identifier remains",
                layer="identifier",
                operation="generate",
            )
        return RuntimeIdentifier(self._values.pop(0))


def is_valid_runtime_identifier(value: str) -> bool:
    """Return whether a value is a canonical UUIDv4 runtime identifier."""
    try:
        RuntimeIdentifier(value)
    except ValueError:
        return False
    return True
