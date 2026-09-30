"""MILESTONE-090 -- the Opportunity Engine: a deterministic, auditable intraday long-only filter.

WHAT THIS IS NOT. Not an AI guessing direction, not a guaranteed-profit system, not a
black-box score, not an auto-trader. Every accepted opportunity explains WHY THIS SYMBOL, WHY
NOW, WHY THIS ENTRY, WHY THIS STOP, WHY THIS TARGET, WHY THIS SIZE, WHY THIS RISK in
machine-readable, reproducible terms; every rejected candidate carries machine-readable
rejection reasons. Nothing here places, modifies or cancels a broker order -- see
`opportunity_engine_repositories.py`'s module docstring for the port boundary that makes that
a structural fact, not a convention.

REUSE, NOT REINVENTION. The bounded universe is `OperatorTradingConfiguration.watchlist`
(already versioned, already validated) -- not a new universe concept. Quote freshness/spread
is judged by `paper_execution.quote_refusal` (M085, unchanged) against an `ExecutionPolicy`
derived the SAME way M085 already derives one. Bar sequences are `market_data.ObservationWindow`
(M057) -- the SAME look-ahead-bias defense Track A already built: a window's `evaluation_bar`
is the current bar and `reference_bars` are every strictly-prior bar; nothing after the
evaluation point is ever in scope, because the window itself cannot contain it.

DETERMINISM. Every function in this module is pure: same evidence, same policy, same
`TradingOpportunity`. No wall-clock read, no randomness, no I/O. The only "current instant"
concept here is `BoundedInstant`/broker time, supplied by the caller (the usecase layer), not
read internally -- matching M085's own discipline exactly.

FULL CLOSE ONLY, LONG ONLY, NO LEVERAGE. `build_trade_plan_geometry` cannot express a short (no
side field exists to flip); `position_size` never multiplies by a leverage factor and is capped
by the SAME capital fields `OperatorTradingConfiguration` already enforces for real orders.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.market_data import ObservationWindow
from empirical_platform.decision_candidate.paper_execution import (
    ExecutionPolicy,
    quote_refusal,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant

__all__ = [
    "OPPORTUNITY_ENGINE_POLICY_VERSION",
    "QUALITY_MODEL_ID",
    "QUALITY_MODEL_VERSION",
    "STRUCTURE_MODEL_ID",
    "STRUCTURE_MODEL_VERSION",
    "ALLOWED_OPPORTUNITY_TRANSITIONS",
    "AssetEvidence",
    "MarketSessionState",
    "OpportunityDecision",
    "OpportunityEnginePolicy",
    "OpportunityStatus",
    "OwnerOpportunityAction",
    "QuoteEvidence",
    "RejectionReason",
    "StructureEvaluation",
    "StructureMeasurements",
    "StructureReasonCode",
    "TradePlanGeometry",
    "TradingOpportunity",
    "asset_eligibility_refusal",
    "bar_evidence_refusal",
    "build_trade_plan_geometry",
    "evaluate_structure",
    "is_opportunity_transition_allowed",
    "liquidity_refusal",
    "mandatory_liquidation_at",
    "market_session_state",
    "opportunity_quality",
    "opportunity_valid_until",
    "plan_geometry_refusal",
    "position_size",
    "quote_quality_refusal",
    "rank_sort_key",
    "session_permits_actionable",
]

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT)


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.normalize()
    return format(normalized if normalized != 0 else Decimal(0), "f")


# ---------------------------------------------------------------------------
# Policy: Phase 5's "versioned M090 policy/configuration"
# ---------------------------------------------------------------------------

#: The FIRST versioned policy this engine ships with. A future change to any threshold below
#: is a NEW version string, never a silent edit of this one -- every `TradingOpportunity`
#: carries the policy fingerprint that produced it (see `OpportunityEnginePolicy.fingerprint`).
OPPORTUNITY_ENGINE_POLICY_VERSION = "M090-V1"


@dataclass(frozen=True, slots=True)
class OpportunityEnginePolicy:
    """Every configurable threshold this engine uses, in ONE versioned, auditable object.

    Fields that already exist on `OperatorTradingConfiguration` (spread, quote age, price
    bounds, capital caps, mandatory liquidation time, entry window) are NOT duplicated here --
    the usecase layer reads them from the SAME durable configuration M084/M085 already use, so
    there is exactly one source of truth for each. This object holds only what is genuinely new
    to the opportunity engine.
    """

    policy_version: str
    #: Phase 7: bars strictly before the evaluation bar used for the structure/breakout/volume
    #: reference calculation. Chosen small (not optimized): enough bars to describe "a recent
    #: bounded range" for 1-minute intraday structure without requiring a long warm-up.
    structure_lookback_bars: int
    #: Phase 6: the evaluation bar's own volume must reach at least this many shares, or the
    #: symbol is marked INSUFFICIENT_EVIDENCE rather than treated as liquid on a guess.
    minimum_recent_share_volume: int
    #: Phase 10: the hard reward/risk floor. Also used as target's OWN minimum multiple of risk
    #: (see `build_trade_plan_geometry`) -- the floor and the target's minimum distance are the
    #: same number on purpose: a target that does not clear the floor is not offered at all.
    minimum_reward_risk_ratio: Decimal
    #: Phase 11: the maximum a single opportunity's position size is permitted to risk if its
    #: stop is touched, BEFORE the usecase layer additionally caps it against
    #: `OperatorTradingConfiguration.maximum_capital_per_trade`/`maximum_percent_per_trade`/
    #: `minimum_cash_reserve` (the SAME fields M084 already enforces for real orders).
    maximum_loss_per_trade: Decimal
    #: Phase 14: only this many ranked survivors reach Today.
    top_n: int
    #: Phase 8: how far the market may move between evidence capture and Owner approval before
    #: the entry is judged to have moved outside tolerance (percent of the evidence entry price).
    entry_tolerance_percent: Decimal
    #: Phase 8/13: how long a CANDIDATE/ACTIONABLE row remains offerable before it EXPIREs.
    opportunity_validity_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")
        for field_name in ("structure_lookback_bars", "minimum_recent_share_volume", "top_n"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field_name} must be a positive int")
        if (
            isinstance(self.opportunity_validity_seconds, bool)
            or not isinstance(self.opportunity_validity_seconds, int)
            or self.opportunity_validity_seconds < 1
        ):
            raise ValueError("opportunity_validity_seconds must be a positive int")
        for field_name in ("minimum_reward_risk_ratio", "maximum_loss_per_trade"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ValueError(f"{field_name} must be a finite, positive Decimal")
        if not isinstance(self.entry_tolerance_percent, Decimal) or not (
            0 < self.entry_tolerance_percent < _HUNDRED
        ):
            raise ValueError("entry_tolerance_percent must be a Decimal strictly between 0 and 100")

    @property
    def fingerprint(self) -> str:
        return _canonical_digest(
            {
                "policy_version": self.policy_version,
                "structure_lookback_bars": self.structure_lookback_bars,
                "minimum_recent_share_volume": self.minimum_recent_share_volume,
                "minimum_reward_risk_ratio": _canonical_decimal(self.minimum_reward_risk_ratio),
                "maximum_loss_per_trade": _canonical_decimal(self.maximum_loss_per_trade),
                "top_n": self.top_n,
                "entry_tolerance_percent": _canonical_decimal(self.entry_tolerance_percent),
                "opportunity_validity_seconds": self.opportunity_validity_seconds,
            }
        )


# ---------------------------------------------------------------------------
# Market session gate: Phase 4
# ---------------------------------------------------------------------------


class MarketSessionState(StrEnum):
    """Research/display may continue in every state; only REGULAR_SESSION may be ACTIONABLE."""

    PREMARKET_RESEARCH = "PREMARKET_RESEARCH"
    REGULAR_SESSION = "REGULAR_SESSION"
    ENTRY_WINDOW_CLOSED = "ENTRY_WINDOW_CLOSED"
    MARKET_CLOSED = "MARKET_CLOSED"


def market_session_state(
    *,
    is_open: bool,
    broker_now: BoundedInstant,
    earliest_entry_time: time,
    latest_entry_time: time,
    operator_timezone: str,
) -> MarketSessionState:
    """The session state, judged conservatively against the WIDEST instant the broker clock
    permits, so a boundary-straddling instant never reads as more permissive than it may be.

    Uses the broker's own `is_open` (the market calendar's own truth, never re-derived from a
    naive weekday/holiday guess) plus the SAME `earliest_entry_time`/`latest_entry_time`/
    `operator_timezone` fields `OperatorTradingConfiguration`/`ExecutionPolicy` already carry.
    """
    if not is_open:
        return MarketSessionState.MARKET_CLOSED
    zone = ZoneInfo(operator_timezone)
    earliest_local = broker_now.earliest.astimezone(zone).time()
    latest_local = broker_now.latest.astimezone(zone).time()
    if latest_local < earliest_entry_time:
        return MarketSessionState.PREMARKET_RESEARCH
    if earliest_local > latest_entry_time:
        return MarketSessionState.ENTRY_WINDOW_CLOSED
    if earliest_local < earliest_entry_time or latest_local > latest_entry_time:
        # The broker's own uncertainty interval straddles a boundary: conservative, not
        # actionable, until a tighter reading resolves it.
        return MarketSessionState.ENTRY_WINDOW_CLOSED
    return MarketSessionState.REGULAR_SESSION


def session_permits_actionable(state: MarketSessionState) -> bool:
    return state is MarketSessionState.REGULAR_SESSION


# ---------------------------------------------------------------------------
# Rejection reasons: Phase 2 ("every rejected symbol should have machine-readable reasons")
# ---------------------------------------------------------------------------


class RejectionReason(StrEnum):
    NOT_TRADABLE = "NOT_TRADABLE"
    NOT_ACTIVE = "NOT_ACTIVE"
    NOT_ON_APPROVED_MARKET = "NOT_ON_APPROVED_MARKET"
    NOT_ON_WATCHLIST = "NOT_ON_WATCHLIST"
    PROHIBITED_INSTRUMENT = "PROHIBITED_INSTRUMENT"
    PRICE_TOO_LOW = "PRICE_TOO_LOW"
    PRICE_TOO_HIGH = "PRICE_TOO_HIGH"
    QUOTE_STALE_OR_INVALID = "QUOTE_STALE_OR_INVALID"
    STALE_OR_MISSING_BARS = "STALE_OR_MISSING_BARS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    NO_BREAKOUT_STRUCTURE = "NO_BREAKOUT_STRUCTURE"
    STOP_INVALID = "STOP_INVALID"
    REWARD_RISK_TOO_LOW = "REWARD_RISK_TOO_LOW"
    QUANTITY_LESS_THAN_ONE = "QUANTITY_LESS_THAN_ONE"
    SESSION_NOT_ACTIONABLE = "SESSION_NOT_ACTIONABLE"
    ENTRY_MOVED_OUTSIDE_TOLERANCE = "ENTRY_MOVED_OUTSIDE_TOLERANCE"


# ---------------------------------------------------------------------------
# Asset eligibility and data-quality gates: Phase 3, 5
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssetEvidence:
    symbol: str
    tradable: bool
    status: str
    exchange: str


def asset_eligibility_refusal(
    *,
    asset: AssetEvidence | None,
    symbol: str,
    watchlist: tuple[str, ...],
    prohibited_instruments: tuple[str, ...],
    permitted_markets: tuple[str, ...],
) -> RejectionReason | None:
    """Phase 3's universe filters, in precedence order. `None` means eligible to proceed."""
    if symbol not in watchlist:
        return RejectionReason.NOT_ON_WATCHLIST
    if symbol in prohibited_instruments:
        return RejectionReason.PROHIBITED_INSTRUMENT
    if asset is None:
        return RejectionReason.INSUFFICIENT_EVIDENCE
    if asset.status != "active":
        return RejectionReason.NOT_ACTIVE
    if not asset.tradable:
        return RejectionReason.NOT_TRADABLE
    if permitted_markets and asset.exchange not in permitted_markets:
        return RejectionReason.NOT_ON_APPROVED_MARKET
    return None


def price_bounds_refusal(
    *, price: Decimal, minimum_price: Decimal, maximum_price: Decimal | None
) -> RejectionReason | None:
    if price < minimum_price:
        return RejectionReason.PRICE_TOO_LOW
    if maximum_price is not None and price > maximum_price:
        return RejectionReason.PRICE_TOO_HIGH
    return None


@dataclass(frozen=True, slots=True)
class QuoteEvidence:
    bid: Decimal | None
    ask: Decimal | None
    captured_at: datetime | None
    source: str


def quote_quality_refusal(
    *, quote: QuoteEvidence, execution_policy: ExecutionPolicy, broker_now: BoundedInstant
) -> RejectionReason | None:
    """Phase 5's quote-freshness/spread gate: `quote_refusal` (M085), reused unchanged.

    `execution_policy` is the SAME `ExecutionPolicy` M085 already derives from
    `OperatorTradingConfiguration` -- `quote_maximum_age_seconds`/`maximum_spread_percent` are
    not re-specified in `OpportunityEnginePolicy`.
    """
    refusal = quote_refusal(
        bid=quote.bid,
        ask=quote.ask,
        captured_at=quote.captured_at,
        policy=execution_policy,
        broker_now=broker_now,
    )
    return None if refusal is None else RejectionReason.QUOTE_STALE_OR_INVALID


def bar_evidence_refusal(
    window: ObservationWindow | None, *, policy: OpportunityEnginePolicy
) -> RejectionReason | None:
    """Phase 5's bar-evidence gate. `ObservationWindow.__post_init__` already refuses
    non-chronological or duplicate timestamps and non-positive/inconsistent OHLC (M057) -- this
    only checks what a valid-but-thin window can still fail: not enough reference bars."""
    if window is None:
        return RejectionReason.STALE_OR_MISSING_BARS
    if len(window.reference_bars) < policy.structure_lookback_bars:
        return RejectionReason.STALE_OR_MISSING_BARS
    return None


def liquidity_refusal(
    window: ObservationWindow, *, policy: OpportunityEnginePolicy
) -> RejectionReason | None:
    """Phase 6: reject weak liquidity using ONLY evidence actually measured (recent bar volume
    and bar participation) -- never a fabricated average-daily-volume figure. A window with
    fewer bars than required to even judge participation is INSUFFICIENT_EVIDENCE, not assumed
    liquid."""
    if len(window.bars) < policy.structure_lookback_bars + 1:
        return RejectionReason.INSUFFICIENT_EVIDENCE
    if window.evaluation_bar.volume < policy.minimum_recent_share_volume:
        return RejectionReason.INSUFFICIENT_LIQUIDITY
    return None


# ---------------------------------------------------------------------------
# Structure / signal: Phase 7
# ---------------------------------------------------------------------------

#: A versioned model id, mirroring M058's `RANKING_MODEL_ID` pattern: a pure function, a
#: closed evidence set, never silently changed without a new version string.
STRUCTURE_MODEL_ID = "BOUNDED_RANGE_BREAKOUT_HIGHER_LOW_VOLUME"
STRUCTURE_MODEL_VERSION = "1"


class StructureReasonCode(StrEnum):
    BREAKOUT_ABOVE_RANGE_HIGH = "BREAKOUT_ABOVE_RANGE_HIGH"
    NO_BREAKOUT_ABOVE_RANGE_HIGH = "NO_BREAKOUT_ABOVE_RANGE_HIGH"
    HIGHER_LOW_CONFIRMED = "HIGHER_LOW_CONFIRMED"
    NO_HIGHER_LOW = "NO_HIGHER_LOW"
    VOLUME_ABOVE_REFERENCE_AVERAGE = "VOLUME_ABOVE_REFERENCE_AVERAGE"
    VOLUME_NOT_ABOVE_REFERENCE_AVERAGE = "VOLUME_NOT_ABOVE_REFERENCE_AVERAGE"


@dataclass(frozen=True, slots=True)
class StructureMeasurements:
    """The exact numeric measurements the structure decision was computed from."""

    current_close: Decimal
    current_volume: int
    range_high: Decimal
    range_low: Decimal
    prior_swing_low: Decimal
    reference_average_volume: Decimal


@dataclass(frozen=True, slots=True)
class StructureEvaluation:
    is_long_candidate: bool
    reasons: tuple[StructureReasonCode, ...]
    measurements: StructureMeasurements


def evaluate_structure(window: ObservationWindow, *, lookback_bars: int) -> StructureEvaluation:
    """The smallest deterministic, auditable evidence set (Phase 7): a bounded-range breakout,
    confirmed by higher-low structure and above-average volume, ALL measured over the SAME
    `lookback_bars` reference window `bar_evidence_refusal` already required to be present.

    Reads `window.reference_bars` (strictly prior bars) for the reference range/swing-low/
    average-volume calculation and `window.evaluation_bar` for the current price/volume --
    exactly M057's `strategy.evaluate` discipline, reused as a pattern (see module docstring),
    never anything the window does not itself contain.

    Raises `ValueError` if fewer than `lookback_bars` reference bars exist -- call
    `bar_evidence_refusal` first, which is the intended fail-closed gate for that case.
    """
    reference_bars = window.reference_bars
    if len(reference_bars) < lookback_bars:
        raise ValueError(
            f"ObservationWindow has {len(reference_bars)} reference bars; structure evaluation "
            f"requires at least {lookback_bars}"
        )
    reference_window = reference_bars[-lookback_bars:]
    range_high = max(bar.high for bar in reference_window)
    range_low = min(bar.low for bar in reference_window)
    #: The prior swing low: the lowest LOW reached AFTER the reference window's own lowest
    #: point -- i.e. the most recent higher-low pivot, the structural level a breakout is
    #: judged to have invalidated if price returns to it. For a monotonically rising window
    #: this is the last bar's low; for one still forming its low it is the true recent pivot.
    trough_index = min(range(len(reference_window)), key=lambda index: reference_window[index].low)
    prior_swing_low = min((bar.low for bar in reference_window[trough_index:]), default=range_low)
    reference_average_volume = sum((bar.volume for bar in reference_window), start=0) / Decimal(
        len(reference_window)
    )

    current = window.evaluation_bar
    breakout = current.close > range_high
    higher_low = current.low >= prior_swing_low
    volume_confirmed = Decimal(current.volume) > reference_average_volume

    reasons = (
        StructureReasonCode.BREAKOUT_ABOVE_RANGE_HIGH
        if breakout
        else StructureReasonCode.NO_BREAKOUT_ABOVE_RANGE_HIGH,
        StructureReasonCode.HIGHER_LOW_CONFIRMED
        if higher_low
        else StructureReasonCode.NO_HIGHER_LOW,
        StructureReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE
        if volume_confirmed
        else StructureReasonCode.VOLUME_NOT_ABOVE_REFERENCE_AVERAGE,
    )
    return StructureEvaluation(
        is_long_candidate=breakout and higher_low and volume_confirmed,
        reasons=reasons,
        measurements=StructureMeasurements(
            current_close=current.close,
            current_volume=current.volume,
            range_high=range_high,
            range_low=range_low,
            prior_swing_low=prior_swing_low,
            reference_average_volume=reference_average_volume,
        ),
    )


# ---------------------------------------------------------------------------
# Entry / stop / target / size / mandatory exit: Phase 8-12
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TradePlanGeometry:
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    risk_per_share: Decimal
    reward_per_share: Decimal
    reward_risk_ratio: Decimal


def plan_geometry_refusal(*, entry_price: Decimal, stop_price: Decimal) -> RejectionReason | None:
    if stop_price >= entry_price:
        return RejectionReason.STOP_INVALID
    return None


def build_trade_plan_geometry(
    *, entry_price: Decimal, structure: StructureMeasurements, policy: OpportunityEnginePolicy
) -> TradePlanGeometry | None:
    """Phase 9/10: a STRUCTURAL stop (the confirmed prior swing low), never an arbitrary dollar
    amount, and a target that is exactly the policy's own reward/risk floor applied to that
    risk -- the floor and the target's minimum multiple are the same number, so a target is
    never offered below the floor it will also be judged against. Returns `None` (never a
    negative-risk or inverted plan) when the stop is not below the entry.
    """
    entry = _quantize(entry_price)
    stop = _quantize(structure.prior_swing_low)
    if plan_geometry_refusal(entry_price=entry, stop_price=stop) is not None:
        return None
    risk_per_share = _quantize(entry - stop)
    if risk_per_share <= 0:
        return None
    target = _quantize(entry + policy.minimum_reward_risk_ratio * risk_per_share)
    reward_per_share = _quantize(target - entry)
    reward_risk_ratio = (reward_per_share / risk_per_share).quantize(Decimal("0.01"))
    return TradePlanGeometry(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        reward_risk_ratio=reward_risk_ratio,
    )


def reward_risk_refusal(
    geometry: TradePlanGeometry, *, minimum_reward_risk_ratio: Decimal
) -> RejectionReason | None:
    if geometry.reward_risk_ratio < minimum_reward_risk_ratio:
        return RejectionReason.REWARD_RISK_TOO_LOW
    return None


def position_size(
    *,
    entry_price: Decimal,
    stop_price: Decimal,
    maximum_loss: Decimal,
    maximum_capital_per_trade: Decimal,
    maximum_percent_per_trade: Decimal,
    deployable_capital: Decimal,
) -> int:
    """Phase 11: the quantity is the MINIMUM every applicable cap allows, floored to a whole
    share, never leveraged (no factor here multiplies size beyond capital actually available)
    and never negative (a non-positive risk-per-share, which `build_trade_plan_geometry` already
    refuses to produce, would make this undefined -- callers must not reach here with one).
    """
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        raise ValueError("risk_per_share must be positive; check plan_geometry_refusal first")
    by_risk = (maximum_loss / risk_per_share).to_integral_value(rounding=ROUND_DOWN)
    by_trade_cap = (maximum_capital_per_trade / entry_price).to_integral_value(rounding=ROUND_DOWN)
    by_percent_cap = (
        (deployable_capital * maximum_percent_per_trade / _HUNDRED) / entry_price
    ).to_integral_value(rounding=ROUND_DOWN)
    return int(min(by_risk, by_trade_cap, by_percent_cap))


def mandatory_liquidation_at(
    *, session_date: date, liquidation_time: time, operator_timezone: str
) -> datetime:
    """Phase 12: reuses `OperatorTradingConfiguration.mandatory_liquidation_time` (the SAME
    field M084/M085 already apply), never a new deadline concept. Returned in UTC."""
    zone = ZoneInfo(operator_timezone)
    local = datetime.combine(session_date, liquidation_time, tzinfo=zone)
    return local.astimezone(UTC)


def opportunity_valid_until(
    *, generated_at: datetime, policy: OpportunityEnginePolicy, liquidation_at: datetime
) -> datetime:
    """Phase 8/13: an opportunity never claims validity past its own mandatory exit."""
    return min(
        generated_at + timedelta(seconds=policy.opportunity_validity_seconds), liquidation_at
    )


def entry_moved_refusal(
    *, evidence_entry_price: Decimal, current_price: Decimal, policy: OpportunityEnginePolicy
) -> RejectionReason | None:
    """Phase 16: re-checked at Review/Approval. Price moving MORE than the tolerance in EITHER
    direction invalidates -- a favorable move is not silently accepted at a worse-than-reviewed
    entry either, since the Owner approved the exact terms shown, not "better or worse.\""""
    if evidence_entry_price <= 0:
        raise ValueError("evidence_entry_price must be positive")
    moved_percent = abs(current_price - evidence_entry_price) / evidence_entry_price * _HUNDRED
    if moved_percent > policy.entry_tolerance_percent:
        return RejectionReason.ENTRY_MOVED_OUTSIDE_TOLERANCE
    return None


# ---------------------------------------------------------------------------
# The Opportunity object: Phase 13
# ---------------------------------------------------------------------------


class OpportunityStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    ACTIONABLE = "ACTIONABLE"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    REJECTED = "REJECTED"
    OWNER_APPROVED = "OWNER_APPROVED"
    OWNER_IGNORED = "OWNER_IGNORED"


#: The closed transition table. REJECTED is terminal at creation (a symbol that failed a hard
#: gate is never later reconsidered under the SAME opportunity_id); CANDIDATE may only ever
#: become ACTIONABLE, EXPIRED or INVALIDATED -- never OWNER_APPROVED/OWNER_IGNORED directly,
#: because those require passing through ACTIONABLE (an opportunity the Owner was never shown
#: as actionable cannot be approved).
ALLOWED_OPPORTUNITY_TRANSITIONS: dict[OpportunityStatus, frozenset[OpportunityStatus]] = {
    OpportunityStatus.CANDIDATE: frozenset(
        {OpportunityStatus.ACTIONABLE, OpportunityStatus.EXPIRED, OpportunityStatus.INVALIDATED}
    ),
    OpportunityStatus.ACTIONABLE: frozenset(
        {
            OpportunityStatus.EXPIRED,
            OpportunityStatus.INVALIDATED,
            OpportunityStatus.OWNER_APPROVED,
            OpportunityStatus.OWNER_IGNORED,
        }
    ),
    OpportunityStatus.EXPIRED: frozenset(),
    OpportunityStatus.INVALIDATED: frozenset(),
    OpportunityStatus.REJECTED: frozenset(),
    OpportunityStatus.OWNER_APPROVED: frozenset(),
    OpportunityStatus.OWNER_IGNORED: frozenset(),
}


def is_opportunity_transition_allowed(
    current: OpportunityStatus, target: OpportunityStatus
) -> bool:
    if not isinstance(current, OpportunityStatus) or not isinstance(target, OpportunityStatus):
        raise ValueError("both states must be OpportunityStatus members")
    return target in ALLOWED_OPPORTUNITY_TRANSITIONS[current]


@dataclass(frozen=True, slots=True)
class TradingOpportunity:
    """One deterministic research artifact: everything the Owner needs to judge, approve or
    ignore a plan, and everything an auditor needs to reproduce why it was offered or refused.
    """

    opportunity_id: str
    policy_fingerprint: str
    symbol: str
    generated_at: datetime
    expires_at: datetime
    evidence_as_of: datetime
    session: MarketSessionState
    bid: Decimal | None
    ask: Decimal | None
    spread_percent: Decimal | None
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_price: Decimal | None
    risk_per_share: Decimal | None
    reward_per_share: Decimal | None
    reward_risk_ratio: Decimal | None
    quantity: int | None
    notional: Decimal | None
    maximum_loss: Decimal | None
    mandatory_liquidation_at: datetime | None
    structure_model_id: str
    structure_model_version: str
    evidence: tuple[str, ...]
    quality_score: Decimal | None
    quality_model_id: str
    quality_model_version: str
    rejection_reasons: tuple[RejectionReason, ...]
    status: OpportunityStatus

    def __post_init__(self) -> None:
        if not self.opportunity_id or not self.opportunity_id.strip():
            raise ValueError("opportunity_id must be a non-empty string")
        if not self.symbol or self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be upper-case and unpadded")
        for field_name in ("generated_at", "expires_at", "evidence_as_of"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError(f"{field_name} must be a timezone-aware datetime")
        if self.expires_at <= self.generated_at:
            raise ValueError("expires_at must follow generated_at")
        if not isinstance(self.status, OpportunityStatus):
            raise ValueError("status must be an OpportunityStatus")
        if self.status is OpportunityStatus.ACTIONABLE:
            if self.rejection_reasons:
                raise ValueError("an ACTIONABLE opportunity cannot carry rejection reasons")
            required = (
                self.entry_price,
                self.stop_price,
                self.target_price,
                self.quantity,
                self.mandatory_liquidation_at,
            )
            if any(value is None for value in required):
                raise ValueError(
                    "an ACTIONABLE opportunity must carry entry/stop/target/quantity/"
                    "mandatory_liquidation_at: every hard gate must have actually passed"
                )
            assert self.entry_price is not None and self.stop_price is not None
            if self.stop_price >= self.entry_price:
                raise ValueError("an ACTIONABLE opportunity cannot carry stop >= entry")
            assert self.quantity is not None
            if self.quantity < 1:
                raise ValueError("an ACTIONABLE opportunity cannot carry quantity < 1")
        if self.status is OpportunityStatus.REJECTED and not self.rejection_reasons:
            raise ValueError("a REJECTED opportunity must carry at least one rejection reason")


# ---------------------------------------------------------------------------
# Ranking: Phase 14
# ---------------------------------------------------------------------------

#: "Opportunity Quality" -- never "chance of profit" or "win probability" anywhere this is
#: rendered. A weighted sum of measurable, already-gated evidence; documented, versioned.
QUALITY_MODEL_ID = "SPREAD_LIQUIDITY_TREND_REWARD_RISK_FRESHNESS_WEIGHTED_SUM"
QUALITY_MODEL_VERSION = "1"

#: Weights sum to 1 for interpretability (a 0-100 style score after scaling); each factor is
#: itself normalized to [0, 1] before weighting. Chosen to favor reward/risk and liquidity
#: (the two factors most directly tied to "can this be filled and is the plan worth the risk")
#: over freshness/spread (gates already enforced as hard pass/fail, so their remaining
#: variation among survivors is a secondary signal, not a primary one).
_WEIGHT_SPREAD = Decimal("0.15")
_WEIGHT_LIQUIDITY = Decimal("0.20")
_WEIGHT_TREND = Decimal("0.15")
_WEIGHT_REWARD_RISK = Decimal("0.35")
_WEIGHT_FRESHNESS = Decimal("0.15")


def _normalized(value: Decimal, *, floor: Decimal, ceiling: Decimal) -> Decimal:
    """Clamp-and-scale `value` into [0, 1] against `[floor, ceiling]`. `ceiling <= floor`
    always yields 1 (a degenerate band means "any passing value is maximally good")."""
    if ceiling <= floor:
        return Decimal(1)
    if value <= floor:
        return Decimal(0)
    if value >= ceiling:
        return Decimal(1)
    return (value - floor) / (ceiling - floor)


def opportunity_quality(
    *,
    spread_percent: Decimal,
    maximum_spread_percent: Decimal,
    recent_volume: int,
    minimum_recent_share_volume: int,
    structure: StructureMeasurements,
    geometry: TradePlanGeometry,
    minimum_reward_risk_ratio: Decimal,
    quote_age_seconds: Decimal,
    maximum_quote_age_seconds: int,
) -> Decimal:
    """A pure function over ALREADY-GATED evidence (every input here belongs to an opportunity
    that already passed every hard gate) -- ranking never substitutes for or bypasses a gate
    (Phase 14: "hard fail first, rank survivors second"). Returns a Decimal in [0, 100].
    """
    spread_quality = Decimal(1) - _normalized(
        spread_percent, floor=Decimal(0), ceiling=maximum_spread_percent
    )
    liquidity_quality = _normalized(
        Decimal(recent_volume),
        floor=Decimal(minimum_recent_share_volume),
        ceiling=Decimal(minimum_recent_share_volume) * Decimal(5),
    )
    trend_quality = _normalized(
        structure.current_close - structure.range_high,
        floor=Decimal(0),
        ceiling=(structure.range_high - structure.range_low)
        if structure.range_high > structure.range_low
        else Decimal(1),
    )
    reward_risk_quality = _normalized(
        geometry.reward_risk_ratio,
        floor=minimum_reward_risk_ratio,
        ceiling=minimum_reward_risk_ratio * Decimal(3),
    )
    freshness_quality = Decimal(1) - _normalized(
        quote_age_seconds, floor=Decimal(0), ceiling=Decimal(maximum_quote_age_seconds)
    )
    score = (
        _WEIGHT_SPREAD * spread_quality
        + _WEIGHT_LIQUIDITY * liquidity_quality
        + _WEIGHT_TREND * trend_quality
        + _WEIGHT_REWARD_RISK * reward_risk_quality
        + _WEIGHT_FRESHNESS * freshness_quality
    ) * _HUNDRED
    return score.quantize(Decimal("0.1"))


def rank_sort_key(opportunity: TradingOpportunity) -> tuple[Decimal, str]:
    """Score descending, symbol ascending tiebreak -- mirrors M058's `rank_sort_key` shape."""
    score = opportunity.quality_score if opportunity.quality_score is not None else Decimal(0)
    return (-score, opportunity.symbol)


# ---------------------------------------------------------------------------
# Owner decision: Phase 15-17
# ---------------------------------------------------------------------------


class OwnerOpportunityAction(StrEnum):
    APPROVE = "APPROVE"
    IGNORE = "IGNORE"


@dataclass(frozen=True, slots=True)
class OpportunityDecision:
    """The Owner's one, durable, single-use decision on one opportunity."""

    decision_id: str
    opportunity_id: str
    action: OwnerOpportunityAction
    decided_by: str
    decided_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("decision_id", "opportunity_id", "decided_by"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.action, OwnerOpportunityAction):
            raise ValueError("action must be an OwnerOpportunityAction")
        if not isinstance(self.decided_at, datetime) or self.decided_at.tzinfo is None:
            raise ValueError("decided_at must be a timezone-aware datetime")
