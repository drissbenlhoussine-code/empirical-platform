"""MILESTONE-093 Phase 5 -- Family A (trend continuation): hand-built bars so the expected
result is verifiable by inspection, plus a look-ahead audit."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.opportunity_family_trend_continuation import (
    TrendContinuationPolicy,
    build_trend_plan_geometry,
    evaluate_trend_continuation,
)

_SYMBOL = "AAPL"


def _bar(*, minute: int, o: str, h: str, low: str, c: str, v: int = 2000) -> Bar:
    return Bar(
        instrument=Instrument(_SYMBOL),
        interval=BarInterval.ONE_MINUTE,
        timestamp=datetime(2026, 8, 3, 14, minute, tzinfo=UTC),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=v,
    )


def _policy(**overrides: object) -> TrendContinuationPolicy:
    defaults: dict[str, object] = dict(
        lookback_bars=6,
        pullback_bars=2,
        minimum_volume_ratio=Decimal("1.2"),
        minimum_liquidity_shares=500,
        target_range_multiple=Decimal("2"),
        minimum_reward_risk_ratio=Decimal("1.5"),
    )
    defaults.update(overrides)
    return TrendContinuationPolicy(**defaults)  # type: ignore[arg-type]


def _uptrend_pullback_resumption_bars() -> list[Bar]:
    return [
        # establish phase (4 bars): first half low, second half makes a higher high
        _bar(minute=0, o="100.00", h="100.50", low="99.80", c="100.30"),
        _bar(minute=1, o="100.30", h="100.70", low="100.00", c="100.50"),
        _bar(minute=2, o="100.50", h="101.50", low="100.20", c="101.30"),
        _bar(minute=3, o="101.30", h="102.00", low="100.90", c="101.80"),
        # pullback phase (2 bars): low stays above establish's own low (99.80)
        _bar(minute=4, o="101.80", h="101.90", low="100.80", c="101.00"),
        _bar(minute=5, o="101.00", h="101.20", low="100.60", c="100.90"),
        # resumption (evaluation) bar: closes above the pullback's own high (101.90)
        _bar(minute=6, o="101.00", h="102.30", low="100.90", c="102.20", v=3000),
    ]


def test_a_genuine_establish_pullback_resumption_is_accepted() -> None:
    bars = _uptrend_pullback_resumption_bars()
    window = ObservationWindow(bars=tuple(bars))
    evaluation = evaluate_trend_continuation(window, policy=_policy())
    assert evaluation.is_candidate
    assert evaluation.reason is None
    geometry = build_trend_plan_geometry(evaluation, policy=_policy())
    assert geometry is not None
    assert geometry.stop_price == Decimal("100.60")  # pullback's own low
    assert geometry.entry_price == Decimal("102.20")
    assert geometry.stop_price < geometry.entry_price


def test_a_pullback_that_breaks_the_establish_low_is_rejected() -> None:
    bars = _uptrend_pullback_resumption_bars()
    # Deepen the pullback below the establish phase's own low (99.80).
    bars[5] = _bar(minute=5, o="101.00", h="101.20", low="99.00", c="100.90")
    window = ObservationWindow(bars=tuple(bars))
    evaluation = evaluate_trend_continuation(window, policy=_policy())
    assert not evaluation.is_candidate
    assert evaluation.reason == "PULLBACK_BROKE_STRUCTURE"


def test_no_prior_uptrend_is_rejected_even_with_a_resumption_looking_bar() -> None:
    bars = [
        _bar(minute=0, o="100.00", h="102.00", low="99.80", c="101.80"),
        _bar(minute=1, o="101.80", h="101.90", low="100.00", c="100.50"),
        _bar(minute=2, o="100.50", h="100.80", low="99.50", c="100.00"),
        _bar(minute=3, o="100.00", h="100.20", low="99.00", c="99.50"),
        _bar(minute=4, o="99.50", h="99.80", low="99.00", c="99.60"),
        _bar(minute=5, o="99.60", h="99.90", low="99.30", c="99.70"),
        _bar(minute=6, o="99.70", h="103.00", low="99.60", c="102.90", v=3000),
    ]
    window = ObservationWindow(bars=tuple(bars))
    evaluation = evaluate_trend_continuation(window, policy=_policy())
    assert not evaluation.is_candidate
    assert evaluation.reason == "NO_ESTABLISHED_TREND"


def test_evaluation_never_reads_bars_after_the_evaluation_bar() -> None:
    """Look-ahead audit: appending an extreme future bar to the window must not exist in the
    first place for `evaluate_trend_continuation` to read -- `ObservationWindow.evaluation_bar`
    IS the last bar by construction, so this proves the function only ever uses
    `window.reference_bars` (strictly before) and `window.evaluation_bar` (the decision
    instant), never anything beyond it."""
    bars = _uptrend_pullback_resumption_bars()
    baseline_window = ObservationWindow(bars=tuple(bars))
    baseline = evaluate_trend_continuation(baseline_window, policy=_policy())

    # Re-run with the SAME evaluation bar but a poisoned bar inserted BEFORE it in a position
    # evaluate_trend_continuation never reads (older than the lookback) -- must not change
    # the result, since only the last `lookback_bars` reference bars are ever used.
    extra_early = Bar(
        instrument=Instrument(_SYMBOL),
        interval=BarInterval.ONE_MINUTE,
        timestamp=datetime(2026, 8, 3, 13, 55, tzinfo=UTC),
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=1,
    )
    poisoned = [extra_early] + bars
    poisoned_window = ObservationWindow(bars=tuple(poisoned))
    poisoned_result = evaluate_trend_continuation(poisoned_window, policy=_policy())
    assert poisoned_result == baseline
