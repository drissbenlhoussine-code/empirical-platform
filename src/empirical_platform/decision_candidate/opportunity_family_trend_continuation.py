"""MILESTONE-093 Phase 5 -- STRATEGY FAMILY A: TREND CONTINUATION.

Genuinely different from V1/V2's simple "close above N-bar range high" breakout: this family
requires an established intraday uptrend FIRST, then a pullback that preserves that trend's
own structure, then a resumption trigger -- never a bare range breakout with no prior trend
context.

Deterministic, at-or-before-T only (every measurement comes from `window.reference_bars`,
strictly before the decision bar, or `window.evaluation_bar`, the decision bar itself).

THE THREE-PHASE STRUCTURE:
1. ESTABLISH -- the first two-thirds of the reference window. An uptrend is confirmed if the
   second half of this phase made a higher high than its first half (a simple, deterministic,
   explainable trend proxy -- not a regression slope or any black-box indicator).
2. PULLBACK -- the last one-third of the reference window. Its own low must not violate the
   establish phase's own low (the trend's structure is preserved, not broken).
3. RESUMPTION -- the evaluation bar's close must reclaim ABOVE the pullback phase's own high
   (the pullback's local high, not the establish phase's high) with volume participation --
   this is the "resumption/continuation" trigger, deliberately distinct from "price crossed a
   prior high" since the level being reclaimed is the PULLBACK's own high, not the trend's
   overall high.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from empirical_platform.decision_candidate.market_data import ObservationWindow

__all__ = [
    "FAMILY_NAME",
    "STRUCTURE_MODEL_ID",
    "STRUCTURE_MODEL_VERSION",
    "TrendContinuationEvaluation",
    "TrendContinuationPolicy",
    "TrendPlanGeometry",
    "build_trend_plan_geometry",
    "evaluate_trend_continuation",
]

FAMILY_NAME = "TREND_CONTINUATION"
STRUCTURE_MODEL_ID = "ESTABLISH_PULLBACK_RESUMPTION_HIGHER_LOW_V1"
STRUCTURE_MODEL_VERSION = "1"

_HUNDRED = Decimal("100")
_CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class TrendContinuationPolicy:
    #: Total reference bars used for the establish+pullback phases together.
    lookback_bars: int
    #: The reference window's LAST this-many bars form the pullback phase; the rest form the
    #: establish phase. Must be strictly less than `lookback_bars`.
    pullback_bars: int
    #: The resumption bar's volume must reach at least this multiple of the establish phase's
    #: own average volume.
    minimum_volume_ratio: Decimal
    minimum_liquidity_shares: int
    target_range_multiple: Decimal
    minimum_reward_risk_ratio: Decimal

    def __post_init__(self) -> None:
        if self.pullback_bars < 1 or self.pullback_bars >= self.lookback_bars:
            raise ValueError("pullback_bars must be >= 1 and < lookback_bars")
        if self.lookback_bars - self.pullback_bars < 2:
            raise ValueError("the establish phase needs at least 2 bars")


@dataclass(frozen=True, slots=True)
class TrendContinuationEvaluation:
    is_candidate: bool
    reason: str | None
    establish_first_half_high: Decimal
    establish_second_half_high: Decimal
    establish_low: Decimal
    pullback_low: Decimal
    pullback_high: Decimal
    establish_average_volume: Decimal
    reference_average_range: Decimal
    current_close: Decimal
    current_volume: int
    volume_ratio: Decimal


def evaluate_trend_continuation(
    window: ObservationWindow, *, policy: TrendContinuationPolicy
) -> TrendContinuationEvaluation:
    """Reads ONLY `window.reference_bars` (strictly before T) and `window.evaluation_bar`
    (the decision bar itself, T) -- never anything after T."""
    reference = window.reference_bars[-policy.lookback_bars :]
    if len(reference) < policy.lookback_bars:
        return TrendContinuationEvaluation(
            is_candidate=False,
            reason="INSUFFICIENT_REFERENCE_BARS",
            establish_first_half_high=Decimal("0"),
            establish_second_half_high=Decimal("0"),
            establish_low=Decimal("0"),
            pullback_low=Decimal("0"),
            pullback_high=Decimal("0"),
            establish_average_volume=Decimal("0"),
            reference_average_range=Decimal("0"),
            current_close=window.evaluation_bar.close,
            current_volume=window.evaluation_bar.volume,
            volume_ratio=Decimal("0"),
        )

    split = len(reference) - policy.pullback_bars
    establish = reference[:split]
    pullback = reference[split:]
    establish_mid = len(establish) // 2
    establish_first_half = establish[:establish_mid] or establish[:1]
    establish_second_half = establish[establish_mid:]

    establish_first_half_high = max(bar.high for bar in establish_first_half)
    establish_second_half_high = max(bar.high for bar in establish_second_half)
    establish_low = min(bar.low for bar in establish)
    pullback_low = min(bar.low for bar in pullback)
    pullback_high = max(bar.high for bar in pullback)
    establish_volumes = [Decimal(bar.volume) for bar in establish]
    establish_average_volume = sum(establish_volumes, start=Decimal(0)) / Decimal(
        len(establish_volumes)
    )
    ranges = [bar.high - bar.low for bar in reference]
    reference_average_range = sum(ranges, start=Decimal(0)) / Decimal(len(ranges))

    current = window.evaluation_bar
    volume_ratio = (
        Decimal(current.volume) / establish_average_volume
        if establish_average_volume > 0
        else Decimal(0)
    )

    trend_confirmed = establish_second_half_high > establish_first_half_high
    pullback_preserves_structure = pullback_low >= establish_low
    resumption = current.close > pullback_high
    liquid_enough = current.volume >= policy.minimum_liquidity_shares
    volume_confirms = volume_ratio >= policy.minimum_volume_ratio

    is_candidate = (
        trend_confirmed
        and pullback_preserves_structure
        and resumption
        and liquid_enough
        and volume_confirms
    )
    reason: str | None = None
    if not is_candidate:
        if not liquid_enough:
            reason = "INSUFFICIENT_LIQUIDITY"
        elif not trend_confirmed:
            reason = "NO_ESTABLISHED_TREND"
        elif not pullback_preserves_structure:
            reason = "PULLBACK_BROKE_STRUCTURE"
        elif not resumption:
            reason = "NO_RESUMPTION_TRIGGER"
        elif not volume_confirms:
            reason = "WEAK_RESUMPTION_VOLUME"

    return TrendContinuationEvaluation(
        is_candidate=is_candidate,
        reason=reason,
        establish_first_half_high=establish_first_half_high,
        establish_second_half_high=establish_second_half_high,
        establish_low=establish_low,
        pullback_low=pullback_low,
        pullback_high=pullback_high,
        establish_average_volume=establish_average_volume,
        reference_average_range=reference_average_range,
        current_close=current.close,
        current_volume=current.volume,
        volume_ratio=volume_ratio,
    )


@dataclass(frozen=True, slots=True)
class TrendPlanGeometry:
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    risk_per_share: Decimal
    reward_per_share: Decimal
    reward_risk_ratio: Decimal


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_DOWN)


def build_trend_plan_geometry(
    evaluation: TrendContinuationEvaluation, *, policy: TrendContinuationPolicy
) -> TrendPlanGeometry | None:
    """Stop = the pullback's own low (structural, the level whose violation would disprove
    the continuation thesis). Target = range-aware, floored at the policy's own R:R minimum
    -- never below that many multiples of risk."""
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
    return TrendPlanGeometry(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        reward_risk_ratio=reward_risk_ratio,
    )
