"""Concrete PostgreSQL `DecisionCandidateRepository` adapter (MILESTONE-057).

Implements the `DecisionCandidateRepository` Protocol against the
`decision_candidate` table (MILESTONE-057 migration) directly -- there is no
separate mapper module, matching this milestone's own deliberate
simplification: `DecisionCandidate` is an immutable, single-insert record
with no lifecycle, no `save()`, and no transition history, so the full
`Mapper`/`_reconstruction` machinery used by the four lifecycle aggregates
would be pure ceremony here.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.decision_candidate.strategy import (
    EvaluationMeasurements,
    EvaluationOutcome,
    EvaluationReasonCode,
    TradingDecision,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import DecisionCandidateId, EvidencePackageId
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_AGGREGATE_KIND = "DecisionCandidate"
_ROOT_UNIQUE_CONSTRAINTS = {"pk_decision_candidate", "uq_decision_candidate_governance_id"}


def _row_to_candidate(row: Mapping[str, Any]) -> DecisionCandidate:
    measurements = EvaluationMeasurements(
        current_close=cast(Decimal, row["current_close"]),
        current_volume=cast(int, row["current_volume"]),
        reference_high=cast(Decimal, row["reference_high"]),
        reference_average_volume=cast(Decimal, row["reference_average_volume"]),
    )
    outcome = EvaluationOutcome(
        decision=TradingDecision(row["decision"]),
        reasons=tuple(EvaluationReasonCode(reason) for reason in row["reasons"]),
        measurements=measurements,
    )
    return DecisionCandidate(
        identity=DomainIdentity(
            governance_id=DecisionCandidateId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        target_evidence_package_id=EvidencePackageId(
            str(row["target_evidence_package_governance_id"])
        ),
        instrument=Instrument(str(row["instrument_symbol"])),
        interval=BarInterval(row["bar_interval"]),
        evaluation_timestamp=row["evaluation_timestamp"],
        strategy_id=str(row["strategy_id"]),
        strategy_version=str(row["strategy_version"]),
        reference_window_size=cast(int, row["reference_window_size"]),
        outcome=outcome,
    )


class PostgresDecisionCandidateRepository:
    """Concrete, storage-aware `DecisionCandidateRepository` implementation."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, identity: DomainIdentity[DecisionCandidateId]) -> DecisionCandidate:
        """Load a DecisionCandidate by canonical identity."""
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM decision_candidate "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=identity)
            candidate = _row_to_candidate(rows[0])
        return candidate

    def add(self, candidate: DecisionCandidate) -> None:
        """Persist a new DecisionCandidate that must not already exist."""
        identity = candidate.identity
        outcome = candidate.outcome
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    "INSERT INTO decision_candidate "
                    "(runtime_id, governance_id, target_evidence_package_governance_id, "
                    "instrument_symbol, bar_interval, evaluation_timestamp, strategy_id, "
                    "strategy_version, reference_window_size, decision, reasons, "
                    "current_close, current_volume, reference_high, reference_average_volume) "
                    "VALUES (:runtime_id, :governance_id, :target_evidence_package_governance_id, "
                    ":instrument_symbol, :bar_interval, :evaluation_timestamp, :strategy_id, "
                    ":strategy_version, :reference_window_size, :decision, :reasons, "
                    ":current_close, :current_volume, :reference_high, :reference_average_volume)",
                    {
                        "runtime_id": str(identity.runtime_id),
                        "governance_id": str(identity.governance_id),
                        "target_evidence_package_governance_id": str(
                            candidate.target_evidence_package_id
                        ),
                        "instrument_symbol": str(candidate.instrument),
                        "bar_interval": candidate.interval.value,
                        "evaluation_timestamp": candidate.evaluation_timestamp,
                        "strategy_id": candidate.strategy_id,
                        "strategy_version": candidate.strategy_version,
                        "reference_window_size": candidate.reference_window_size,
                        "decision": outcome.decision.value,
                        "reasons": [reason.value for reason in outcome.reasons],
                        "current_close": outcome.measurements.current_close,
                        "current_volume": outcome.measurements.current_volume,
                        "reference_high": outcome.measurements.reference_high,
                        "reference_average_volume": outcome.measurements.reference_average_volume,
                    },
                )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _ROOT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_AGGREGATE_KIND, identity=identity
                    ) from exc
                raise
