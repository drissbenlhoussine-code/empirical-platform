"""Concrete PostgreSQL `TradingOpportunityScanRepository` adapter (MILESTONE-058).

Implements the `TradingOpportunityScanRepository` Protocol against the
`trading_opportunity_scan`/`trading_opportunity_scan_evaluation` tables
(MILESTONE-058 migration) directly -- no separate mapper module, matching
the M057 `PostgresDecisionCandidateRepository` precedent: both records are
immutable, single-insert, with no lifecycle and no transition history.

`trading_opportunity_scan_evaluation` deliberately does not duplicate
`decision_candidate`'s own measurements/reasons columns -- `get()`
reconstructs each `ScanEvaluationEntry` by joining back to `decision_candidate`
at read time (see MILESTONE_058 scope Section 8).

`add()` persists the scan row and every evaluation row within one
`unit_of_work()` -- a genuine atomic transaction for the scan and its full
evaluation set. It does NOT additionally wrap the caller's own prior
`DecisionCandidateRepository.add()` calls (see
`usecases/run_trading_opportunity_scan.py` for that disclosed boundary).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.scan import ScanEvaluationEntry, TradingOpportunityScan
from empirical_platform.decision_candidate.strategy import (
    EvaluationMeasurements,
    EvaluationReasonCode,
    TradingDecision,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_AGGREGATE_KIND = "TradingOpportunityScan"
_ROOT_UNIQUE_CONSTRAINTS = {
    "pk_trading_opportunity_scan",
    "uq_trading_opportunity_scan_governance_id",
}


def _row_to_evaluation_entry(row: Mapping[str, Any]) -> ScanEvaluationEntry:
    measurements = EvaluationMeasurements(
        current_close=cast(Decimal, row["current_close"]),
        current_volume=cast(int, row["current_volume"]),
        reference_high=cast(Decimal, row["reference_high"]),
        reference_average_volume=cast(Decimal, row["reference_average_volume"]),
    )
    return ScanEvaluationEntry(
        instrument=Instrument(str(row["instrument_symbol"])),
        decision_candidate_id=DecisionCandidateId(str(row["decision_candidate_governance_id"])),
        decision=TradingDecision(row["decision"]),
        measurements=measurements,
        reasons=tuple(EvaluationReasonCode(reason) for reason in row["reasons"]),
        rank=cast("int | None", row["rank"]),
        score=cast("Decimal | None", row["score"]),
    )


class PostgresTradingOpportunityScanRepository:
    """Concrete, storage-aware `TradingOpportunityScanRepository` implementation."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, identity: DomainIdentity[TradingOpportunityScanId]) -> TradingOpportunityScan:
        """Load a TradingOpportunityScan by canonical identity, reconstructing
        every evaluation entry by joining back to `decision_candidate`."""
        with self._service.unit_of_work() as work:
            scan_rows = work.execute(
                "SELECT * FROM trading_opportunity_scan "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not scan_rows:
                raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=identity)
            scan_row = scan_rows[0]
            evaluation_rows = work.execute(
                "SELECT toe.position, toe.instrument_symbol, toe.decision_candidate_governance_id, "
                "toe.decision, toe.rank, toe.score, "
                "dc.current_close, dc.current_volume, dc.reference_high, "
                "dc.reference_average_volume, dc.reasons "
                "FROM trading_opportunity_scan_evaluation toe "
                "JOIN decision_candidate dc "
                "ON dc.governance_id = toe.decision_candidate_governance_id "
                "WHERE toe.scan_runtime_id = :scan_runtime_id "
                "ORDER BY toe.position",
                {"scan_runtime_id": str(identity.runtime_id)},
            )
        evaluations = tuple(_row_to_evaluation_entry(row) for row in evaluation_rows)
        return TradingOpportunityScan(
            identity=DomainIdentity(
                governance_id=TradingOpportunityScanId(str(scan_row["governance_id"])),
                runtime_id=RuntimeIdentifier(str(scan_row["runtime_id"])),
            ),
            target_evidence_package_id=EvidencePackageId(
                str(scan_row["target_evidence_package_governance_id"])
            ),
            strategy_id=str(scan_row["strategy_id"]),
            strategy_version=str(scan_row["strategy_version"]),
            ranking_model_id=str(scan_row["ranking_model_id"]),
            ranking_model_version=str(scan_row["ranking_model_version"]),
            evaluation_cutoff=cast(datetime, scan_row["evaluation_cutoff"]),
            evaluations=evaluations,
        )

    def add(self, scan: TradingOpportunityScan) -> None:
        """Persist a new TradingOpportunityScan and its full evaluation set,
        atomically, within one transaction."""
        identity = scan.identity
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    "INSERT INTO trading_opportunity_scan "
                    "(runtime_id, governance_id, target_evidence_package_governance_id, "
                    "strategy_id, strategy_version, ranking_model_id, ranking_model_version, "
                    "evaluation_cutoff) "
                    "VALUES (:runtime_id, :governance_id, :target_evidence_package_governance_id, "
                    ":strategy_id, :strategy_version, :ranking_model_id, :ranking_model_version, "
                    ":evaluation_cutoff)",
                    {
                        "runtime_id": str(identity.runtime_id),
                        "governance_id": str(identity.governance_id),
                        "target_evidence_package_governance_id": str(
                            scan.target_evidence_package_id
                        ),
                        "strategy_id": scan.strategy_id,
                        "strategy_version": scan.strategy_version,
                        "ranking_model_id": scan.ranking_model_id,
                        "ranking_model_version": scan.ranking_model_version,
                        "evaluation_cutoff": scan.evaluation_cutoff,
                    },
                )
                for position, entry in enumerate(scan.evaluations):
                    work.execute(
                        "INSERT INTO trading_opportunity_scan_evaluation "
                        "(scan_runtime_id, position, decision_candidate_governance_id, "
                        "instrument_symbol, decision, rank, score) "
                        "VALUES (:scan_runtime_id, :position, :decision_candidate_governance_id, "
                        ":instrument_symbol, :decision, :rank, :score)",
                        {
                            "scan_runtime_id": str(identity.runtime_id),
                            "position": position,
                            "decision_candidate_governance_id": str(entry.decision_candidate_id),
                            "instrument_symbol": str(entry.instrument),
                            "decision": entry.decision.value,
                            "rank": entry.rank,
                            "score": entry.score,
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _ROOT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_AGGREGATE_KIND, identity=identity
                    ) from exc
                raise
