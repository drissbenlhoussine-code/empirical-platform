"""MILESTONE-057 behavioral tests for the deterministic trading strategy
`decision_candidate.strategy.evaluate()`.

Proves the three mandatory categories (Phase 9 of the mission): a positive
LONG_CANDIDATE, a valid NO_TRADE, and genuinely invalid input -- plus
deterministic replay (Phase 15) and reason-code/measurement correctness.
Pure, no PostgreSQL. Independent mathematical re-verification of the
measurements lives in `test_decision_candidate_independent_verification.py`,
deliberately kept separate so it never imports this module's own
calculation.
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
from empirical_platform.decision_candidate.strategy import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    EvaluationReasonCode,
    StrategyParameters,
    TradingDecision,
    evaluate,
)

_BASE_TIME = datetime(2026, 8, 10, 13, 30, 0, tzinfo=UTC)
_INSTRUMENT = Instrument("AAPL")


def _bar(*, minute_offset: int, close: str, high: str | None = None, volume: int) -> Bar:
    close_decimal = Decimal(close)
    high_decimal = Decimal(high) if high is not None else close_decimal
    low_decimal = min(close_decimal, high_decimal) - Decimal("0.10")
    open_decimal = close_decimal
    return Bar(
        instrument=_INSTRUMENT,
        interval=BarInterval.ONE_MINUTE,
        timestamp=_BASE_TIME + timedelta(minutes=minute_offset),
        open=open_decimal,
        high=high_decimal,
        low=low_decimal,
        close=close_decimal,
        volume=volume,
    )


def _reference_window(*, highs: list[str], volumes: list[int]) -> list[Bar]:
    return [
        _bar(minute_offset=i, close=h, high=h, volume=v)
        for i, (h, v) in enumerate(zip(highs, volumes, strict=True))
    ]


def test_strategy_identity_constants() -> None:
    assert STRATEGY_ID == "PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION"
    assert STRATEGY_VERSION == "1"


def test_positive_long_candidate_when_both_conditions_met() -> None:
    reference = _reference_window(
        highs=["100.00", "100.50", "100.20", "100.80", "100.40"],
        volumes=[1000, 1100, 900, 1200, 1000],
    )
    # reference_high = 100.80, reference_average_volume = 1040
    evaluation = _bar(minute_offset=5, close="101.00", high="101.00", volume=1500)
    window = ObservationWindow(bars=(*reference, evaluation))

    outcome = evaluate(window, StrategyParameters(reference_window_size=5))

    assert outcome.decision is TradingDecision.LONG_CANDIDATE
    assert outcome.reasons == (
        EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH,
        EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE,
    )
    assert outcome.measurements.current_close == Decimal("101.00")
    assert outcome.measurements.current_volume == 1500
    assert outcome.measurements.reference_high == Decimal("100.80")
    assert outcome.measurements.reference_average_volume == Decimal("1040")


def test_no_trade_when_price_condition_fails() -> None:
    reference = _reference_window(
        highs=["100.00", "100.50", "100.20", "100.80", "100.40"],
        volumes=[1000, 1100, 900, 1200, 1000],
    )
    # price does not clear reference_high (100.80), but volume does clear 1040
    evaluation = _bar(minute_offset=5, close="100.60", high="100.60", volume=2000)
    window = ObservationWindow(bars=(*reference, evaluation))

    outcome = evaluate(window, StrategyParameters(reference_window_size=5))

    assert outcome.decision is TradingDecision.NO_TRADE
    assert outcome.reasons == (
        EvaluationReasonCode.PRICE_NOT_ABOVE_REFERENCE_HIGH,
        EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE,
    )


def test_no_trade_when_volume_condition_fails() -> None:
    reference = _reference_window(
        highs=["100.00", "100.50", "100.20", "100.80", "100.40"],
        volumes=[1000, 1100, 900, 1200, 1000],
    )
    # price clears reference_high, but volume (500) does not clear 1040
    evaluation = _bar(minute_offset=5, close="101.00", high="101.00", volume=500)
    window = ObservationWindow(bars=(*reference, evaluation))

    outcome = evaluate(window, StrategyParameters(reference_window_size=5))

    assert outcome.decision is TradingDecision.NO_TRADE
    assert outcome.reasons == (
        EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH,
        EvaluationReasonCode.VOLUME_NOT_ABOVE_REFERENCE_AVERAGE,
    )


def test_no_trade_when_both_conditions_fail() -> None:
    reference = _reference_window(
        highs=["100.00", "100.50", "100.20", "100.80", "100.40"],
        volumes=[1000, 1100, 900, 1200, 1000],
    )
    evaluation = _bar(minute_offset=5, close="100.10", high="100.10", volume=200)
    window = ObservationWindow(bars=(*reference, evaluation))

    outcome = evaluate(window, StrategyParameters(reference_window_size=5))

    assert outcome.decision is TradingDecision.NO_TRADE
    assert outcome.reasons == (
        EvaluationReasonCode.PRICE_NOT_ABOVE_REFERENCE_HIGH,
        EvaluationReasonCode.VOLUME_NOT_ABOVE_REFERENCE_AVERAGE,
    )


def test_invalid_input_insufficient_reference_bars_raises_value_error() -> None:
    reference = _reference_window(highs=["100.00", "100.50"], volumes=[1000, 1100])
    evaluation = _bar(minute_offset=2, close="101.00", high="101.00", volume=1500)
    window = ObservationWindow(bars=(*reference, evaluation))

    with pytest.raises(ValueError, match="reference bars"):
        evaluate(window, StrategyParameters(reference_window_size=5))


def test_deterministic_replay_produces_identical_outcome() -> None:
    reference = _reference_window(
        highs=["100.00", "100.50", "100.20", "100.80", "100.40"],
        volumes=[1000, 1100, 900, 1200, 1000],
    )
    evaluation = _bar(minute_offset=5, close="101.00", high="101.00", volume=1500)
    window = ObservationWindow(bars=(*reference, evaluation))
    parameters = StrategyParameters(reference_window_size=5)

    first = evaluate(window, parameters)
    second = evaluate(window, parameters)

    assert first == second


def test_custom_reference_window_size_uses_only_that_many_prior_bars() -> None:
    """A smaller `reference_window_size` uses only the most recent N prior
    bars, not the entire reference history -- proving the window is
    genuinely respected, not merely accepted."""
    reference = _reference_window(
        highs=["999.00", "100.00", "100.50"],  # first bar's extreme high must be excluded
        volumes=[999_999, 1000, 1100],
    )
    evaluation = _bar(minute_offset=3, close="100.60", high="100.60", volume=1200)
    window = ObservationWindow(bars=(*reference, evaluation))

    outcome = evaluate(window, StrategyParameters(reference_window_size=2))

    # reference_high computed only from the last 2 reference bars (100.00, 100.50)
    assert outcome.measurements.reference_high == Decimal("100.50")
    assert outcome.decision is TradingDecision.LONG_CANDIDATE
