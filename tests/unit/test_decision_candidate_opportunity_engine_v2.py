"""MILESTONE-092 -- V2 domain unit tests: determinism, gate order, and the new entry-
quality/liquidity/geometry/feasibility gates. Every arithmetic expectation here is hand-
computed, mirroring V1's own `test_decision_candidate_opportunity_engine.py` discipline."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.opportunity_engine_v2 import (
    OpportunityEnginePolicyV2,
    RejectionReasonV2,
    build_trade_plan_geometry_v2,
    entry_quality_refusal,
    evaluate_structure_v2,
    liquidity_refusal_v2,
    plan_geometry_refusal_v2,
    position_size_v2,
    reward_risk_refusal_v2,
    time_to_target_refusal,
)

_SYMBOL = "AAPL"


def _bar(*, minute: int, o: str, h: str, low: str, c: str, v: int) -> Bar:
    return Bar(
        instrument=Instrument(_SYMBOL),
        interval=BarInterval.ONE_MINUTE,
        timestamp=datetime(2026, 6, 10, 14, minute, tzinfo=UTC),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=v,
    )


def _policy(**overrides: object) -> OpportunityEnginePolicyV2:
    defaults: dict[str, object] = {
        "policy_version": "M092-V2-TEST",
        "structure_lookback_bars": 5,
        "minimum_recent_share_volume": 100,
        "relative_liquidity_multiple": None,
        "minimum_volume_ratio": Decimal("1.5"),
        "minimum_close_location_value": Decimal("0.6"),
        "target_range_multiple": Decimal("3"),
        "minimum_reward_risk_ratio": Decimal("1.5"),
        "time_to_target_feasibility_enabled": False,
        "time_to_target_safety_factor": Decimal("1"),
        "maximum_loss_per_trade": Decimal("100"),
        "top_n": 5,
        "entry_tolerance_percent": Decimal("0.5"),
        "opportunity_validity_seconds": 300,
    }
    defaults.update(overrides)
    return OpportunityEnginePolicyV2(**defaults)  # type: ignore[arg-type]


def _breakout_window() -> ObservationWindow:
    """5 flat reference bars (range_high=100.50, range_low=99.00) + a strong breakout bar
    closing at 101.50 near its own high (close_location_value high) on 2.5x average volume.
    """
    bars = [
        _bar(minute=0, o="100.00", h="100.50", low="99.00", c="100.00", v=1000),
        _bar(minute=1, o="100.00", h="100.40", low="99.20", c="100.20", v=1000),
        _bar(minute=2, o="100.20", h="100.30", low="99.40", c="100.30", v=1000),
        _bar(minute=3, o="100.30", h="100.45", low="99.60", c="100.40", v=1000),
        _bar(minute=4, o="100.40", h="100.50", low="99.80", c="100.50", v=1000),
        # Breakout bar: high=101.60, low=101.40, close=101.55
        # -> CLV = (101.55-101.40)/(101.60-101.40) = 0.75
        _bar(minute=5, o="101.45", h="101.60", low="101.40", c="101.55", v=2500),
    ]
    return ObservationWindow(bars=tuple(bars))


def test_structure_evaluation_is_deterministic_and_measures_new_fields() -> None:
    window = _breakout_window()
    is_candidate, m = evaluate_structure_v2(window, lookback_bars=5)
    assert is_candidate is True
    assert m.range_high == Decimal("100.50")
    assert m.range_low == Decimal("99.00")
    assert m.reference_average_volume == Decimal("1000")
    assert m.volume_ratio == Decimal("2.5")
    # close_location_value = (101.55 - 101.40) / (101.60 - 101.40) = 0.15/0.20 = 0.75
    assert m.close_location_value == Decimal("0.75")

    # Re-running with the SAME inputs produces the SAME measurements (pure function).
    is_candidate_2, m2 = evaluate_structure_v2(window, lookback_bars=5)
    assert (is_candidate_2, m2) == (is_candidate, m)


def test_entry_quality_refusal_rejects_weak_volume_ratio() -> None:
    _, m = evaluate_structure_v2(_breakout_window(), lookback_bars=5)
    policy = _policy(minimum_volume_ratio=Decimal("3"))  # 2.5x actual < 3x required
    assert entry_quality_refusal(m, policy=policy) is RejectionReasonV2.WEAK_BREAKOUT_VOLUME_RATIO


def test_entry_quality_refusal_rejects_weak_close_location() -> None:
    _, m = evaluate_structure_v2(_breakout_window(), lookback_bars=5)
    policy = _policy(minimum_close_location_value=Decimal("0.9"))  # 0.75 actual < 0.9 required
    assert entry_quality_refusal(m, policy=policy) is RejectionReasonV2.WEAK_CLOSE_LOCATION


def test_entry_quality_passes_a_strong_breakout() -> None:
    _, m = evaluate_structure_v2(_breakout_window(), lookback_bars=5)
    policy = _policy(minimum_volume_ratio=Decimal("2"), minimum_close_location_value=Decimal("0.6"))
    assert entry_quality_refusal(m, policy=policy) is None


def test_liquidity_refusal_absolute_floor() -> None:
    window = _breakout_window()
    _, m = evaluate_structure_v2(window, lookback_bars=5)
    policy = _policy(minimum_recent_share_volume=3000)  # bar volume 2500 < 3000
    assert (
        liquidity_refusal_v2(window, m, policy=policy)
        is RejectionReasonV2.INSUFFICIENT_LIQUIDITY_ABSOLUTE
    )


def test_liquidity_refusal_relative_multiple() -> None:
    window = _breakout_window()
    _, m = evaluate_structure_v2(window, lookback_bars=5)
    # reference_median_volume = 1000 (all reference bars are 1000); bar volume 2500.
    # A relative multiple of 3x requires >= 3000, which 2500 does not meet.
    policy = _policy(relative_liquidity_multiple=Decimal("3"))
    assert (
        liquidity_refusal_v2(window, m, policy=policy)
        is RejectionReasonV2.INSUFFICIENT_LIQUIDITY_RELATIVE
    )
    # A relative multiple of 2x requires >= 2000, which 2500 clears.
    policy_permissive = _policy(relative_liquidity_multiple=Decimal("2"))
    assert liquidity_refusal_v2(window, m, policy=policy_permissive) is None


def test_geometry_stop_is_structural_and_target_is_range_aware() -> None:
    _, m = evaluate_structure_v2(_breakout_window(), lookback_bars=5)
    policy = _policy(target_range_multiple=Decimal("3"), minimum_reward_risk_ratio=Decimal("1"))
    geometry = build_trade_plan_geometry_v2(
        entry_price=Decimal("101.55"), measurements=m, policy=policy
    )
    assert geometry is not None
    # stop = prior_swing_low. Reference lows: 99.00,99.20,99.40,99.60,99.80 -> trough at index 0
    # (99.00); swing low = min of lows from trough index onward = 99.00.
    assert geometry.stop_price == Decimal("99.00")
    assert geometry.risk_per_share == Decimal("2.55")
    # reference_average_range: bar ranges are 1.50,1.20,0.90,0.85,0.70 -> avg = 1.03
    # range_aware_target = 101.55 + 3 * 1.03 = 104.64; floor_target = 101.55 + 1*2.55=104.10
    # max(104.64, 104.10) = 104.64
    assert geometry.target_price == Decimal("104.64")


def test_geometry_never_offers_below_the_reward_risk_floor() -> None:
    """A tiny target_range_multiple must not undercut minimum_reward_risk_ratio."""
    _, m = evaluate_structure_v2(_breakout_window(), lookback_bars=5)
    policy = _policy(target_range_multiple=Decimal("0.01"), minimum_reward_risk_ratio=Decimal("2"))
    geometry = build_trade_plan_geometry_v2(
        entry_price=Decimal("101.55"), measurements=m, policy=policy
    )
    assert geometry is not None
    assert geometry.reward_risk_ratio >= Decimal("2")


def test_plan_geometry_refusal_rejects_inverted_stop() -> None:
    assert (
        plan_geometry_refusal_v2(entry_price=Decimal("100"), stop_price=Decimal("100"))
        is RejectionReasonV2.STOP_INVALID
    )
    assert (
        plan_geometry_refusal_v2(entry_price=Decimal("100"), stop_price=Decimal("101"))
        is RejectionReasonV2.STOP_INVALID
    )
    assert plan_geometry_refusal_v2(entry_price=Decimal("100"), stop_price=Decimal("99")) is None


def test_reward_risk_refusal() -> None:
    _, m = evaluate_structure_v2(_breakout_window(), lookback_bars=5)
    policy = _policy(target_range_multiple=Decimal("3"), minimum_reward_risk_ratio=Decimal("1"))
    geometry = build_trade_plan_geometry_v2(
        entry_price=Decimal("101.55"), measurements=m, policy=policy
    )
    assert geometry is not None
    assert reward_risk_refusal_v2(geometry, minimum_reward_risk_ratio=Decimal("10")) is (
        RejectionReasonV2.REWARD_RISK_TOO_LOW
    )
    assert reward_risk_refusal_v2(geometry, minimum_reward_risk_ratio=Decimal("1")) is None


def test_time_to_target_feasibility_disabled_by_default() -> None:
    _, m = evaluate_structure_v2(_breakout_window(), lookback_bars=5)
    policy = _policy(time_to_target_feasibility_enabled=False)
    geometry = build_trade_plan_geometry_v2(
        entry_price=Decimal("101.55"), measurements=m, policy=policy
    )
    assert geometry is not None
    assert (
        time_to_target_refusal(
            geometry=geometry, measurements=m, remaining_bars_to_mandatory_exit=0, policy=policy
        )
        is None
    )


def test_time_to_target_feasibility_rejects_an_unreachable_target() -> None:
    _, m = evaluate_structure_v2(_breakout_window(), lookback_bars=5)
    policy = _policy(
        time_to_target_feasibility_enabled=True,
        time_to_target_safety_factor=Decimal("1"),
        target_range_multiple=Decimal("3"),
        minimum_reward_risk_ratio=Decimal("1"),
    )
    geometry = build_trade_plan_geometry_v2(
        entry_price=Decimal("101.55"), measurements=m, policy=policy
    )
    assert geometry is not None
    # reward_per_share ~= 3.09 (104.64-101.55); average_range ~= 1.03/bar; with only 1 bar
    # remaining, achievable = 1 * 1.03 * 1 = 1.03 < 3.09 -> infeasible.
    assert (
        time_to_target_refusal(
            geometry=geometry, measurements=m, remaining_bars_to_mandatory_exit=1, policy=policy
        )
        is RejectionReasonV2.TARGET_NOT_FEASIBLE_IN_REMAINING_TIME
    )
    # With plenty of remaining bars, the same target becomes feasible.
    assert (
        time_to_target_refusal(
            geometry=geometry, measurements=m, remaining_bars_to_mandatory_exit=100, policy=policy
        )
        is None
    )


def test_time_to_target_feasibility_rejects_zero_remaining_bars_when_enabled() -> None:
    _, m = evaluate_structure_v2(_breakout_window(), lookback_bars=5)
    policy = _policy(time_to_target_feasibility_enabled=True)
    geometry = build_trade_plan_geometry_v2(
        entry_price=Decimal("101.55"), measurements=m, policy=policy
    )
    assert geometry is not None
    assert (
        time_to_target_refusal(
            geometry=geometry, measurements=m, remaining_bars_to_mandatory_exit=0, policy=policy
        )
        is RejectionReasonV2.TARGET_NOT_FEASIBLE_IN_REMAINING_TIME
    )


def test_position_size_never_leverages_and_floors_to_whole_shares() -> None:
    quantity = position_size_v2(
        entry_price=Decimal("100"),
        stop_price=Decimal("98"),
        maximum_loss=Decimal("50"),
        maximum_capital_per_trade=Decimal("10000"),
        maximum_percent_per_trade=Decimal("100"),
        deployable_capital=Decimal("10000"),
    )
    # by_risk = floor(50 / 2) = 25; by_trade_cap = floor(10000/100) = 100;
    # by_percent_cap = floor(10000*100/100 / 100) = 100 -> min = 25
    assert quantity == 25


def test_policy_rejects_invalid_fields() -> None:
    with pytest.raises(ValueError, match="policy_version"):
        OpportunityEnginePolicyV2(
            policy_version="",
            structure_lookback_bars=5,
            minimum_recent_share_volume=100,
            relative_liquidity_multiple=None,
            minimum_volume_ratio=Decimal("1.5"),
            minimum_close_location_value=Decimal("0.6"),
            target_range_multiple=Decimal("3"),
            minimum_reward_risk_ratio=Decimal("1.5"),
            time_to_target_feasibility_enabled=False,
            time_to_target_safety_factor=Decimal("1"),
            maximum_loss_per_trade=Decimal("100"),
            top_n=5,
            entry_tolerance_percent=Decimal("0.5"),
            opportunity_validity_seconds=300,
        )
    with pytest.raises(ValueError, match="minimum_close_location_value"):
        _policy(minimum_close_location_value=Decimal("1.5"))
    with pytest.raises(ValueError, match="relative_liquidity_multiple"):
        _policy(relative_liquidity_multiple=Decimal("-1"))
