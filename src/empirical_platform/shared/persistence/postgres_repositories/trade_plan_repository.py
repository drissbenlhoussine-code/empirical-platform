"""Concrete PostgreSQL `TradePlanRepository` adapter (MILESTONE-059).

Implements the `TradePlanRepository` Protocol against the `trade_plan`
table (MILESTONE-059 migration) directly -- no separate mapper module,
matching the M057 `PostgresDecisionCandidateRepository` and M058
`PostgresTradingOpportunityScanRepository` precedent: `TradePlan` is
immutable, single-insert, with no lifecycle and no transition history.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.trade_plan import (
    TradePlan,
    TradePlanGeometry,
    TradePlanRejectionReason,
    TradePlanStatus,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_AGGREGATE_KIND = "TradePlan"
_ROOT_UNIQUE_CONSTRAINTS = {"pk_trade_plan", "uq_trade_plan_governance_id"}


def _row_to_plan(row: Mapping[str, Any]) -> TradePlan:
    geometry: TradePlanGeometry | None = None
    if row["entry_price"] is not None:
        geometry = TradePlanGeometry(
            entry_price=cast(Decimal, row["entry_price"]),
            stop_price=cast(Decimal, row["stop_price"]),
            target_price=cast(Decimal, row["target_price"]),
            risk_per_unit=cast(Decimal, row["risk_per_unit"]),
            reward_per_unit=cast(Decimal, row["reward_per_unit"]),
            reward_risk_ratio=cast(Decimal, row["reward_risk_ratio"]),
        )
    return TradePlan(
        identity=DomainIdentity(
            governance_id=TradePlanId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        source_scan_id=TradingOpportunityScanId(str(row["source_scan_governance_id"])),
        source_decision_candidate_id=DecisionCandidateId(
            str(row["source_decision_candidate_governance_id"])
        ),
        target_evidence_package_id=EvidencePackageId(
            str(row["target_evidence_package_governance_id"])
        ),
        instrument=Instrument(str(row["instrument_symbol"])),
        evaluation_cutoff=cast(datetime, row["evaluation_cutoff"]),
        strategy_id=str(row["strategy_id"]),
        strategy_version=str(row["strategy_version"]),
        ranking_model_id=str(row["ranking_model_id"]),
        ranking_model_version=str(row["ranking_model_version"]),
        policy_id=str(row["policy_id"]),
        policy_version=str(row["policy_version"]),
        status=TradePlanStatus(row["status"]),
        geometry=geometry,
        reasons=tuple(TradePlanRejectionReason(reason) for reason in row["reasons"]),
    )


class PostgresTradePlanRepository:
    """Concrete, storage-aware `TradePlanRepository` implementation."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, identity: DomainIdentity[TradePlanId]) -> TradePlan:
        """Load a TradePlan by canonical identity."""
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM trade_plan "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=identity)
            plan = _row_to_plan(rows[0])
        return plan

    def add(self, plan: TradePlan) -> None:
        """Persist a new TradePlan that must not already exist."""
        identity = plan.identity
        geometry = plan.geometry
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    "INSERT INTO trade_plan "
                    "(runtime_id, governance_id, source_scan_governance_id, "
                    "source_decision_candidate_governance_id, "
                    "target_evidence_package_governance_id, instrument_symbol, "
                    "evaluation_cutoff, strategy_id, strategy_version, "
                    "ranking_model_id, ranking_model_version, policy_id, policy_version, "
                    "status, reasons, entry_price, stop_price, target_price, "
                    "risk_per_unit, reward_per_unit, reward_risk_ratio) "
                    "VALUES (:runtime_id, :governance_id, :source_scan_governance_id, "
                    ":source_decision_candidate_governance_id, "
                    ":target_evidence_package_governance_id, :instrument_symbol, "
                    ":evaluation_cutoff, :strategy_id, :strategy_version, "
                    ":ranking_model_id, :ranking_model_version, :policy_id, :policy_version, "
                    ":status, :reasons, :entry_price, :stop_price, :target_price, "
                    ":risk_per_unit, :reward_per_unit, :reward_risk_ratio)",
                    {
                        "runtime_id": str(identity.runtime_id),
                        "governance_id": str(identity.governance_id),
                        "source_scan_governance_id": str(plan.source_scan_id),
                        "source_decision_candidate_governance_id": str(
                            plan.source_decision_candidate_id
                        ),
                        "target_evidence_package_governance_id": str(
                            plan.target_evidence_package_id
                        ),
                        "instrument_symbol": str(plan.instrument),
                        "evaluation_cutoff": plan.evaluation_cutoff,
                        "strategy_id": plan.strategy_id,
                        "strategy_version": plan.strategy_version,
                        "ranking_model_id": plan.ranking_model_id,
                        "ranking_model_version": plan.ranking_model_version,
                        "policy_id": plan.policy_id,
                        "policy_version": plan.policy_version,
                        "status": plan.status.value,
                        "reasons": [reason.value for reason in plan.reasons],
                        "entry_price": geometry.entry_price if geometry else None,
                        "stop_price": geometry.stop_price if geometry else None,
                        "target_price": geometry.target_price if geometry else None,
                        "risk_per_unit": geometry.risk_per_unit if geometry else None,
                        "reward_per_unit": geometry.reward_per_unit if geometry else None,
                        "reward_risk_ratio": geometry.reward_risk_ratio if geometry else None,
                    },
                )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _ROOT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_AGGREGATE_KIND, identity=identity
                    ) from exc
                raise
