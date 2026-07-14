"""Wall-clock and monotonic-clock abstractions for deterministic tests."""

from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import Protocol


class WallClock(Protocol):
    """Calendar-time source."""

    def now(self) -> datetime:
        """Return a timezone-aware calendar timestamp."""
        ...


class SystemWallClock:
    """System UTC wall clock."""

    def now(self) -> datetime:
        """Return current timezone-aware UTC calendar time."""
        return datetime.now(tz=UTC)


class FixedWallClock:
    """Test-controlled wall clock that may move forward or backward."""

    def __init__(self, current: datetime) -> None:
        if current.tzinfo is None:
            raise ValueError("wall-clock timestamp must be timezone-aware")
        self._current = current

    def now(self) -> datetime:
        """Return the configured timezone-aware timestamp."""
        return self._current

    def set(self, current: datetime) -> None:
        """Set the clock to any timezone-aware timestamp."""
        if current.tzinfo is None:
            raise ValueError("wall-clock timestamp must be timezone-aware")
        self._current = current


class MonotonicClock(Protocol):
    """Elapsed-duration and in-process sequencing clock."""

    def tick(self) -> float:
        """Return a non-decreasing process-local reading."""
        ...

    def elapsed_since(self, started_at: float) -> float:
        """Return elapsed seconds since a prior monotonic reading."""
        ...


class SystemMonotonicClock:
    """System monotonic clock."""

    def tick(self) -> float:
        """Return a process-local monotonic reading."""
        return monotonic()

    def elapsed_since(self, started_at: float) -> float:
        """Return elapsed seconds since a prior monotonic reading."""
        return self.tick() - started_at


class ManualMonotonicClock:
    """Test-controlled monotonic clock."""

    def __init__(self, initial: float = 0.0) -> None:
        self._current = initial

    def tick(self) -> float:
        """Return the current monotonic reading."""
        return self._current

    def advance(self, seconds: float) -> None:
        """Advance the monotonic reading."""
        if seconds < 0:
            raise ValueError("monotonic clock cannot move backward")
        self._current += seconds

    def elapsed_since(self, started_at: float) -> float:
        """Return elapsed seconds since a prior monotonic reading."""
        return self._current - started_at


Clock = WallClock
SystemClock = SystemWallClock
