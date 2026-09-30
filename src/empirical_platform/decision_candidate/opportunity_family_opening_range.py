"""MILESTONE-093 Phase 7 -- STRATEGY FAMILY C: OPENING RANGE.

A FIXED, predeclared opening-range duration (this module implements exactly two economically
reasonable variants -- 5 minutes and 15 minutes, chosen because they are the two most
commonly cited opening-range conventions and require no further tuning; NOT dozens of
durations). The opening range itself is the first `duration_minutes` one-minute bars of the
regular session.

STRUCTURALLY CANNOT TRADE BEFORE THE RANGE COMPLETES. `first_eligible_bar_index` is the bar
index at which decisions may first be made; the replay loop in
`run_opening_range_session` below starts at exactly that index, so no bar inside the opening
range is EVER passed to the decision function at all -- not filtered out after the fact, never
evaluated in the first place. A dedicated test proves no decision this family produces can
ever have `bar_index < duration_minutes`.

ENTRY: opening-range breakout with volume confirmation, using ONLY bars observed since the
range completed for its own reference statistics (never the range's own bars as a volume
baseline, and never anything after the decision bar).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from empirical_platform.decision_candidate.market_data import Bar

__all__ = [
    "FAMILY_NAME",
    "OPENING_RANGE_VARIANTS_MINUTES",
    "STRUCTURE_MODEL_ID",
    "STRUCTURE_MODEL_VERSION",
    "OpeningRangeEvaluation",
    "OpeningRangePolicy",
    "OpeningRangePlanGeometry",
    "build_opening_range_plan_geometry",
    "compute_opening_range",
    "evaluate_opening_range_breakout",
]

FAMILY_NAME = "OPENING_RANGE_BREAKOUT"
STRUCTURE_MODEL_ID = "FIXED_DURATION_OPENING_RANGE_BREAKOUT_V1"
STRUCTURE_MODEL_VERSION = "1"

#: The ONLY two variants this family tests -- Phase 7's own instruction: "Do not test dozens
#: of opening-range durations. Choose at most 2 economically reasonable variants."
OPENING_RANGE_VARIANTS_MINUTES: tuple[int, ...] = (5, 15)

_CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class OpeningRangePolicy:
    #: Which of `OPENING_RANGE_VARIANTS_MINUTES` this policy instance uses. Assumes 1-minute
    #: bars, so this is also the opening-range bar COUNT.
    duration_minutes: int
    minimum_reference_bars: int
    minimum_volume_ratio: Decimal
    minimum_liquidity_shares: int
    target_range_multiple: Decimal
    minimum_reward_risk_ratio: Decimal

    def __post_init__(self) -> None:
        if self.duration_minutes not in OPENING_RANGE_VARIANTS_MINUTES:
            raise ValueError(
                f"duration_minutes must be one of {OPENING_RANGE_VARIANTS_MINUTES}, "
                f"got {self.duration_minutes}"
            )

    @property
    def first_eligible_bar_index(self) -> int:
        """No decision may ever be made at an index strictly less than this -- the opening
        range's own bars are indices `0` through `duration_minutes - 1`."""
        return self.duration_minutes


@dataclass(frozen=True, slots=True)
class OpeningRange:
    high: Decimal
    low: Decimal


def compute_opening_range(
    bars: Sequence[Bar], *, policy: OpeningRangePolicy
) -> OpeningRange | None:
    """Reads ONLY `bars[0:duration_minutes]` -- the session's own opening bars, all
    necessarily at or before any bar this family is ever allowed to decide at."""
    opening_bars = bars[: policy.duration_minutes]
    if len(opening_bars) < policy.duration_minutes:
        return None
    return OpeningRange(
        high=max(bar.high for bar in opening_bars), low=min(bar.low for bar in opening_bars)
    )


@dataclass(frozen=True, slots=True)
class OpeningRangeEvaluation:
    is_candidate: bool
    reason: str | None
    opening_range_high: Decimal
    opening_range_low: Decimal
    current_close: Decimal
    current_volume: int
    reference_average_volume: Decimal


def evaluate_opening_range_breakout(
    bars: Sequence[Bar],
    index: int,
    opening_range: OpeningRange,
    *,
    policy: OpeningRangePolicy,
) -> OpeningRangeEvaluation:
    """`index` must be `>= policy.first_eligible_bar_index` -- the caller (`run_opening_range_
    session`) enforces this structurally by never invoking this function for an earlier
    index. Reads only `bars[duration_minutes:index+1]` for its own reference/current
    evidence, plus the already-computed `opening_range` (itself only from `bars[0:
    duration_minutes]`) -- never a bar after `index`."""
    if index < policy.first_eligible_bar_index:
        raise ValueError(
            f"bar {index} is inside the opening range (first eligible index is "
            f"{policy.first_eligible_bar_index}) -- this must never be called for it"
        )
    current = bars[index]
    reference_bars = bars[policy.duration_minutes : index]
    if len(reference_bars) < policy.minimum_reference_bars:
        return OpeningRangeEvaluation(
            is_candidate=False,
            reason="INSUFFICIENT_POST_RANGE_REFERENCE",
            opening_range_high=opening_range.high,
            opening_range_low=opening_range.low,
            current_close=current.close,
            current_volume=current.volume,
            reference_average_volume=Decimal("0"),
        )
    ref_volumes = [Decimal(bar.volume) for bar in reference_bars]
    reference_average_volume = sum(ref_volumes, start=Decimal(0)) / Decimal(len(ref_volumes))
    volume_ratio = (
        Decimal(current.volume) / reference_average_volume
        if reference_average_volume > 0
        else Decimal(0)
    )

    breakout = current.close > opening_range.high
    liquid_enough = current.volume >= policy.minimum_liquidity_shares
    volume_confirms = volume_ratio >= policy.minimum_volume_ratio

    is_candidate = breakout and liquid_enough and volume_confirms
    reason: str | None = None
    if not is_candidate:
        if not liquid_enough:
            reason = "INSUFFICIENT_LIQUIDITY"
        elif not breakout:
            reason = "NO_OPENING_RANGE_BREAKOUT"
        elif not volume_confirms:
            reason = "WEAK_BREAKOUT_VOLUME"

    return OpeningRangeEvaluation(
        is_candidate=is_candidate,
        reason=reason,
        opening_range_high=opening_range.high,
        opening_range_low=opening_range.low,
        current_close=current.close,
        current_volume=current.volume,
        reference_average_volume=reference_average_volume,
    )


@dataclass(frozen=True, slots=True)
class OpeningRangePlanGeometry:
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    risk_per_share: Decimal
    reward_per_share: Decimal
    reward_risk_ratio: Decimal


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_DOWN)


def build_opening_range_plan_geometry(
    evaluation: OpeningRangeEvaluation, *, policy: OpeningRangePolicy
) -> OpeningRangePlanGeometry | None:
    """Stop = the opening range's own low (structural: a breakout that gives back the whole
    range disproves the thesis). Target = a multiple of the opening range's own width,
    floored at the policy's R:R minimum."""
    entry = _quantize(evaluation.current_close)
    stop = _quantize(evaluation.opening_range_low)
    if stop >= entry:
        return None
    risk_per_share = _quantize(entry - stop)
    if risk_per_share <= 0:
        return None
    range_width = evaluation.opening_range_high - evaluation.opening_range_low
    range_aware_target = entry + policy.target_range_multiple * range_width
    floor_target = entry + policy.minimum_reward_risk_ratio * risk_per_share
    target = _quantize(max(range_aware_target, floor_target))
    reward_per_share = _quantize(target - entry)
    reward_risk_ratio = (reward_per_share / risk_per_share).quantize(Decimal("0.01"))
    return OpeningRangePlanGeometry(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        reward_risk_ratio=reward_risk_ratio,
    )
