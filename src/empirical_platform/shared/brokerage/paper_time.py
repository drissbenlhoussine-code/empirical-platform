"""M085 operation-local time: elapsed work cannot extend a permission.

UTC supplies the absolute epoch; monotonic time accounts for fetches, locks and
preparation. A broker clock response must lie within its local request interval.
There is no assumed clock-skew allowance. Uncertain alignment refuses execution.
The upper instant is conservative for expiry and age, including a stalled wall
clock. Backward wall/monotonic movement is refused rather than corrected silently.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PaperTimeReading:
    utc: datetime
    monotonic: float


class PaperTimeSource(Protocol):
    def read(self) -> PaperTimeReading: ...


class SystemPaperTimeSource:
    def read(self) -> PaperTimeReading:
        return PaperTimeReading(datetime.now(UTC), time.monotonic())


class PaperTimeUncertainError(ValueError):
    """No order may be sent using this operation's uncertain time."""


class PaperTimeWindow:
    def __init__(self, source: PaperTimeSource) -> None:
        self._source = source
        self._first = self._validated(source.read())
        self._last = self._first
        self._broker_anchor: PaperTimeReading | None = None
        self.last_safe_at = self._first.utc

    @staticmethod
    def _validated(reading: PaperTimeReading) -> PaperTimeReading:
        if reading.utc.tzinfo is None or reading.utc.utcoffset() is None:
            raise PaperTimeUncertainError("time source must provide aware UTC")
        if not math.isfinite(reading.monotonic):
            raise PaperTimeUncertainError("monotonic time is not finite")
        return reading

    def now(self) -> datetime:
        current = self._validated(self._source.read())
        if current.utc < self._last.utc or current.monotonic < self._last.monotonic:
            raise PaperTimeUncertainError("clock rollback: execution time is uncertain")
        elapsed = current.monotonic - self._first.monotonic
        upper = max(current.utc, self._first.utc + timedelta(seconds=elapsed))
        if self._broker_anchor is not None:
            upper = max(
                upper,
                self._broker_anchor.utc
                + timedelta(seconds=current.monotonic - self._broker_anchor.monotonic),
            )
        self._last = current
        self.last_safe_at = max(self.last_safe_at, upper)
        return self.last_safe_at

    @property
    def last_monotonic(self) -> float:
        return self._last.monotonic

    def verify_broker(
        self, timestamp: datetime, requested_at: datetime, requested_monotonic: float
    ) -> None:
        received_at = self.now()
        if timestamp.tzinfo is None or not requested_at <= timestamp <= received_at:
            raise PaperTimeUncertainError(
                "broker clock lies outside the request interval; clock alignment is uncertain"
            )
        # The response timestamp may have been sampled at ANY point in the
        # round trip. Propagate its upper bound, not just the local wall clock:
        # apparent agreement inside a wide interval does not prove zero skew.
        upper = timestamp + timedelta(seconds=self._last.monotonic - requested_monotonic)
        self._broker_anchor = PaperTimeReading(upper, self._last.monotonic)
        self.last_safe_at = max(self.last_safe_at, upper)
