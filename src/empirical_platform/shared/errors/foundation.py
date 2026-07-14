"""Foundation error model with safe structured context."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Self

from empirical_platform.shared.config.redaction import redact_mapping


class FoundationErrorCategory(StrEnum):
    """Specification-owned foundation error categories."""

    CONFIGURATION = "configuration_error"
    PERSISTENCE = "persistence_error"
    OBJECT_STORAGE = "object_storage_error"
    TIME_IDENTIFIER = "time_identifier_error"
    FOUNDATION = "foundation_error"


class FoundationError(Exception):
    """Boundary-safe foundation exception."""

    def __init__(
        self,
        *,
        category: FoundationErrorCategory,
        message: str,
        layer: str,
        operation: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        self.category = category
        self.safe_message = message
        self.layer = layer
        self.operation = operation
        self.context = redact_mapping(context or {})
        super().__init__(message)

    @classmethod
    def wrap(
        cls,
        cause: BaseException,
        *,
        category: FoundationErrorCategory,
        message: str,
        layer: str,
        operation: str,
        context: Mapping[str, Any] | None = None,
    ) -> Self:
        """Wrap a lower-level exception without exposing its raw type in public fields."""
        error = cls(
            category=category,
            message=message,
            layer=layer,
            operation=operation,
            context=context,
        )
        error.__cause__ = cause
        return error

    def as_dict(self) -> dict[str, Any]:
        """Return a structured, safe representation suitable for logs or diagnostics."""
        return {
            "category": self.category.value,
            "message": self.safe_message,
            "layer": self.layer,
            "operation": self.operation,
            "context": self.context,
        }
