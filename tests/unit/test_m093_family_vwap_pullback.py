"""MILESTONE-093 Phase 6 -- Family B (VWAP pullback/reclaim): the VWAP look-ahead proof
required by the mission, plus hand-built determinism tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.opportunity_family_vwap_pullback import (
    VwapPullbackPolicy,
    build_vwap_plan_geometry,
    compute_vwap_series,
    evaluate_vwap_pullback,
)

_SYMBOL = "AAPL"


def _bar(*, minute: int, o: str, h: str, low: str, c: str, v: int = 1000) -> Bar:
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


def test_vwap_series_matches_hand_computed_value_for_one_bar() -> None:
    bars = [_bar(minute=0, o="100", h="101", low="99", c="100", v=1000)]
    series = compute_vwap_series(bars)
    typical = (Decimal("101") + Decimal("99") + Decimal("100")) / Decimal("3")
    assert series[0] == typical  # one bar: VWAP == that bar's own typical price


def test_vwap_series_is_cumulative_across_bars() -> None:
    bars = [
        _bar(minute=0, o="100", h="101", low="99", c="100", v=1000),
        _bar(minute=1, o="100", h="102", low="100", c="101", v=1000),
    ]
    series = compute_vwap_series(bars)
    tp0 = (Decimal("101") + Decimal("99") + Decimal("100")) / Decimal("3")
    tp1 = (Decimal("102") + Decimal("100") + Decimal("101")) / Decimal("3")
    expected_vwap1 = (tp0 * 1000 + tp1 * 1000) / Decimal("2000")
    assert series[1] == expected_vwap1


def test_vwap_series_entry_i_is_unaffected_by_any_bar_after_i() -> None:
    """THE LOOK-AHEAD PROOF the mission requires: `vwap_series[i]` computed from a bar
    sequence must be IDENTICAL whether or not bars after index `i` exist at all."""
    bars = [
        _bar(minute=0, o="100", h="101", low="99", c="100", v=1000),
        _bar(minute=1, o="100", h="102", low="100", c="101", v=1500),
        _bar(minute=2, o="101", h="103", low="100.50", c="102", v=800),
    ]
    full_series = compute_vwap_series(bars)

    # An impossible, extreme future bar appended at the very end must not change ANY
    # earlier entry of the series.
    poisoned_bars = [
        *bars,
        _bar(minute=3, o="1000000", h="1000000", low="1000000", c="1000000", v=999_999_999),
    ]
    poisoned_series = compute_vwap_series(poisoned_bars)
    assert poisoned_series[: len(bars)] == full_series

    # And a truncated series (as if bar 2 never existed) must still agree with the full
    # series on every index it shares -- proving index i never reads index i+1 either.
    truncated_series = compute_vwap_series(bars[:2])
    assert truncated_series == full_series[:2]


def _policy(**overrides: object) -> VwapPullbackPolicy:
    defaults: dict[str, object] = dict(
        constructive_lookback_bars=3,
        pullback_bars=2,
        minimum_volume_ratio=Decimal("1.1"),
        minimum_liquidity_shares=500,
        target_range_multiple=Decimal("2"),
        minimum_reward_risk_ratio=Decimal("1.5"),
    )
    defaults.update(overrides)
    return VwapPullbackPolicy(**defaults)  # type: ignore[arg-type]


def _constructive_pullback_reclaim_bars() -> list[Bar]:
    return [
        # constructive phase (3 bars): price above its own running VWAP throughout
        _bar(minute=0, o="100.00", h="100.80", low="99.90", c="100.60", v=1500),
        _bar(minute=1, o="100.60", h="101.20", low="100.40", c="101.00", v=1500),
        _bar(minute=2, o="101.00", h="101.60", low="100.80", c="101.40", v=1500),
        # pullback phase (2 bars): dips to/below the running VWAP
        _bar(minute=3, o="101.40", h="101.50", low="100.00", c="100.30", v=1200),
        _bar(minute=4, o="100.30", h="100.60", low="99.80", c="100.10", v=1200),
        # reclaim (evaluation) bar: bullish close above the current VWAP, strong volume
        _bar(minute=5, o="100.20", h="101.80", low="100.10", c="101.70", v=2500),
    ]


def test_a_genuine_pullback_and_reclaim_is_accepted() -> None:
    bars = _constructive_pullback_reclaim_bars()
    series = compute_vwap_series(bars)
    evaluation = evaluate_vwap_pullback(bars, len(bars) - 1, series, policy=_policy())
    assert evaluation.is_candidate
    assert evaluation.reason is None
    geometry = build_vwap_plan_geometry(evaluation, policy=_policy())
    assert geometry is not None
    assert geometry.stop_price == Decimal("99.80")  # pullback window's own low


def test_no_pullback_below_vwap_is_rejected() -> None:
    bars = _constructive_pullback_reclaim_bars()
    # Keep the pullback bars entirely above the running VWAP (no dip at all) -- pushed well
    # above the ~101.35 VWAP the evaluation bar will see.
    bars[3] = _bar(minute=3, o="102.50", h="102.60", low="102.30", c="102.40", v=1200)
    bars[4] = _bar(minute=4, o="102.40", h="102.60", low="102.30", c="102.50", v=1200)
    series = compute_vwap_series(bars)
    evaluation = evaluate_vwap_pullback(bars, len(bars) - 1, series, policy=_policy())
    assert not evaluation.is_candidate
    assert evaluation.reason == "NO_VWAP_PULLBACK"


def test_no_reclaim_above_vwap_is_rejected() -> None:
    bars = _constructive_pullback_reclaim_bars()
    # Evaluation bar stays below VWAP -- no reclaim.
    bars[5] = _bar(minute=5, o="100.20", h="100.40", low="100.00", c="100.15", v=2500)
    series = compute_vwap_series(bars)
    evaluation = evaluate_vwap_pullback(bars, len(bars) - 1, series, policy=_policy())
    assert not evaluation.is_candidate
    assert evaluation.reason in {"NO_VWAP_RECLAIM", "WEAK_RECLAIM_VOLUME"}
