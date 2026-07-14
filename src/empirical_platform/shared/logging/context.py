"""Logging context objects."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

_current_log_context: ContextVar[LogContext | None] = ContextVar(
    "current_log_context", default=None
)


@dataclass(frozen=True, slots=True)
class LogContext:
    """Optional correlation context propagated through logs."""

    correlation_id: str
    campaign_id: str | None = None
    run_id: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Return a serializable context mapping."""
        return {
            "correlation_id": self.correlation_id,
            "campaign_id": self.campaign_id,
            "run_id": self.run_id,
        }


def set_log_context(context: LogContext | None) -> None:
    """Set process-local logging context for the current execution context."""
    _current_log_context.set(context)


def get_log_context() -> LogContext | None:
    """Return process-local logging context for the current execution context."""
    return _current_log_context.get()
