"""MILESTONE-093 Phase 6 -- STRATEGY FAMILY B: PULLBACK / VWAP RECLAIM.

A look-ahead-safe INTRADAY volume-weighted average price (VWAP), computed cumulatively from
the session's own open through the bar under evaluation -- NEVER the session's full-day
VWAP, which would leak future information. `compute_vwap_series` is the one function that
does this computation; a dedicated test proves `vwap_series[i]` only ever depends on
`bars[:i+1]`.

SETUP: price was constructive (above VWAP) before a pullback, the pullback touches VWAP (or
dips below it) without the broader structure breaking, then price RECLAIMS above VWAP with
confirmation (a bullish close, adequate volume). Stop derives from the pullback's own
structure; target derives from a realistic intraday excursion (range-aware, same convention
as every other family in this milestone).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from empirical_platform.decision_candidate.market_data import Bar

__all__ = [
    "FAMILY_NAME",
    "STRUCTURE_MODEL_ID",
    "STRUCTURE_MODEL_VERSION",
    "VwapPlanGeometry",
    "VwapPullbackEvaluation",
    "VwapPullbackPolicy",
    "build_vwap_plan_geometry",
    "compute_vwap_series",
    "evaluate_vwap_pullback",
]

FAMILY_NAME = "VWAP_PULLBACK_RECLAIM"
STRUCTURE_MODEL_ID = "SESSION_VWAP_PULLBACK_RECLAIM_V1"
STRUCTURE_MODEL_VERSION = "1"

_THREE = Decimal("3")
_CENT = Decimal("0.01")


def compute_vwap_series(bars: Sequence[Bar]) -> tuple[Decimal, ...]:
    """`result[i]` is the session VWAP computed from `bars[0]` through `bars[i]` inclusive
    ONLY -- never any bar after `i`. This is the entire look-ahead defense for this family's
    reference level; see `tests/unit/test_m093_family_vwap_pullback.py`'s dedicated proof."""
    series: list[Decimal] = []
    cumulative_pv = Decimal("0")
    cumulative_v = Decimal("0")
    for bar in bars:
        typical_price = (bar.high + bar.low + bar.close) / _THREE
        cumulative_pv += typical_price * Decimal(bar.volume)
        cumulative_v += Decimal(bar.volume)
        series.append(cumulative_pv / cumulative_v if cumulative_v > 0 else typical_price)
    return tuple(series)


@dataclass(frozen=True, slots=True)
class VwapPullbackPolicy:
    #: How many bars BEFORE the pullback window must show price constructive (close above
    #: that bar's own VWAP) -- proves an uptrend context existed, not just a random dip.
    constructive_lookback_bars: int
    #: The bars immediately before the decision bar that form the pullback window.
    pullback_bars: int
    minimum_volume_ratio: Decimal
    minimum_liquidity_shares: int
    target_range_multiple: Decimal
    minimum_reward_risk_ratio: Decimal

    def __post_init__(self) -> None:
        if self.constructive_lookback_bars < 1 or self.pullback_bars < 1:
            raise ValueError("constructive_lookback_bars and pullback_bars must be >= 1")


@dataclass(frozen=True, slots=True)
class VwapPullbackEvaluation:
    is_candidate: bool
    reason: str | None
    current_vwap: Decimal
    current_close: Decimal
    current_open: Decimal
    current_volume: int
    pullback_low: Decimal
    reference_average_volume: Decimal
    reference_average_range: Decimal
    volume_ratio: Decimal


def evaluate_vwap_pullback(
    bars: Sequence[Bar], index: int, vwap_series: Sequence[Decimal], *, policy: VwapPullbackPolicy
) -> VwapPullbackEvaluation:
    """Reads ONLY `bars[:index+1]` and `vwap_series[:index+1]` (itself already computed from
    `bars[:index+1]` only) -- never anything after `index`."""
    required_bars = policy.constructive_lookback_bars + policy.pullback_bars
    current = bars[index]
    current_vwap = vwap_series[index]
    if index < required_bars:
        return VwapPullbackEvaluation(
            is_candidate=False,
            reason="INSUFFICIENT_REFERENCE_BARS",
            current_vwap=current_vwap,
            current_close=current.close,
            current_open=current.open,
            current_volume=current.volume,
            pullback_low=current.low,
            reference_average_volume=Decimal("0"),
            reference_average_range=Decimal("0"),
            volume_ratio=Decimal("0"),
        )

    constructive_window = bars[index - required_bars : index - policy.pullback_bars]
    constructive_vwaps = vwap_series[index - required_bars : index - policy.pullback_bars]
    pullback_window = bars[index - policy.pullback_bars : index]

    was_constructive = all(
        bar.close > vwap for bar, vwap in zip(constructive_window, constructive_vwaps, strict=True)
    )
    pullback_low = min(bar.low for bar in pullback_window)
    touched_vwap = any(bar.low <= current_vwap for bar in pullback_window)

    reference_bars = tuple(constructive_window) + tuple(pullback_window)
    ref_volumes = [Decimal(bar.volume) for bar in reference_bars]
    reference_average_volume = sum(ref_volumes, start=Decimal(0)) / Decimal(len(ref_volumes))
    ref_ranges = [bar.high - bar.low for bar in reference_bars]
    reference_average_range = sum(ref_ranges, start=Decimal(0)) / Decimal(len(ref_ranges))
    volume_ratio = (
        Decimal(current.volume) / reference_average_volume
        if reference_average_volume > 0
        else Decimal(0)
    )

    reclaim = current.close > current_vwap and current.close > current.open
    liquid_enough = current.volume >= policy.minimum_liquidity_shares
    volume_confirms = volume_ratio >= policy.minimum_volume_ratio

    is_candidate = (
        was_constructive and touched_vwap and reclaim and liquid_enough and volume_confirms
    )
    reason: str | None = None
    if not is_candidate:
        if not liquid_enough:
            reason = "INSUFFICIENT_LIQUIDITY"
        elif not was_constructive:
            reason = "NO_CONSTRUCTIVE_CONTEXT"
        elif not touched_vwap:
            reason = "NO_VWAP_PULLBACK"
        elif not reclaim:
            reason = "NO_VWAP_RECLAIM"
        elif not volume_confirms:
            reason = "WEAK_RECLAIM_VOLUME"

    return VwapPullbackEvaluation(
        is_candidate=is_candidate,
        reason=reason,
        current_vwap=current_vwap,
        current_close=current.close,
        current_open=current.open,
        current_volume=current.volume,
        pullback_low=pullback_low,
        reference_average_volume=reference_average_volume,
        reference_average_range=reference_average_range,
        volume_ratio=volume_ratio,
    )


@dataclass(frozen=True, slots=True)
class VwapPlanGeometry:
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    risk_per_share: Decimal
    reward_per_share: Decimal
    reward_risk_ratio: Decimal


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_DOWN)


def build_vwap_plan_geometry(
    evaluation: VwapPullbackEvaluation, *, policy: VwapPullbackPolicy
) -> VwapPlanGeometry | None:
    entry = _quantize(evaluation.current_close)
    stop = _quantize(evaluation.pullback_low)
    if stop >= entry:
        return None
    risk_per_share = _quantize(entry - stop)
    if risk_per_share <= 0:
        return None
    range_aware_target = entry + policy.target_range_multiple * evaluation.reference_average_range
    floor_target = entry + policy.minimum_reward_risk_ratio * risk_per_share
    target = _quantize(max(range_aware_target, floor_target))
    reward_per_share = _quantize(target - entry)
    reward_risk_ratio = (reward_per_share / risk_per_share).quantize(Decimal("0.01"))
    return VwapPlanGeometry(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        reward_risk_ratio=reward_risk_ratio,
    )
