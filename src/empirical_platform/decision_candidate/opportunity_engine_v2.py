"""MILESTONE-092 -- the V2 research policy: deterministic, explainable rework of M090 V1's
signal, liquidity, and geometry, motivated by specific M091/Phase-6 evidence.

V1 IS NEVER TOUCHED. Nothing in this module imports, edits, or re-exports anything from
`opportunity_engine.py`'s frozen constants (`OPPORTUNITY_ENGINE_POLICY_VERSION`,
`STRUCTURE_MODEL_ID`, `QUALITY_MODEL_ID`, or any `OpportunityEnginePolicy` instance V1 uses).
V2 reuses only genuinely shared, non-V1-specific building blocks: `ObservationWindow`/`Bar`
(M057's own look-ahead defense, not V1's), `TradePlanGeometry`'s SHAPE (a new V2 instance is
built here, never V1's `build_trade_plan_geometry`), and `RejectionReason`'s REUSABLE members
(gates identical in spirit to V1's, e.g. `STOP_INVALID`, get the SAME reason code; genuinely
new gates get NEW reason codes in `RejectionReasonV2` below).

WHY THESE THREE FEATURES, PER PHASE 7-10 EVIDENCE:

1. ENTRY QUALITY (Phase 7) -- `close_location_value` (Phase 6/H2: a stronger breakout,
   closing near its own bar's high, should show a materially better MFE profile than a
   breakout that merely clears the range high by a hair) and `volume_ratio` (a STRONGER
   threshold than V1's implicit ">1.0"). Both are deterministic, computed only from
   `window.reference_bars`/`window.evaluation_bar` (strictly at-or-before T), and documented
   below with their own rationale.

2. NORMALIZED LIQUIDITY (Phase 9, H3) -- V1's absolute `minimum_recent_share_volume` floor
   structurally favors whichever symbol trades the most shares per minute in absolute terms
   (NVDA), not whichever symbol is liquid RELATIVE TO ITSELF. `relative_volume_ratio`
   (current bar volume / that SAME symbol's own rolling median volume over the reference
   window) replaces the single absolute floor with a floor PLUS a relative multiple, so a
   symbol with naturally lower absolute volume is not structurally excluded just for being
   smaller, while a genuinely quiet bar for ANY symbol (including NVDA) is still rejected.

3. TIME-AWARE TARGET + FEASIBILITY GATE (Phase 8/10, H1/H5) -- Phase 6's own MFE finding
   (median MFE well below V1's fixed 2.0R) motivates a target that scales with the symbol's
   OWN recently observed range rather than an arbitrary fixed multiple, and an explicit
   feasibility check: given the remaining minutes to mandatory liquidation and the symbol's
   own recent per-bar range, is the required price move even structurally plausible? This
   never claims a probability -- it is a bounded, deterministic, documented reject/accept
   rule, exactly Phase 8's own instruction.

NO ML, NO BLACK BOX. Every function here is pure, deterministic, and takes only evidence
computed from bars at or before the decision bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.market_data import ObservationWindow

__all__ = [
    "ENTRY_QUALITY_MODEL_ID",
    "ENTRY_QUALITY_MODEL_VERSION",
    "GEOMETRY_MODEL_ID",
    "GEOMETRY_MODEL_VERSION",
    "LIQUIDITY_MODEL_ID",
    "LIQUIDITY_MODEL_VERSION",
    "STRUCTURE_MODEL_ID",
    "STRUCTURE_MODEL_VERSION",
    "OpportunityEnginePolicyV2",
    "RejectionReasonV2",
    "StructureMeasurementsV2",
    "TradePlanGeometryV2",
    "bar_evidence_refusal_v2",
    "build_trade_plan_geometry_v2",
    "entry_quality_refusal",
    "evaluate_structure_v2",
    "liquidity_refusal_v2",
    "plan_geometry_refusal_v2",
    "position_size_v2",
    "reward_risk_refusal_v2",
    "time_to_target_refusal",
]

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")

#: Versioned model identities, mirroring V1's OWN `STRUCTURE_MODEL_ID`/`QUALITY_MODEL_ID`
#: pattern exactly -- each a pure function over a closed evidence set, never silently
#: changed without a new version string. Named distinctly from V1's (never reused).
STRUCTURE_MODEL_ID = "BOUNDED_RANGE_BREAKOUT_HIGHER_LOW_VOLUME_V2"
STRUCTURE_MODEL_VERSION = "1"
ENTRY_QUALITY_MODEL_ID = "CLOSE_LOCATION_AND_VOLUME_RATIO_CONFIRMATION_V2"
ENTRY_QUALITY_MODEL_VERSION = "1"
LIQUIDITY_MODEL_ID = "ABSOLUTE_FLOOR_PLUS_RELATIVE_VOLUME_RATIO_V2"
LIQUIDITY_MODEL_VERSION = "1"
GEOMETRY_MODEL_ID = "STRUCTURAL_STOP_RANGE_AWARE_TARGET_V2"
GEOMETRY_MODEL_VERSION = "1"


class RejectionReasonV2(StrEnum):
    """Reasons reused from V1 (same meaning, same code) plus genuinely new V2 gates."""

    # Reused (same concept as V1's RejectionReason members of the same name).
    STALE_OR_MISSING_BARS = "STALE_OR_MISSING_BARS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NO_BREAKOUT_STRUCTURE = "NO_BREAKOUT_STRUCTURE"
    STOP_INVALID = "STOP_INVALID"
    REWARD_RISK_TOO_LOW = "REWARD_RISK_TOO_LOW"
    QUANTITY_LESS_THAN_ONE = "QUANTITY_LESS_THAN_ONE"
    # New to V2.
    INSUFFICIENT_LIQUIDITY_ABSOLUTE = "INSUFFICIENT_LIQUIDITY_ABSOLUTE"
    INSUFFICIENT_LIQUIDITY_RELATIVE = "INSUFFICIENT_LIQUIDITY_RELATIVE"
    WEAK_BREAKOUT_VOLUME_RATIO = "WEAK_BREAKOUT_VOLUME_RATIO"
    WEAK_CLOSE_LOCATION = "WEAK_CLOSE_LOCATION"
    TARGET_NOT_FEASIBLE_IN_REMAINING_TIME = "TARGET_NOT_FEASIBLE_IN_REMAINING_TIME"


@dataclass(frozen=True, slots=True)
class OpportunityEnginePolicyV2:
    """Every V2 threshold, in one versioned, auditable object -- mirrors V1's
    `OpportunityEnginePolicy` shape exactly, extended with the new entry-quality,
    normalized-liquidity, and time-aware-geometry fields Phase 7-10 introduce. A permissive
    default (documented per field) makes a feature a structural no-op for a candidate that
    does not use it, rather than requiring three separate dataclass types for three
    candidates that mostly share the same shape.
    """

    policy_version: str
    structure_lookback_bars: int
    #: Phase 9: the absolute floor, kept LOW relative to V1's 20,000 -- a basic sanity floor
    #: against near-zero-volume bars, never the primary liquidity gate in V2.
    minimum_recent_share_volume: int
    #: Phase 9: current bar volume must also reach at least this multiple of the SAME
    #: symbol's own rolling median volume over the reference window. `None` disables the
    #: relative check (V2-A does not use it).
    relative_liquidity_multiple: Decimal | None
    #: Phase 7: current bar volume must reach at least this multiple of the reference
    #: average volume -- STRONGER than V1's implicit ">1.0".
    minimum_volume_ratio: Decimal
    #: Phase 7: the breakout bar's own close must sit in at least this fraction of its own
    #: [low, high] range (a close near the bar's high is a stronger, more decisive breakout
    #: than one that merely ticks above the range high before fading).
    minimum_close_location_value: Decimal
    #: Phase 10: the target is `entry + target_range_multiple * (recent average bar range)`,
    #: floored at `minimum_reward_risk_ratio` (never below that many multiples of risk) --
    #: range-aware rather than an arbitrary fixed R multiple.
    target_range_multiple: Decimal
    minimum_reward_risk_ratio: Decimal
    #: Phase 8: if enabled, reject a plan whose required move (target - entry) exceeds the
    #: symbol's own recent average bar range times the number of bars remaining to
    #: mandatory liquidation times this safety factor -- a bounded feasibility check, never
    #: a probability claim. `False` disables the gate (V2-A/V2-B do not use it).
    time_to_target_feasibility_enabled: bool
    time_to_target_safety_factor: Decimal
    maximum_loss_per_trade: Decimal
    top_n: int
    entry_tolerance_percent: Decimal
    opportunity_validity_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")
        for field_name in ("structure_lookback_bars", "minimum_recent_share_volume", "top_n"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field_name} must be a positive int")
        for field_name in (
            "minimum_volume_ratio",
            "minimum_close_location_value",
            "target_range_multiple",
            "minimum_reward_risk_ratio",
            "maximum_loss_per_trade",
            "time_to_target_safety_factor",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ValueError(f"{field_name} must be a finite, positive Decimal")
        if not (Decimal("0") < self.minimum_close_location_value <= Decimal("1")):
            raise ValueError("minimum_close_location_value must be a Decimal in (0, 1]")
        if self.relative_liquidity_multiple is not None and (
            not isinstance(self.relative_liquidity_multiple, Decimal)
            or self.relative_liquidity_multiple <= 0
        ):
            raise ValueError("relative_liquidity_multiple must be None or a positive Decimal")


# ---------------------------------------------------------------------------
# Bar evidence / structure: Phase 7
# ---------------------------------------------------------------------------


def bar_evidence_refusal_v2(
    window: ObservationWindow | None, *, policy: OpportunityEnginePolicyV2
) -> RejectionReasonV2 | None:
    if window is None:
        return RejectionReasonV2.STALE_OR_MISSING_BARS
    if len(window.reference_bars) < policy.structure_lookback_bars:
        return RejectionReasonV2.STALE_OR_MISSING_BARS
    return None


@dataclass(frozen=True, slots=True)
class StructureMeasurementsV2:
    current_close: Decimal
    current_high: Decimal
    current_low: Decimal
    current_volume: int
    range_high: Decimal
    range_low: Decimal
    prior_swing_low: Decimal
    reference_average_volume: Decimal
    reference_median_volume: Decimal
    reference_average_range: Decimal
    close_location_value: Decimal
    volume_ratio: Decimal
    breakout_distance_percent: Decimal | None


def evaluate_structure_v2(
    window: ObservationWindow, *, lookback_bars: int
) -> tuple[bool, StructureMeasurementsV2]:
    """The SAME bounded-range-breakout-plus-higher-low structure V1 uses (a real, shared
    idea, not reinvented for its own sake), with the ADDITIONAL measurements Phase 7's
    entry-quality gates need: close-location-value and volume-ratio (both computed here so
    `entry_quality_refusal` never has to re-touch the window).
    """
    reference_bars = window.reference_bars
    if len(reference_bars) < lookback_bars:
        raise ValueError(
            f"ObservationWindow has {len(reference_bars)} reference bars; V2 structure "
            f"evaluation requires at least {lookback_bars}"
        )
    reference_window = reference_bars[-lookback_bars:]
    range_high = max(bar.high for bar in reference_window)
    range_low = min(bar.low for bar in reference_window)
    trough_index = min(range(len(reference_window)), key=lambda i: reference_window[i].low)
    prior_swing_low = min((bar.low for bar in reference_window[trough_index:]), default=range_low)
    volumes = [Decimal(bar.volume) for bar in reference_window]
    reference_average_volume = sum(volumes, start=Decimal(0)) / Decimal(len(volumes))
    sorted_volumes = sorted(volumes)
    mid = len(sorted_volumes) // 2
    reference_median_volume = (
        sorted_volumes[mid]
        if len(sorted_volumes) % 2 == 1
        else (sorted_volumes[mid - 1] + sorted_volumes[mid]) / Decimal(2)
    )
    ranges = [bar.high - bar.low for bar in reference_window]
    reference_average_range = sum(ranges, start=Decimal(0)) / Decimal(len(ranges))

    current = window.evaluation_bar
    breakout = current.close > range_high
    higher_low = current.low >= prior_swing_low
    volume_ratio = (
        Decimal(current.volume) / reference_average_volume
        if reference_average_volume > 0
        else Decimal(0)
    )
    bar_span = current.high - current.low
    close_location_value = (
        (current.close - current.low) / bar_span if bar_span > 0 else Decimal("0.5")
    )
    breakout_distance_percent = (
        (current.close - range_high) / (range_high - range_low) * _HUNDRED
        if range_high > range_low
        else None
    )

    measurements = StructureMeasurementsV2(
        current_close=current.close,
        current_high=current.high,
        current_low=current.low,
        current_volume=current.volume,
        range_high=range_high,
        range_low=range_low,
        prior_swing_low=prior_swing_low,
        reference_average_volume=reference_average_volume,
        reference_median_volume=reference_median_volume,
        reference_average_range=reference_average_range,
        close_location_value=close_location_value,
        volume_ratio=volume_ratio,
        breakout_distance_percent=breakout_distance_percent,
    )
    return breakout and higher_low, measurements


def entry_quality_refusal(
    measurements: StructureMeasurementsV2, *, policy: OpportunityEnginePolicyV2
) -> RejectionReasonV2 | None:
    """Phase 7: the STRONGER confirmation gates V1 did not have. Checked only for a
    candidate that already passed the base breakout/higher-low structure check."""
    if measurements.volume_ratio < policy.minimum_volume_ratio:
        return RejectionReasonV2.WEAK_BREAKOUT_VOLUME_RATIO
    if measurements.close_location_value < policy.minimum_close_location_value:
        return RejectionReasonV2.WEAK_CLOSE_LOCATION
    return None


# ---------------------------------------------------------------------------
# Liquidity: Phase 9
# ---------------------------------------------------------------------------


def liquidity_refusal_v2(
    window: ObservationWindow,
    measurements: StructureMeasurementsV2,
    *,
    policy: OpportunityEnginePolicyV2,
) -> RejectionReasonV2 | None:
    """Phase 9: an absolute floor (kept low -- a sanity check, not the primary gate) PLUS a
    relative check against the SAME symbol's own rolling median volume, so a naturally
    lower-absolute-volume symbol is not structurally excluded merely for being smaller.
    """
    if len(window.bars) < policy.structure_lookback_bars + 1:
        return RejectionReasonV2.INSUFFICIENT_EVIDENCE
    if measurements.current_volume < policy.minimum_recent_share_volume:
        return RejectionReasonV2.INSUFFICIENT_LIQUIDITY_ABSOLUTE
    if policy.relative_liquidity_multiple is not None:
        required = policy.relative_liquidity_multiple * measurements.reference_median_volume
        if Decimal(measurements.current_volume) < required:
            return RejectionReasonV2.INSUFFICIENT_LIQUIDITY_RELATIVE
    return None


# ---------------------------------------------------------------------------
# Geometry: Phase 10
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TradePlanGeometryV2:
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    risk_per_share: Decimal
    reward_per_share: Decimal
    reward_risk_ratio: Decimal


def plan_geometry_refusal_v2(
    *, entry_price: Decimal, stop_price: Decimal
) -> RejectionReasonV2 | None:
    if stop_price >= entry_price:
        return RejectionReasonV2.STOP_INVALID
    return None


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT)


def build_trade_plan_geometry_v2(
    *,
    entry_price: Decimal,
    measurements: StructureMeasurementsV2,
    policy: OpportunityEnginePolicyV2,
) -> TradePlanGeometryV2 | None:
    """Phase 10: the SAME structural stop V1 uses (the confirmed prior swing low -- a real,
    shared idea) but a RANGE-AWARE target: `entry + target_range_multiple * reference
    average bar range`, floored at `minimum_reward_risk_ratio` multiples of risk (never
    offered below the policy's own hard floor). Never a guaranteed outcome -- a deterministic
    geometry, documented as such everywhere it is rendered.
    """
    entry = _quantize(entry_price)
    stop = _quantize(measurements.prior_swing_low)
    if plan_geometry_refusal_v2(entry_price=entry, stop_price=stop) is not None:
        return None
    risk_per_share = _quantize(entry - stop)
    if risk_per_share <= 0:
        return None
    range_aware_target = entry + policy.target_range_multiple * measurements.reference_average_range
    floor_target = entry + policy.minimum_reward_risk_ratio * risk_per_share
    target = _quantize(max(range_aware_target, floor_target))
    reward_per_share = _quantize(target - entry)
    reward_risk_ratio = (reward_per_share / risk_per_share).quantize(Decimal("0.01"))
    return TradePlanGeometryV2(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        reward_risk_ratio=reward_risk_ratio,
    )


def reward_risk_refusal_v2(
    geometry: TradePlanGeometryV2, *, minimum_reward_risk_ratio: Decimal
) -> RejectionReasonV2 | None:
    if geometry.reward_risk_ratio < minimum_reward_risk_ratio:
        return RejectionReasonV2.REWARD_RISK_TOO_LOW
    return None


# ---------------------------------------------------------------------------
# Time-to-target feasibility: Phase 8
# ---------------------------------------------------------------------------


def time_to_target_refusal(
    *,
    geometry: TradePlanGeometryV2,
    measurements: StructureMeasurementsV2,
    remaining_bars_to_mandatory_exit: int,
    policy: OpportunityEnginePolicyV2,
) -> RejectionReasonV2 | None:
    """Phase 8: is the required move even structurally plausible given the remaining
    session and the symbol's own recently observed per-bar range? A bounded, deterministic
    bound -- `remaining_bars * reference_average_range * safety_factor` -- never a
    probability claim. Disabled (returns `None` unconditionally) unless the policy turns it
    on, so V2-A/V2-B are unaffected by this gate.
    """
    if not policy.time_to_target_feasibility_enabled:
        return None
    if remaining_bars_to_mandatory_exit <= 0:
        return RejectionReasonV2.TARGET_NOT_FEASIBLE_IN_REMAINING_TIME
    achievable = (
        Decimal(remaining_bars_to_mandatory_exit)
        * measurements.reference_average_range
        * policy.time_to_target_safety_factor
    )
    required = geometry.reward_per_share
    if required > achievable:
        return RejectionReasonV2.TARGET_NOT_FEASIBLE_IN_REMAINING_TIME
    return None


# ---------------------------------------------------------------------------
# Position size: unchanged concept from V1 (capital/risk math is not V1-specific), reused
# as its OWN V2 function so this module never imports from opportunity_engine.py.
# ---------------------------------------------------------------------------


def position_size_v2(
    *,
    entry_price: Decimal,
    stop_price: Decimal,
    maximum_loss: Decimal,
    maximum_capital_per_trade: Decimal,
    maximum_percent_per_trade: Decimal,
    deployable_capital: Decimal,
) -> int:
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        raise ValueError("risk_per_share must be positive; check plan_geometry_refusal_v2 first")
    by_risk = (maximum_loss / risk_per_share).to_integral_value(rounding=ROUND_DOWN)
    by_trade_cap = (maximum_capital_per_trade / entry_price).to_integral_value(rounding=ROUND_DOWN)
    by_percent_cap = (
        (deployable_capital * maximum_percent_per_trade / _HUNDRED) / entry_price
    ).to_integral_value(rounding=ROUND_DOWN)
    return int(min(by_risk, by_trade_cap, by_percent_cap))
