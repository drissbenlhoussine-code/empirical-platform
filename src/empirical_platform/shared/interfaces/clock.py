"""Time access interface for deterministic tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Abstract time source."""

    def now(self) -> datetime:
        """Return current time."""
        ...


class SystemClock:
    """System UTC clock."""

    def now(self) -> datetime:
        """Return current UTC time."""
        return datetime.now(tz=UTC)
