"""Logging context objects."""

from __future__ import annotations

from dataclasses import dataclass


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
