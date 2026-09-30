"""MILESTONE-093 Phase 8 -- Family D (conditional mean reversion): hand-built determinism
tests, including the "never buy falling prices merely because they fell" regime/stabilization
gates."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.opportunity_family_mean_reversion import (
    MeanReversionPolicy,
    build_mean_reversion_plan_geometry,
    compute_vwap_series,
    evaluate_mean_reversion,
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


def _policy(**overrides: object) -> MeanReversionPolicy:
    defaults: dict[str, object] = dict(
        regime_lookback_bars=4,
        maximum_adverse_trend_percent=Decimal("5"),
        minimum_deviation_percent=Decimal("0.1"),
        minimum_liquidity_shares=500,
        minimum_reward_risk_ratio=Decimal("1.2"),
    )
    defaults.update(overrides)
    return MeanReversionPolicy(**defaults)  # type: ignore[arg-type]


def _stabilizing_deviation_bars() -> list[Bar]:
    return [
        _bar(minute=0, o="100.00", h="100.30", low="99.80", c="100.10"),
        _bar(minute=1, o="100.10", h="100.30", low="99.90", c="100.05"),
        _bar(minute=2, o="100.05", h="100.20", low="99.70", c="99.90"),
        _bar(minute=3, o="99.90", h="100.00", low="99.50", c="99.70"),
        # evaluation bar: dips below VWAP, closes above its own open, low holds the prior low
        _bar(minute=4, o="99.55", h="99.80", low="99.50", c="99.60", v=2000),
    ]


def test_regime_deviation_and_stabilization_together_is_accepted() -> None:
    bars = _stabilizing_deviation_bars()
    series = compute_vwap_series(bars)
    evaluation = evaluate_mean_reversion(bars, len(bars) - 1, series, policy=_policy())
    assert evaluation.is_candidate
    assert evaluation.reason is None
    geometry = build_mean_reversion_plan_geometry(evaluation, policy=_policy())
    assert geometry is not None
    assert geometry.stop_price == Decimal("99.50")  # the reversal bar's own low
    assert geometry.target_price == evaluation.current_vwap.quantize(
        Decimal("0.01"), rounding=ROUND_DOWN
    )


def test_a_new_low_with_no_stabilization_is_rejected_even_though_it_deviates_from_vwap() -> None:
    """The core "never buy falling prices merely because they fell" guard: a bar that keeps
    making new lows (no reversal evidence) must be rejected even if its deviation from VWAP
    alone would otherwise qualify."""
    bars = _stabilizing_deviation_bars()
    bars[4] = _bar(minute=4, o="99.60", h="99.70", low="99.20", c="99.30", v=2000)
    series = compute_vwap_series(bars)
    evaluation = evaluate_mean_reversion(bars, len(bars) - 1, series, policy=_policy())
    assert not evaluation.is_candidate
    assert evaluation.reason == "NO_STABILIZATION_EVIDENCE"


def test_a_strong_adverse_trend_regime_is_rejected() -> None:
    bars = [
        _bar(minute=0, o="105.00", h="105.20", low="104.80", c="105.00"),
        _bar(minute=1, o="105.00", h="105.00", low="102.00", c="102.50"),
        _bar(minute=2, o="102.50", h="102.60", low="100.00", c="100.50"),
        _bar(minute=3, o="100.50", h="100.60", low="98.00", c="98.50"),
        _bar(minute=4, o="98.40", h="98.80", low="98.30", c="98.70", v=2000),
    ]
    series = compute_vwap_series(bars)
    evaluation = evaluate_mean_reversion(
        bars, len(bars) - 1, series, policy=_policy(maximum_adverse_trend_percent=Decimal("3"))
    )
    assert not evaluation.is_candidate
    assert evaluation.reason == "ADVERSE_TREND_REGIME"


def test_insufficient_deviation_from_vwap_is_rejected() -> None:
    bars = _stabilizing_deviation_bars()
    # Close right at (barely below) the VWAP -- not enough deviation to qualify.
    bars[4] = _bar(minute=4, o="99.80", h="99.90", low="99.70", c="99.85", v=2000)
    series = compute_vwap_series(bars)
    evaluation = evaluate_mean_reversion(
        bars, len(bars) - 1, series, policy=_policy(minimum_deviation_percent=Decimal("5"))
    )
    assert not evaluation.is_candidate
    assert evaluation.reason == "INSUFFICIENT_VWAP_DEVIATION"
