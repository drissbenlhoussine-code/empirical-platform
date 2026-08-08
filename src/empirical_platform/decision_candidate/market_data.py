"""Minimum first-class market-data representation for trading evaluation.

MILESTONE-057. Deliberately narrow: only what the first trading vertical
slice genuinely requires. `Instrument`/`Bar`/`ObservationWindow` are pure,
persistence-ignorant value objects -- no I/O, no randomness, no wall-clock
reads. `Decimal` is used for all price fields to avoid binary
floating-point precision loss on financial data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

_SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}$")


@dataclass(frozen=True, slots=True)
class Instrument:
    """A supported US-listed equity or ETF ticker symbol.

    Scope: US-listed common equities and ETFs only (see
    MILESTONE_057_TRADING_EVALUATION_SCOPE_AND_DESIGN.md Section 3). Bare
    ticker symbols only -- no exchange suffix, no share-class dot/dash
    notation -- since neither is required by this milestone's own slice.
    """

    symbol: str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not _SYMBOL_PATTERN.match(self.symbol):
            raise ValueError("instrument symbol must match ^[A-Z]{1,5}$")

    def __str__(self) -> str:
        return self.symbol


class BarInterval(StrEnum):
    """Supported intraday bar intervals (see scope Section 3)."""

    ONE_MINUTE = "ONE_MINUTE"
    FIVE_MINUTE = "FIVE_MINUTE"


@dataclass(frozen=True, slots=True)
class Bar:
    """One immutable OHLCV bar for one instrument, at one interval, at one timestamp.

    `timestamp` marks the bar's close (the instant its OHLCV values became
    fully known) and must be timezone-aware. All price fields use `Decimal`;
    `volume` is a non-negative integer share count.
    """

    instrument: Instrument
    interval: BarInterval
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        if not isinstance(self.interval, BarInterval):
            raise TypeError("interval must be a BarInterval")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        for field_name in ("open", "high", "low", "close"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{field_name} must be a Decimal")
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if not isinstance(self.volume, int) or isinstance(self.volume, bool):
            raise TypeError("volume must be an int")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.high < self.open or self.high < self.close or self.high < self.low:
            raise ValueError("high must be >= open, close, and low")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be <= open and close")


@dataclass(frozen=True, slots=True)
class ObservationWindow:
    """An ordered, immutable sequence of bars for one instrument at one
    interval, ending at the bar under evaluation.

    The last bar (`evaluation_bar`) is the bar being evaluated; every prior
    bar (`reference_bars`) strictly precedes it in time. This ordering is
    the entire look-ahead-bias defense: a strategy given this window can
    only read `reference_bars` for its reference calculation and the
    `evaluation_bar` for the current price/volume -- there is no bar in the
    window that occurs after the evaluation point (see MILESTONE-057 Phase
    18 look-ahead audit in governance).
    """

    bars: tuple[Bar, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bars, tuple):
            raise TypeError("bars must be a tuple")
        if len(self.bars) < 2:
            raise ValueError("an ObservationWindow requires at least 2 bars")
        for previous, current in zip(self.bars, self.bars[1:], strict=False):
            if current.instrument != previous.instrument:
                raise ValueError("all bars in an ObservationWindow must share one instrument")
            if current.interval != previous.interval:
                raise ValueError("all bars in an ObservationWindow must share one interval")
            if current.timestamp <= previous.timestamp:
                raise ValueError("bars must be strictly ordered by timestamp with no duplicates")

    @property
    def instrument(self) -> Instrument:
        """Return the single instrument shared by every bar in this window."""
        return self.bars[0].instrument

    @property
    def interval(self) -> BarInterval:
        """Return the single interval shared by every bar in this window."""
        return self.bars[0].interval

    @property
    def evaluation_bar(self) -> Bar:
        """Return the bar under evaluation -- the last, most recent bar."""
        return self.bars[-1]

    @property
    def reference_bars(self) -> tuple[Bar, ...]:
        """Return every bar strictly preceding the evaluation bar, in order."""
        return self.bars[:-1]
