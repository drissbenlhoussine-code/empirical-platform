"""Position sizing and capital-risk gate: if a TradePlan is approved, how
large may the position be without violating explicit capital-risk rules?

MILESTONE-060. Answers the question M059 deliberately left open (see
MILESTONE_059 scope Section 10): an `APPROVED_PLAN` proves a trade's risk
*geometry* is acceptable, but says nothing about size -- an approved plan
does not mean unlimited size. This module consumes an already-persisted,
already-approved `TradePlan` plus a caller-supplied capital/risk sizing
context, and gates the resulting quantity against one explicit, versioned
sizing policy: every `PositionPlan` is either `APPROVED_POSITION_PLAN` or
`REJECTED_POSITION_PLAN`, never a naked quantity, and a `REJECTED_PLAN`
TradePlan can never become an `APPROVED_POSITION_PLAN` -- there is no
override or "force" parameter anywhere in this module.

No live brokerage order is placed anywhere in this module or the usecases
built on it. No account, portfolio, cash-ledger, margin, or leverage
concept is introduced -- `account_equity` is a plain caller-supplied number
describing this one sizing calculation, not a persisted or mutable
aggregate. THIS MODULE DOES NOT CLAIM A PROFITABLE OUTCOME -- it only
proves a specific quantity satisfies one explicit, versioned risk/capital
policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.trade_plan import TradePlan, TradePlanStatus
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PositionPlanId, TradePlanId

SIZING_POLICY_ID = "EQUITY_PERCENT_RISK_SIZING_GATE"
SIZING_POLICY_VERSION = "1"


@dataclass(frozen=True, slots=True)
class SizingPolicy:
    """One explicit, versioned capital-risk sizing policy.

    **This is a first product contract, not historical or industry
    authority.** No frozen numeric sizing policy existed anywhere in this
    repository before M060 (Phase 1 inventory: zero pre-existing
    position-sizing code) -- these parameters are M060's own origination,
    transparently labeled as such.

    `maximum_risk_percent` bounds the caller-supplied `risk_percent` a
    sizing request may use (the caller chooses how much of their own
    equity to risk on this specific trade; the policy caps how aggressive
    that choice may be). `maximum_notional_percent` bounds position size
    as a fraction of equity, independent of risk-derived quantity --
    the second, independent gate `build_position_plan()` enforces (see
    Section 5 of MILESTONE_060 scope). `allow_fractional_shares` is
    `False` for v1 (Section 9): whole shares only.
    """

    policy_id: str = SIZING_POLICY_ID
    policy_version: str = SIZING_POLICY_VERSION
    maximum_risk_percent: Decimal = Decimal("0.02")
    maximum_notional_percent: Decimal = Decimal("0.25")
    allow_fractional_shares: bool = False

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if self.maximum_risk_percent <= 0:
            raise ValueError("maximum_risk_percent must be positive")
        if self.maximum_notional_percent <= 0:
            raise ValueError("maximum_notional_percent must be positive")
        if self.allow_fractional_shares:
            raise ValueError("fractional shares are not supported in policy version 1")


DEFAULT_SIZING_POLICY = SizingPolicy()


@dataclass(frozen=True, slots=True)
class PositionSizingContext:
    """The minimum caller-supplied capital/risk context for one sizing
    calculation.

    Deliberately not an Account or Portfolio aggregate -- there is no
    persisted, mutable capital state anywhere in this platform (Phase 20).
    `account_equity` describes only this one calculation; a different
    calculation for the same TradePlan may freely supply a different
    equity or risk_percent, producing an independent PositionPlan (Section
    11: append-only, never mutated).
    """

    account_equity: Decimal
    risk_percent: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.account_equity, Decimal):
            raise TypeError("account_equity must be a Decimal")
        if not isinstance(self.risk_percent, Decimal):
            raise TypeError("risk_percent must be a Decimal")


class PositionPlanStatus(StrEnum):
    """Closed decision vocabulary. Never a naked quantity."""

    APPROVED_POSITION_PLAN = "APPROVED_POSITION_PLAN"
    REJECTED_POSITION_PLAN = "REJECTED_POSITION_PLAN"


class PositionPlanRejectionReason(StrEnum):
    """Machine-readable reason codes. Only reasons the implementation can
    actually produce are listed here."""

    SOURCE_PLAN_NOT_APPROVED = "SOURCE_PLAN_NOT_APPROVED"
    INVALID_EQUITY = "INVALID_EQUITY"
    INVALID_RISK_BUDGET = "INVALID_RISK_BUDGET"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    ZERO_POSITION_SIZE = "ZERO_POSITION_SIZE"
    CAPITAL_LIMIT_EXCEEDED = "CAPITAL_LIMIT_EXCEEDED"


@dataclass(frozen=True, slots=True)
class PositionSizing:
    """The exact, self-explaining sizing computation a decision was
    derived from -- structurally correct regardless of the final
    APPROVED/REJECTED outcome (mirroring `TradePlanGeometry`'s own
    preserved-on-threshold-rejection precedent). Approval-specific
    invariants (`quantity > 0`, risk/notional within budget) are enforced
    one level up, on `PositionPlan.__post_init__`, since a `quantity == 0`
    sizing computation is itself a valid, auditable result for
    `ZERO_POSITION_SIZE`/`CAPITAL_LIMIT_EXCEEDED`.
    """

    entry_price: Decimal
    stop_price: Decimal
    risk_per_unit: Decimal
    allowed_risk_amount: Decimal
    maximum_notional: Decimal
    risk_based_quantity: int
    capital_based_quantity: int
    quantity: int
    position_notional: Decimal
    actual_risk: Decimal

    def __post_init__(self) -> None:
        for field_name in (
            "entry_price",
            "stop_price",
            "risk_per_unit",
            "allowed_risk_amount",
            "maximum_notional",
            "position_notional",
            "actual_risk",
        ):
            if not isinstance(getattr(self, field_name), Decimal):
                raise TypeError(f"{field_name} must be a Decimal")
        for field_name in ("risk_based_quantity", "capital_based_quantity", "quantity"):
            if not isinstance(getattr(self, field_name), int):
                raise TypeError(f"{field_name} must be an int")
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if self.risk_per_unit <= 0:
            raise ValueError("risk_per_unit must be positive")
        if self.allowed_risk_amount < 0:
            raise ValueError("allowed_risk_amount must not be negative")
        if self.maximum_notional < 0:
            raise ValueError("maximum_notional must not be negative")
        if self.risk_based_quantity < 0:
            raise ValueError("risk_based_quantity must not be negative")
        if self.capital_based_quantity < 0:
            raise ValueError("capital_based_quantity must not be negative")
        if self.quantity < 0:
            raise ValueError("quantity must not be negative")
        if self.quantity != min(self.risk_based_quantity, self.capital_based_quantity):
            raise ValueError("quantity must equal min(risk_based_quantity, capital_based_quantity)")
        if self.position_notional != Decimal(self.quantity) * self.entry_price:
            raise ValueError("position_notional must equal quantity * entry_price")
        if self.actual_risk != Decimal(self.quantity) * self.risk_per_unit:
            raise ValueError("actual_risk must equal quantity * risk_per_unit")


def _floor_quantity(numerator: Decimal, denominator: Decimal) -> int:
    """Deterministic whole-unit floor division, Decimal throughout -- no
    binary float anywhere in this module's financial math."""
    return int((numerator / denominator).to_integral_value(rounding=ROUND_FLOOR))


@dataclass(frozen=True, slots=True)
class PositionPlan:
    """One immutable, persisted, independently-auditable position-sizing
    decision -- APPROVED_POSITION_PLAN or REJECTED_POSITION_PLAN, never a
    naked quantity.

    Like `TradePlan` (M059), deliberately NOT a lifecycle aggregate: a
    sizing decision is a fact computed once from a fixed, already-persisted
    source (`TradePlan` + caller-supplied `PositionSizingContext` +
    `SizingPolicy`) and never mutated afterward. If capital or risk
    tolerance changes, a NEW PositionPlan is built; the old one is never
    revised (Section 11).
    """

    identity: DomainIdentity[PositionPlanId]
    source_trade_plan_id: TradePlanId
    instrument: Instrument
    policy_id: str
    policy_version: str
    policy_maximum_risk_percent: Decimal
    policy_maximum_notional_percent: Decimal
    policy_allow_fractional_shares: bool
    supplied_account_equity: Decimal
    supplied_risk_percent: Decimal
    status: PositionPlanStatus
    sizing: PositionSizing | None
    reasons: tuple[PositionPlanRejectionReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[PositionPlanId]")
        if not isinstance(self.identity.governance_id, PositionPlanId):
            raise TypeError("identity governance_id must be a PositionPlanId")
        if not isinstance(self.source_trade_plan_id, TradePlanId):
            raise TypeError("source_trade_plan_id must be a TradePlanId")
        if not isinstance(self.policy_maximum_risk_percent, Decimal):
            raise TypeError("policy_maximum_risk_percent must be a Decimal")
        if not isinstance(self.policy_maximum_notional_percent, Decimal):
            raise TypeError("policy_maximum_notional_percent must be a Decimal")
        if not isinstance(self.policy_allow_fractional_shares, bool):
            raise TypeError("policy_allow_fractional_shares must be a bool")
        if not isinstance(self.supplied_account_equity, Decimal):
            raise TypeError("supplied_account_equity must be a Decimal")
        if not isinstance(self.supplied_risk_percent, Decimal):
            raise TypeError("supplied_risk_percent must be a Decimal")
        for field_name in ("policy_id", "policy_version"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.policy_maximum_risk_percent <= 0:
            raise ValueError("policy_maximum_risk_percent must be positive")
        if self.policy_maximum_notional_percent <= 0:
            raise ValueError("policy_maximum_notional_percent must be positive")

        is_approved = self.status is PositionPlanStatus.APPROVED_POSITION_PLAN
        if is_approved:
            if self.sizing is None:
                raise ValueError("an APPROVED_POSITION_PLAN must carry sizing")
            if self.reasons:
                raise ValueError("an APPROVED_POSITION_PLAN must carry no rejection reasons")
            if self.sizing.quantity <= 0:
                raise ValueError("an APPROVED_POSITION_PLAN must carry a positive quantity")
            if self.sizing.actual_risk > self.sizing.allowed_risk_amount:
                raise ValueError("actual_risk must not exceed allowed_risk_amount")
            if self.sizing.position_notional > self.sizing.maximum_notional:
                raise ValueError("position_notional must not exceed maximum_notional")
        else:
            if not self.reasons:
                raise ValueError(
                    "a REJECTED_POSITION_PLAN must carry at least one rejection reason"
                )
            if len(self.reasons) != 1:
                raise ValueError("a REJECTED_POSITION_PLAN carries exactly one rejection reason")


def build_position_plan(
    *,
    identity: DomainIdentity[PositionPlanId],
    trade_plan: TradePlan,
    sizing_context: PositionSizingContext,
    policy: SizingPolicy = DEFAULT_SIZING_POLICY,
) -> PositionPlan:
    """Construct one immutable `PositionPlan`, applying the full gate
    pipeline: source-approval check -> equity/risk-budget validity ->
    policy-percentage check -> risk-based quantity -> capital-based
    quantity -> final size.

    `trade_plan` must be the already-persisted, authoritative `TradePlan`
    record (see `usecases/build_position_plan.py`) -- this function
    performs no persistence lookup of its own, only pure computation,
    matching the `build_trade_plan()` (M059) precedent. It never trusts a
    caller-supplied entry/stop/risk-per-unit or approval status: every
    price value is read from `trade_plan.geometry` itself, and a
    `REJECTED_PLAN` source is rejected immediately, with no override.

    No `Bar`, `ObservationWindow`, or wall-clock parameter exists anywhere
    in this signature -- position sizing depends only on the frozen
    TradePlan and the caller's own sizing context, never on live or future
    market data (Phase 19).
    """

    def _plan(
        *,
        status: PositionPlanStatus,
        sizing: PositionSizing | None,
        reasons: tuple[PositionPlanRejectionReason, ...],
    ) -> PositionPlan:
        return PositionPlan(
            identity=identity,
            source_trade_plan_id=trade_plan.identity.governance_id,
            instrument=trade_plan.instrument,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_maximum_risk_percent=policy.maximum_risk_percent,
            policy_maximum_notional_percent=policy.maximum_notional_percent,
            policy_allow_fractional_shares=policy.allow_fractional_shares,
            supplied_account_equity=sizing_context.account_equity,
            supplied_risk_percent=sizing_context.risk_percent,
            status=status,
            sizing=sizing,
            reasons=reasons,
        )

    if trade_plan.status is not TradePlanStatus.APPROVED_PLAN:
        return _plan(
            status=PositionPlanStatus.REJECTED_POSITION_PLAN,
            sizing=None,
            reasons=(PositionPlanRejectionReason.SOURCE_PLAN_NOT_APPROVED,),
        )

    if sizing_context.account_equity <= 0:
        return _plan(
            status=PositionPlanStatus.REJECTED_POSITION_PLAN,
            sizing=None,
            reasons=(PositionPlanRejectionReason.INVALID_EQUITY,),
        )

    if sizing_context.risk_percent <= 0:
        return _plan(
            status=PositionPlanStatus.REJECTED_POSITION_PLAN,
            sizing=None,
            reasons=(PositionPlanRejectionReason.INVALID_RISK_BUDGET,),
        )

    if sizing_context.risk_percent > policy.maximum_risk_percent:
        return _plan(
            status=PositionPlanStatus.REJECTED_POSITION_PLAN,
            sizing=None,
            reasons=(PositionPlanRejectionReason.POLICY_VIOLATION,),
        )

    # trade_plan.status is APPROVED_PLAN, so geometry is guaranteed non-None
    # (TradePlan.__post_init__'s own M059 invariant).
    geometry = trade_plan.geometry
    assert geometry is not None  # noqa: S101

    allowed_risk_amount = sizing_context.account_equity * sizing_context.risk_percent
    maximum_notional = sizing_context.account_equity * policy.maximum_notional_percent
    risk_based_quantity = _floor_quantity(allowed_risk_amount, geometry.risk_per_unit)
    capital_based_quantity = _floor_quantity(maximum_notional, geometry.entry_price)

    if risk_based_quantity <= 0:
        sizing = PositionSizing(
            entry_price=geometry.entry_price,
            stop_price=geometry.stop_price,
            risk_per_unit=geometry.risk_per_unit,
            allowed_risk_amount=allowed_risk_amount,
            maximum_notional=maximum_notional,
            risk_based_quantity=risk_based_quantity,
            capital_based_quantity=capital_based_quantity,
            quantity=0,
            position_notional=Decimal(0),
            actual_risk=Decimal(0),
        )
        return _plan(
            status=PositionPlanStatus.REJECTED_POSITION_PLAN,
            sizing=sizing,
            reasons=(PositionPlanRejectionReason.ZERO_POSITION_SIZE,),
        )

    if capital_based_quantity <= 0:
        sizing = PositionSizing(
            entry_price=geometry.entry_price,
            stop_price=geometry.stop_price,
            risk_per_unit=geometry.risk_per_unit,
            allowed_risk_amount=allowed_risk_amount,
            maximum_notional=maximum_notional,
            risk_based_quantity=risk_based_quantity,
            capital_based_quantity=capital_based_quantity,
            quantity=0,
            position_notional=Decimal(0),
            actual_risk=Decimal(0),
        )
        return _plan(
            status=PositionPlanStatus.REJECTED_POSITION_PLAN,
            sizing=sizing,
            reasons=(PositionPlanRejectionReason.CAPITAL_LIMIT_EXCEEDED,),
        )

    quantity = min(risk_based_quantity, capital_based_quantity)
    position_notional = Decimal(quantity) * geometry.entry_price
    actual_risk = Decimal(quantity) * geometry.risk_per_unit
    sizing = PositionSizing(
        entry_price=geometry.entry_price,
        stop_price=geometry.stop_price,
        risk_per_unit=geometry.risk_per_unit,
        allowed_risk_amount=allowed_risk_amount,
        maximum_notional=maximum_notional,
        risk_based_quantity=risk_based_quantity,
        capital_based_quantity=capital_based_quantity,
        quantity=quantity,
        position_notional=position_notional,
        actual_risk=actual_risk,
    )
    return _plan(status=PositionPlanStatus.APPROVED_POSITION_PLAN, sizing=sizing, reasons=())
