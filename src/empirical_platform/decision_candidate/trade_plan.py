"""Risk-gated trade plan: is a ranked LONG_CANDIDATE actually a trade worth
taking?

MILESTONE-059. Answers the question M057/M058 deliberately left open: a
positive `LONG_CANDIDATE` decision (M057) and a high ranking score (M058)
describe how strong an *opportunity* looks -- neither says whether the
resulting trade *geometry* (entry, protective stop, target, and the
resulting reward/risk ratio) is acceptable under an explicit, versioned
risk policy. This module computes that geometry and gates it: every
`TradePlan` is either `APPROVED_PLAN` or `REJECTED_PLAN`, never a naked
boolean, and a `NO_TRADE` source can never become an `APPROVED_PLAN`.

No live brokerage order is placed anywhere in this module or the usecases
built on it. THIS MODULE DOES NOT CLAIM AN APPROVED_PLAN IS PROFITABLE --
it only proves the trade's risk geometry satisfies one explicit, versioned
policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.scan import TradingOpportunityScan
from empirical_platform.decision_candidate.strategy import TradingDecision
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradePlanId,
    TradingOpportunityScanId,
)

RISK_POLICY_ID = "REFERENCE_HIGH_BREAKOUT_RISK_GATE"
RISK_POLICY_VERSION = "1"


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """One explicit, versioned risk policy.

    **This is a first product contract, not historical or industry
    authority.** No frozen numeric risk policy existed anywhere in this
    repository before M059 (see MILESTONE_059 scope Section 2) -- these
    parameters are M059's own origination, transparently labeled as such,
    not a rediscovered prior rule.

    `target_projection_percent` defines the target price as this fraction
    above the M057 strategy's own `reference_high` (the breakout level),
    independent of the entry price's own premium over that level -- see
    `compute_target_price()`. `minimum_reward_risk_ratio` is the inclusive
    (`>=`) threshold a plan's reward/risk ratio must clear to be approved.
    """

    policy_id: str = RISK_POLICY_ID
    policy_version: str = RISK_POLICY_VERSION
    target_projection_percent: Decimal = Decimal("0.02")
    minimum_reward_risk_ratio: Decimal = Decimal("2.0")

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if self.target_projection_percent <= 0:
            raise ValueError("target_projection_percent must be positive")
        if self.minimum_reward_risk_ratio <= 0:
            raise ValueError("minimum_reward_risk_ratio must be positive")


DEFAULT_RISK_POLICY = RiskPolicy()


class TradePlanStatus(StrEnum):
    """Closed decision vocabulary. Never a naked boolean."""

    APPROVED_PLAN = "APPROVED_PLAN"
    REJECTED_PLAN = "REJECTED_PLAN"


class TradePlanRejectionReason(StrEnum):
    """Machine-readable reason codes. Only reasons the implementation can
    actually produce are listed here."""

    SOURCE_NOT_LONG_CANDIDATE = "SOURCE_NOT_LONG_CANDIDATE"
    PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"
    INVALID_STOP_GEOMETRY = "INVALID_STOP_GEOMETRY"
    INVALID_TARGET_GEOMETRY = "INVALID_TARGET_GEOMETRY"
    REWARD_RISK_BELOW_MINIMUM = "REWARD_RISK_BELOW_MINIMUM"


@dataclass(frozen=True, slots=True)
class TradePlanGeometry:
    """The exact, self-explaining trade geometry a plan decision was
    computed from. Only ever constructed for geometrically valid
    (entry > stop, target > entry) inputs -- see `build_geometry()`."""

    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    risk_per_unit: Decimal
    reward_per_unit: Decimal
    reward_risk_ratio: Decimal

    def __post_init__(self) -> None:
        for field_name in (
            "entry_price",
            "stop_price",
            "target_price",
            "risk_per_unit",
            "reward_per_unit",
            "reward_risk_ratio",
        ):
            if not isinstance(getattr(self, field_name), Decimal):
                raise TypeError(f"{field_name} must be a Decimal")
        if self.risk_per_unit <= 0:
            raise ValueError("risk_per_unit must be positive")
        if self.reward_per_unit <= 0:
            raise ValueError("reward_per_unit must be positive")
        if self.stop_price >= self.entry_price:
            raise ValueError("stop_price must be strictly below entry_price")
        if self.target_price <= self.entry_price:
            raise ValueError("target_price must be strictly above entry_price")


def compute_stop_price(reference_high: Decimal) -> Decimal:
    """The protective stop / invalidation level: the M057 strategy's own
    breakout reference high.

    Deterministic, reproducible from data already available at the
    DecisionCandidate's own evaluation cutoff (no new data source), and
    strategy-coherent: the LONG_CANDIDATE thesis is that price broke above
    `reference_high`; a close back at or below it falsifies that thesis.
    Requires no raw bars or reference-window low -- only the already-
    persisted `EvaluationMeasurements.reference_high`.
    """
    return reference_high


def compute_target_price(reference_high: Decimal, policy: RiskPolicy) -> Decimal:
    """The target/exit objective: a fixed percentage above the breakout
    level, independent of the entry price's own premium over that level.

    Deliberately NOT a fixed multiple of `risk_per_unit` -- that pairing
    would make the reward/risk ratio a constant by construction (always
    exactly the chosen multiple), making the minimum-ratio gate incapable
    of ever failing on real data. Projecting from `reference_high` instead
    means reward/risk falls as the entry's premium over the breakout level
    grows -- an extended, already-run breakout produces worse geometry
    than a tight one, a genuine, data-dependent property, not a claim of
    profitability.
    """
    return reference_high * (1 + policy.target_projection_percent)


def build_geometry(
    *, entry_price: Decimal, stop_price: Decimal, target_price: Decimal
) -> TradePlanGeometry | TradePlanRejectionReason:
    """Validate and assemble trade geometry, or return the rejection reason.

    Pure, adversarially testable independent of any DecisionCandidate --
    the geometry-validity questions ("is stop below entry", "is target
    above entry") are meaningful for any (entry, stop, target) triple.
    """
    if stop_price >= entry_price:
        return TradePlanRejectionReason.INVALID_STOP_GEOMETRY
    if target_price <= entry_price:
        return TradePlanRejectionReason.INVALID_TARGET_GEOMETRY
    risk_per_unit = entry_price - stop_price
    reward_per_unit = target_price - entry_price
    reward_risk_ratio = reward_per_unit / risk_per_unit
    return TradePlanGeometry(
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        risk_per_unit=risk_per_unit,
        reward_per_unit=reward_per_unit,
        reward_risk_ratio=reward_risk_ratio,
    )


@dataclass(frozen=True, slots=True)
class TradePlan:
    """One immutable, persisted, independently-auditable risk-gated trade
    plan decision -- APPROVED_PLAN or REJECTED_PLAN, never a naked boolean.

    Like `DecisionCandidate` (M057) and `TradingOpportunityScan` (M058),
    deliberately NOT a lifecycle aggregate: a plan decision is a fact
    computed once from a fixed, already-persisted source
    (`DecisionCandidate` + `TradingOpportunityScan` + `RiskPolicy`) and
    never mutated afterward. If market conditions change, a NEW evaluation
    -> scan -> plan is built; the old plan is never revised.
    """

    identity: DomainIdentity[TradePlanId]
    source_scan_id: TradingOpportunityScanId
    source_decision_candidate_id: DecisionCandidateId
    target_evidence_package_id: EvidencePackageId
    instrument: Instrument
    evaluation_cutoff: datetime
    strategy_id: str
    strategy_version: str
    ranking_model_id: str
    ranking_model_version: str
    policy_id: str
    policy_version: str
    status: TradePlanStatus
    geometry: TradePlanGeometry | None
    reasons: tuple[TradePlanRejectionReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[TradePlanId]")
        if not isinstance(self.identity.governance_id, TradePlanId):
            raise TypeError("identity governance_id must be a TradePlanId")
        if not isinstance(self.target_evidence_package_id, EvidencePackageId):
            raise TypeError("target_evidence_package_id must be an EvidencePackageId")
        if not isinstance(self.evaluation_cutoff, datetime):
            raise TypeError("evaluation_cutoff must be a datetime")
        if self.evaluation_cutoff.tzinfo is None:
            raise ValueError("evaluation_cutoff must be timezone-aware")
        for field_name in (
            "strategy_id",
            "strategy_version",
            "ranking_model_id",
            "ranking_model_version",
            "policy_id",
            "policy_version",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")

        is_approved = self.status is TradePlanStatus.APPROVED_PLAN
        if is_approved:
            if self.geometry is None:
                raise ValueError("an APPROVED_PLAN must carry geometry")
            if self.reasons:
                raise ValueError("an APPROVED_PLAN must carry no rejection reasons")
        else:
            if not self.reasons:
                raise ValueError("a REJECTED_PLAN must carry at least one rejection reason")
            if len(self.reasons) != 1:
                raise ValueError("a REJECTED_PLAN carries exactly one rejection reason")


def _candidate_belongs_to_scan(
    *, scan: TradingOpportunityScan, candidate: DecisionCandidate
) -> bool:
    """Whether `candidate`'s own governance_id genuinely appears among
    `scan`'s own persisted evaluations -- the one provenance fact a caller
    could otherwise defeat by supplying two independently-valid but
    unrelated identities (see MILESTONE_059 scope Section 12, Phase 20)."""
    return any(
        entry.decision_candidate_id == candidate.identity.governance_id
        for entry in scan.evaluations
    )


def build_trade_plan(
    *,
    identity: DomainIdentity[TradePlanId],
    scan: TradingOpportunityScan,
    candidate: DecisionCandidate,
    target_evidence_package_id: EvidencePackageId,
    policy: RiskPolicy = DEFAULT_RISK_POLICY,
) -> TradePlan:
    """Construct one immutable `TradePlan`, applying the full gate pipeline:
    provenance check -> source-decision check -> stop/target geometry ->
    risk-policy threshold.

    `scan` and `candidate` must be the already-persisted, authoritative
    `TradingOpportunityScan`/`DecisionCandidate` records (see
    `usecases/build_trade_plan.py`) -- this function performs no
    persistence lookup of its own, only pure computation, matching the
    `build_scan()` (M058) precedent. It never trusts caller-supplied
    measurements, decision, or scan/strategy/ranking metadata: every field
    on the resulting plan is read from `scan`/`candidate` themselves.
    """

    def _plan(
        *,
        status: TradePlanStatus,
        geometry: TradePlanGeometry | None,
        reasons: tuple[TradePlanRejectionReason, ...],
    ) -> TradePlan:
        return TradePlan(
            identity=identity,
            source_scan_id=scan.identity.governance_id,
            source_decision_candidate_id=candidate.identity.governance_id,
            target_evidence_package_id=target_evidence_package_id,
            instrument=candidate.instrument,
            evaluation_cutoff=candidate.evaluation_timestamp,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            ranking_model_id=scan.ranking_model_id,
            ranking_model_version=scan.ranking_model_version,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            status=status,
            geometry=geometry,
            reasons=reasons,
        )

    if not _candidate_belongs_to_scan(scan=scan, candidate=candidate):
        return _plan(
            status=TradePlanStatus.REJECTED_PLAN,
            geometry=None,
            reasons=(TradePlanRejectionReason.PROVENANCE_MISMATCH,),
        )

    if candidate.outcome.decision is not TradingDecision.LONG_CANDIDATE:
        return _plan(
            status=TradePlanStatus.REJECTED_PLAN,
            geometry=None,
            reasons=(TradePlanRejectionReason.SOURCE_NOT_LONG_CANDIDATE,),
        )

    measurements = candidate.outcome.measurements
    stop_price = compute_stop_price(measurements.reference_high)
    target_price = compute_target_price(measurements.reference_high, policy)
    result = build_geometry(
        entry_price=measurements.current_close,
        stop_price=stop_price,
        target_price=target_price,
    )
    if isinstance(result, TradePlanRejectionReason):
        return _plan(status=TradePlanStatus.REJECTED_PLAN, geometry=None, reasons=(result,))

    geometry = result
    if geometry.reward_risk_ratio < policy.minimum_reward_risk_ratio:
        return _plan(
            status=TradePlanStatus.REJECTED_PLAN,
            geometry=geometry,
            reasons=(TradePlanRejectionReason.REWARD_RISK_BELOW_MINIMUM,),
        )

    return _plan(status=TradePlanStatus.APPROVED_PLAN, geometry=geometry, reasons=())
