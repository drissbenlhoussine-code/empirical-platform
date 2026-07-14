"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Mapping
from typing import Protocol

import structlog

from empirical_platform.shared.config.redaction import redact_mapping
from empirical_platform.shared.config.settings import LoggingSettings
from empirical_platform.shared.logging.context import get_log_context

StructuredFields = Mapping[str, object]


class BoundFoundationLogger(Protocol):
    """Minimal structured logger protocol."""

    def info(self, event: str, **fields: object) -> object:
        """Emit an info event."""
        ...

    def error(self, event: str, **fields: object) -> object:
        """Emit an error event."""
        ...


def configure_logging(settings: LoggingSettings) -> None:
    """Configure deterministic structured logging."""
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        cache_logger_on_first_use=True,
    )


def fallback_diagnostic(message: str, context: StructuredFields | None = None) -> None:
    """Emit minimal fallback diagnostics without normal logging, Health, or Error."""
    safe = redact_mapping(context or {})
    print(f"foundation_logging_fallback: {message} {safe}", file=sys.stderr)


class FoundationLogger:
    """Non-fatal structured foundation logger."""

    def __init__(
        self,
        logger: BoundFoundationLogger | None = None,
        fallback: Callable[[str, StructuredFields | None], None] = fallback_diagnostic,
    ) -> None:
        self._logger = logger or structlog.get_logger("empirical_platform.foundation")
        self._fallback = fallback

    def info(self, event: str, **fields: object) -> None:
        """Emit a structured info event without failing the caller."""
        self._emit("info", event, fields)

    def error(self, event: str, **fields: object) -> None:
        """Emit a structured error event without failing the caller."""
        self._emit("error", event, fields)

    def _emit(self, level: str, event: str, fields: StructuredFields) -> None:
        context = get_log_context()
        safe_fields = redact_mapping(fields)
        if context is not None:
            safe_fields = {**context.as_dict(), **safe_fields}
        try:
            if level == "info":
                self._logger.info(event, **safe_fields)
            else:
                self._logger.error(event, **safe_fields)
        except Exception:
            self._fallback(event, safe_fields)
