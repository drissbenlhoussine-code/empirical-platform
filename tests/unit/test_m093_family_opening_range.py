"""MILESTONE-093 Phase 7 -- Family C (opening range breakout): the "cannot trade before the
range completes" structural proof required by the mission, plus determinism tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.opportunity_family_opening_range import (
    OPENING_RANGE_VARIANTS_MINUTES,
    OpeningRangePolicy,
    build_opening_range_plan_geometry,
    compute_opening_range,
    evaluate_opening_range_breakout,
)

_SYMBOL = "AAPL"


def _bar(*, minute: int, o: str, h: str, low: str, c: str, v: int = 1000) -> Bar:
    return Bar(
        instrument=Instrument(_SYMBOL),
        interval=BarInterval.ONE_MINUTE,
        timestamp=datetime(2026, 8, 3, 13, 30 + minute, tzinfo=UTC),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=v,
    )


def _policy(**overrides: object) -> OpeningRangePolicy:
    defaults: dict[str, object] = dict(
        duration_minutes=5,
        minimum_reference_bars=2,
        minimum_volume_ratio=Decimal("1.1"),
        minimum_liquidity_shares=500,
        target_range_multiple=Decimal("2"),
        minimum_reward_risk_ratio=Decimal("1.5"),
    )
    defaults.update(overrides)
    return OpeningRangePolicy(**defaults)  # type: ignore[arg-type]


def test_only_5_and_15_minute_variants_are_declared() -> None:
    assert OPENING_RANGE_VARIANTS_MINUTES == (5, 15)


def test_policy_rejects_a_duration_outside_the_two_declared_variants() -> None:
    with pytest.raises(ValueError, match="duration_minutes must be one of"):
        _policy(duration_minutes=10)


def test_first_eligible_bar_index_equals_the_opening_range_duration() -> None:
    policy = _policy(duration_minutes=5)
    assert policy.first_eligible_bar_index == 5


def test_evaluate_raises_for_any_index_inside_the_opening_range_window() -> None:
    """THE STRUCTURAL PROOF the mission requires: no opportunity can ever have a decision
    timestamp inside the opening-range window -- calling the evaluation function for any
    index < first_eligible_bar_index must be refused, never silently produce a result."""
    policy = _policy(duration_minutes=5)
    bars = [_bar(minute=i, o="100", h="100.50", low="99.80", c="100.20") for i in range(10)]
    opening_range = compute_opening_range(bars, policy=policy)
    assert opening_range is not None
    for index in range(policy.first_eligible_bar_index):
        with pytest.raises(ValueError, match="inside the opening range"):
            evaluate_opening_range_breakout(bars, index, opening_range, policy=policy)


def test_evaluate_succeeds_at_and_after_the_first_eligible_index() -> None:
    policy = _policy(duration_minutes=5)
    bars = [_bar(minute=i, o="100", h="100.50", low="99.80", c="100.20") for i in range(10)]
    opening_range = compute_opening_range(bars, policy=policy)
    assert opening_range is not None
    for index in range(policy.first_eligible_bar_index, len(bars)):
        evaluate_opening_range_breakout(bars, index, opening_range, policy=policy)  # no raise


def test_compute_opening_range_reads_only_the_first_duration_minutes_bars() -> None:
    policy = _policy(duration_minutes=5)
    opening_bars = [_bar(minute=i, o="100", h="101", low="99", c="100.50") for i in range(5)]
    # A poisoned extreme bar appended after the opening range must not affect the range.
    poisoned = [*opening_bars, _bar(minute=5, o="1000", h="1000", low="1000", c="1000")]
    opening_range = compute_opening_range(poisoned, policy=policy)
    assert opening_range is not None
    assert opening_range.high == Decimal("101")
    assert opening_range.low == Decimal("99")


def _breakout_bars() -> list[Bar]:
    return [
        # opening range (5 bars): tight range 99.80-100.60
        _bar(minute=0, o="100.00", h="100.40", low="99.80", c="100.20", v=1000),
        _bar(minute=1, o="100.20", h="100.50", low="100.00", c="100.30", v=1000),
        _bar(minute=2, o="100.30", h="100.60", low="100.10", c="100.40", v=1000),
        _bar(minute=3, o="100.40", h="100.55", low="100.20", c="100.35", v=1000),
        _bar(minute=4, o="100.35", h="100.50", low="100.10", c="100.30", v=1000),
        # post-range reference (2 bars)
        _bar(minute=5, o="100.30", h="100.45", low="100.15", c="100.30", v=900),
        _bar(minute=6, o="100.30", h="100.55", low="100.20", c="100.40", v=900),
        # breakout (evaluation) bar
        _bar(minute=7, o="100.40", h="101.20", low="100.30", c="101.10", v=2500),
    ]


def test_a_genuine_opening_range_breakout_is_accepted() -> None:
    bars = _breakout_bars()
    policy = _policy(duration_minutes=5)
    opening_range = compute_opening_range(bars, policy=policy)
    assert opening_range is not None
    evaluation = evaluate_opening_range_breakout(bars, len(bars) - 1, opening_range, policy=policy)
    assert evaluation.is_candidate
    assert evaluation.reason is None
    geometry = build_opening_range_plan_geometry(evaluation, policy=policy)
    assert geometry is not None
    assert geometry.stop_price == Decimal("99.80")  # the opening range's own low


def test_a_close_inside_the_opening_range_high_is_rejected() -> None:
    bars = _breakout_bars()
    bars[7] = _bar(minute=7, o="100.40", h="100.55", low="100.30", c="100.50", v=2500)
    policy = _policy(duration_minutes=5)
    opening_range = compute_opening_range(bars, policy=policy)
    assert opening_range is not None
    evaluation = evaluate_opening_range_breakout(bars, len(bars) - 1, opening_range, policy=policy)
    assert not evaluation.is_candidate
    assert evaluation.reason == "NO_OPENING_RANGE_BREAKOUT"
