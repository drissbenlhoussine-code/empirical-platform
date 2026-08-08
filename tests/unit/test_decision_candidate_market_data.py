"""MILESTONE-057 behavioral tests for the market-data domain:
`Instrument`, `Bar`, `ObservationWindow`.

Pure value-object tests -- no PostgreSQL, no I/O. Proves every invariant
documented in `market_data.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)

_BASE_TIME = datetime(2026, 8, 10, 13, 30, 0, tzinfo=UTC)


def _bar(
    *,
    minute_offset: int = 0,
    open_: str = "100.00",
    high: str = "101.00",
    low: str = "99.50",
    close: str = "100.50",
    volume: int = 10_000,
    instrument: Instrument | None = None,
    interval: BarInterval = BarInterval.ONE_MINUTE,
) -> Bar:
    return Bar(
        instrument=instrument or Instrument("AAPL"),
        interval=interval,
        timestamp=_BASE_TIME + timedelta(minutes=minute_offset),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
    )


# ---------------------------------------------------------------------------
# Instrument
# ---------------------------------------------------------------------------


def test_instrument_accepts_valid_symbol() -> None:
    assert str(Instrument("AAPL")) == "AAPL"


@pytest.mark.parametrize("symbol", ["aapl", "AAPL1", "A.B", "", "TOOLONG"])
def test_instrument_rejects_invalid_symbol(symbol: str) -> None:
    with pytest.raises(ValueError, match="instrument symbol"):
        Instrument(symbol)


# ---------------------------------------------------------------------------
# Bar
# ---------------------------------------------------------------------------


def test_bar_accepts_valid_ohlcv() -> None:
    bar = _bar()
    assert bar.close == Decimal("100.50")


def test_bar_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Bar(
            instrument=Instrument("AAPL"),
            interval=BarInterval.ONE_MINUTE,
            timestamp=datetime(2026, 8, 10, 13, 30, 0),  # noqa: DTZ001
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1000,
        )


def test_bar_rejects_high_below_open() -> None:
    with pytest.raises(ValueError, match="high must be >="):
        _bar(open_="105.00", high="101.00")


def test_bar_rejects_high_below_close() -> None:
    with pytest.raises(ValueError, match="high must be >="):
        _bar(close="105.00", high="101.00")


def test_bar_rejects_high_below_low() -> None:
    with pytest.raises(ValueError, match="high must be >="):
        _bar(high="98.00", low="99.00")


def test_bar_rejects_low_above_open() -> None:
    with pytest.raises(ValueError, match="low must be <="):
        _bar(low="102.00", open_="100.00", high="103.00")


def test_bar_rejects_low_above_close() -> None:
    with pytest.raises(ValueError, match="low must be <="):
        _bar(low="102.00", close="100.00", high="103.00")


def test_bar_rejects_negative_volume() -> None:
    with pytest.raises(ValueError, match="volume must be non-negative"):
        _bar(volume=-1)


def test_bar_accepts_zero_volume() -> None:
    assert _bar(volume=0).volume == 0


def test_bar_rejects_non_decimal_price() -> None:
    with pytest.raises(TypeError, match="open must be a Decimal"):
        Bar(
            instrument=Instrument("AAPL"),
            interval=BarInterval.ONE_MINUTE,
            timestamp=_BASE_TIME,
            open=100.0,  # type: ignore[arg-type]
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1000,
        )


def test_bar_rejects_zero_or_negative_price() -> None:
    with pytest.raises(ValueError, match="open must be positive"):
        _bar(open_="0.00")


# ---------------------------------------------------------------------------
# ObservationWindow
# ---------------------------------------------------------------------------


def test_window_requires_at_least_two_bars() -> None:
    with pytest.raises(ValueError, match="at least 2 bars"):
        ObservationWindow(bars=(_bar(),))


def test_window_accepts_strictly_ordered_bars() -> None:
    window = ObservationWindow(bars=(_bar(minute_offset=0), _bar(minute_offset=1)))
    assert window.evaluation_bar.timestamp == _BASE_TIME + timedelta(minutes=1)
    assert window.reference_bars == (window.bars[0],)


def test_window_rejects_duplicate_timestamps() -> None:
    with pytest.raises(ValueError, match="strictly ordered"):
        ObservationWindow(bars=(_bar(minute_offset=0), _bar(minute_offset=0)))


def test_window_rejects_out_of_order_bars() -> None:
    with pytest.raises(ValueError, match="strictly ordered"):
        ObservationWindow(bars=(_bar(minute_offset=1), _bar(minute_offset=0)))


def test_window_rejects_mismatched_instrument() -> None:
    with pytest.raises(ValueError, match="one instrument"):
        ObservationWindow(
            bars=(
                _bar(minute_offset=0, instrument=Instrument("AAPL")),
                _bar(minute_offset=1, instrument=Instrument("MSFT")),
            )
        )


def test_window_rejects_mismatched_interval() -> None:
    with pytest.raises(ValueError, match="one interval"):
        ObservationWindow(
            bars=(
                _bar(minute_offset=0, interval=BarInterval.ONE_MINUTE),
                _bar(minute_offset=5, interval=BarInterval.FIVE_MINUTE),
            )
        )


def test_window_instrument_and_interval_properties() -> None:
    window = ObservationWindow(bars=(_bar(minute_offset=0), _bar(minute_offset=1)))
    assert window.instrument == Instrument("AAPL")
    assert window.interval == BarInterval.ONE_MINUTE
