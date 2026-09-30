"""MILESTONE-093 Phase 8 -- STRATEGY FAMILY D: CONDITIONAL MEAN REVERSION.

Long-only, and NOT "buy because it fell" -- every entry requires an explicit REGIME
precondition (no strong adverse trend), a DEVIATION from the session's own VWAP, AND
stabilization evidence (a reversal bar), all three together, never deviation alone.

Reuses `compute_vwap_series` from the VWAP-pullback family module unchanged (the same
look-ahead-safe cumulative VWAP, not reimplemented a third time) as the reversion TARGET
reference -- the target is `current VWAP`, not an arbitrary fixed upside multiple.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from empirical_platform.decision_candidate.market_data import Bar
from empirical_platform.decision_candidate.opportunity_family_vwap_pullback import (
    compute_vwap_series,
)

__all__ = [
    "FAMILY_NAME",
    "STRUCTURE_MODEL_ID",
    "STRUCTURE_MODEL_VERSION",
    "MeanReversionEvaluation",
    "MeanReversionPlanGeometry",
    "MeanReversionPolicy",
    "build_mean_reversion_plan_geometry",
    "compute_vwap_series",
    "evaluate_mean_reversion",
]

FAMILY_NAME = "CONDITIONAL_MEAN_REVERSION"
STRUCTURE_MODEL_ID = "REGIME_GATED_VWAP_DEVIATION_STABILIZATION_V1"
STRUCTURE_MODEL_VERSION = "1"

_HUNDRED = Decimal("100")
_CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class MeanReversionPolicy:
    regime_lookback_bars: int
    #: The regime is rejected if the FIRST half of the regime window's average close exceeds
    #: the SECOND half's by more than this percent -- a strong adverse (downward) trend.
    maximum_adverse_trend_percent: Decimal
    #: Current close must be at least this percent BELOW the current session VWAP.
    minimum_deviation_percent: Decimal
    minimum_liquidity_shares: int
    minimum_reward_risk_ratio: Decimal

    def __post_init__(self) -> None:
        if self.regime_lookback_bars < 4:
            raise ValueError("regime_lookback_bars must be >= 4 to split into two halves")


@dataclass(frozen=True, slots=True)
class MeanReversionEvaluation:
    is_candidate: bool
    reason: str | None
    current_vwap: Decimal
    current_close: Decimal
    current_low: Decimal
    previous_low: Decimal | None
    deviation_percent: Decimal
    adverse_trend_percent: Decimal


def evaluate_mean_reversion(
    bars: Sequence[Bar], index: int, vwap_series: Sequence[Decimal], *, policy: MeanReversionPolicy
) -> MeanReversionEvaluation:
    """Reads ONLY `bars[:index+1]` and `vwap_series[:index+1]` -- never anything after
    `index`."""
    current = bars[index]
    current_vwap = vwap_series[index]

    if index < policy.regime_lookback_bars:
        return MeanReversionEvaluation(
            is_candidate=False,
            reason="INSUFFICIENT_REFERENCE_BARS",
            current_vwap=current_vwap,
            current_close=current.close,
            current_low=current.low,
            previous_low=None,
            deviation_percent=Decimal("0"),
            adverse_trend_percent=Decimal("0"),
        )

    regime_window = bars[index - policy.regime_lookback_bars : index]
    mid = len(regime_window) // 2
    first_half_avg = sum((bar.close for bar in regime_window[:mid]), Decimal("0")) / Decimal(mid)
    second_half_avg = sum((bar.close for bar in regime_window[mid:]), Decimal("0")) / Decimal(
        len(regime_window) - mid
    )
    adverse_trend_percent = (
        ((first_half_avg - second_half_avg) / first_half_avg) * _HUNDRED
        if first_half_avg > 0
        else Decimal("0")
    )
    regime_ok = adverse_trend_percent <= policy.maximum_adverse_trend_percent

    deviation_percent = (
        ((current_vwap - current.close) / current_vwap) * _HUNDRED
        if current_vwap > 0
        else Decimal("0")
    )
    deviation_ok = deviation_percent >= policy.minimum_deviation_percent

    previous = bars[index - 1]
    stabilizing = current.close > current.open and current.low >= previous.low
    liquid_enough = current.volume >= policy.minimum_liquidity_shares

    is_candidate = regime_ok and deviation_ok and stabilizing and liquid_enough
    reason: str | None = None
    if not is_candidate:
        if not liquid_enough:
            reason = "INSUFFICIENT_LIQUIDITY"
        elif not regime_ok:
            reason = "ADVERSE_TREND_REGIME"
        elif not deviation_ok:
            reason = "INSUFFICIENT_VWAP_DEVIATION"
        elif not stabilizing:
            reason = "NO_STABILIZATION_EVIDENCE"

    return MeanReversionEvaluation(
        is_candidate=is_candidate,
        reason=reason,
        current_vwap=current_vwap,
        current_close=current.close,
        current_low=current.low,
        previous_low=previous.low,
        deviation_percent=deviation_percent,
        adverse_trend_percent=adverse_trend_percent,
    )


@dataclass(frozen=True, slots=True)
class MeanReversionPlanGeometry:
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    risk_per_share: Decimal
    reward_per_share: Decimal
    reward_risk_ratio: Decimal


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_DOWN)


def build_mean_reversion_plan_geometry(
    evaluation: MeanReversionEvaluation, *, policy: MeanReversionPolicy
) -> MeanReversionPlanGeometry | None:
    """Stop = the current bar's own low (tight, structural -- a reversal bar that immediately
    makes a new low disproves the stabilization thesis). Target = the session's own VWAP --
    never an arbitrary fixed upside multiple, per Phase 8's own instruction."""
    entry = _quantize(evaluation.current_close)
    stop = _quantize(evaluation.current_low)
    if stop >= entry:
        return None
    risk_per_share = _quantize(entry - stop)
    if risk_per_share <= 0:
        return None
    vwap_target = _quantize(evaluation.current_vwap)
    floor_target = entry + policy.minimum_reward_risk_ratio * risk_per_share
    target = max(vwap_target, floor_target)
    reward_per_share = _quantize(target - entry)
    if reward_per_share <= 0:
        return None
    reward_risk_ratio = (reward_per_share / risk_per_share).quantize(Decimal("0.01"))
    return MeanReversionPlanGeometry(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        reward_risk_ratio=reward_risk_ratio,
    )
