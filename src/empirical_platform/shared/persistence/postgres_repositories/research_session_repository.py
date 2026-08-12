"""Concrete PostgreSQL repository for M070 daily research sessions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from empirical_platform.decision_candidate.research_session import (
    ResearchDecisionEntry,
    ResearchSession,
    ResearchSessionStatus,
    StageName,
    StageRecord,
    StageStatus,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_SESSION_KIND = "ResearchSession"
_SESSION_UNIQUE_CONSTRAINTS = {
    "pk_research_session",
    "uq_research_session_governance_id",
}


class PostgresResearchSessionRepository:
    """Concrete, storage-aware repository for immutable daily research
    sessions, persisted across `research_session`,
    `research_session_stage`, and `research_session_decision`."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, identity: DomainIdentity[ResearchSessionId]) -> ResearchSession:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM research_session "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                raise AggregateNotFound(aggregate_kind=_SESSION_KIND, identity=identity)
            stage_rows = work.execute(
                "SELECT * FROM research_session_stage "
                "WHERE session_runtime_id = :runtime_id ORDER BY stage_sequence",
                {"runtime_id": str(identity.runtime_id)},
            )
            decision_rows = work.execute(
                "SELECT * FROM research_session_decision "
                "WHERE session_runtime_id = :runtime_id ORDER BY decision_sequence",
                {"runtime_id": str(identity.runtime_id)},
            )
        return _row_to_session(rows[0], stage_rows, decision_rows)

    def add(self, session: ResearchSession) -> None:
        session_insert_sql = (
            "INSERT INTO research_session ("
            "runtime_id, governance_id, created_at, as_of, requested_universe, data_source, "
            "dataset_id, dataset_version, dataset_sha256, strategy_id, strategy_version, "
            "ranking_model_id, ranking_model_version, risk_policy_id, risk_policy_version, "
            "sizing_policy_id, sizing_policy_version, campaign_governance_id, "
            "run_governance_id, evidence_package_governance_id, scan_governance_id, status, "
            "failed_stage, failure_type, failure_message, completed_at, candidate_count, "
            "accepted_trade_plan_count, rejected_trade_plan_count, position_plan_count, "
            "backtest_run_governance_id, backtest_evaluated_opportunity_count, "
            "backtest_executed_trade_count, limitations"
            ") VALUES ("
            ":runtime_id, :governance_id, :created_at, :as_of, :requested_universe, "
            ":data_source, :dataset_id, :dataset_version, :dataset_sha256, :strategy_id, "
            ":strategy_version, :ranking_model_id, :ranking_model_version, :risk_policy_id, "
            ":risk_policy_version, :sizing_policy_id, :sizing_policy_version, "
            ":campaign_governance_id, :run_governance_id, :evidence_package_governance_id, "
            ":scan_governance_id, :status, :failed_stage, :failure_type, :failure_message, "
            ":completed_at, :candidate_count, :accepted_trade_plan_count, "
            ":rejected_trade_plan_count, :position_plan_count, :backtest_run_governance_id, "
            ":backtest_evaluated_opportunity_count, :backtest_executed_trade_count, :limitations"
            ")"
        )
        stage_insert_sql = (
            "INSERT INTO research_session_stage ("
            "session_runtime_id, stage_sequence, stage_name, stage_version, started_at, "
            "completed_at, status, input_authority, output_identity, error_type, error_message"
            ") VALUES ("
            ":session_runtime_id, :stage_sequence, :stage_name, :stage_version, :started_at, "
            ":completed_at, :status, :input_authority, :output_identity, :error_type, "
            ":error_message"
            ")"
        )
        decision_insert_sql = (
            "INSERT INTO research_session_decision ("
            "session_runtime_id, decision_sequence, rank, instrument_symbol, "
            "decision_candidate_governance_id, scan_decision, trade_plan_governance_id, "
            "trade_plan_decision, position_plan_governance_id"
            ") VALUES ("
            ":session_runtime_id, :decision_sequence, :rank, :instrument_symbol, "
            ":decision_candidate_governance_id, :scan_decision, :trade_plan_governance_id, "
            ":trade_plan_decision, :position_plan_governance_id"
            ")"
        )
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    session_insert_sql,
                    {
                        "runtime_id": str(session.identity.runtime_id),
                        "governance_id": str(session.identity.governance_id),
                        "created_at": session.created_at,
                        "as_of": session.as_of,
                        "requested_universe": list(session.requested_universe),
                        "data_source": session.data_source,
                        "dataset_id": session.dataset_id,
                        "dataset_version": session.dataset_version,
                        "dataset_sha256": session.dataset_sha256,
                        "strategy_id": session.strategy_id,
                        "strategy_version": session.strategy_version,
                        "ranking_model_id": session.ranking_model_id,
                        "ranking_model_version": session.ranking_model_version,
                        "risk_policy_id": session.risk_policy_id,
                        "risk_policy_version": session.risk_policy_version,
                        "sizing_policy_id": session.sizing_policy_id,
                        "sizing_policy_version": session.sizing_policy_version,
                        "campaign_governance_id": session.campaign_governance_id,
                        "run_governance_id": session.run_governance_id,
                        "evidence_package_governance_id": session.evidence_package_governance_id,
                        "scan_governance_id": session.scan_governance_id,
                        "status": session.status.value,
                        "failed_stage": (
                            session.failed_stage.value if session.failed_stage is not None else None
                        ),
                        "failure_type": session.failure_type,
                        "failure_message": session.failure_message,
                        "completed_at": session.completed_at,
                        "candidate_count": session.candidate_count,
                        "accepted_trade_plan_count": session.accepted_trade_plan_count,
                        "rejected_trade_plan_count": session.rejected_trade_plan_count,
                        "position_plan_count": session.position_plan_count,
                        "backtest_run_governance_id": session.backtest_run_governance_id,
                        "backtest_evaluated_opportunity_count": (
                            session.backtest_evaluated_opportunity_count
                        ),
                        "backtest_executed_trade_count": session.backtest_executed_trade_count,
                        "limitations": list(session.limitations),
                    },
                )
                for sequence, stage in enumerate(session.stage_manifest, start=1):
                    work.execute(
                        stage_insert_sql,
                        {
                            "session_runtime_id": str(session.identity.runtime_id),
                            "stage_sequence": sequence,
                            "stage_name": stage.stage_name.value,
                            "stage_version": stage.stage_version,
                            "started_at": stage.started_at,
                            "completed_at": stage.completed_at,
                            "status": stage.status.value,
                            "input_authority": stage.input_authority,
                            "output_identity": stage.output_identity,
                            "error_type": stage.error_type,
                            "error_message": stage.error_message,
                        },
                    )
                for sequence, decision in enumerate(session.decisions, start=1):
                    work.execute(
                        decision_insert_sql,
                        {
                            "session_runtime_id": str(session.identity.runtime_id),
                            "decision_sequence": sequence,
                            "rank": decision.rank,
                            "instrument_symbol": decision.instrument_symbol,
                            "decision_candidate_governance_id": (
                                decision.decision_candidate_governance_id
                            ),
                            "scan_decision": decision.scan_decision,
                            "trade_plan_governance_id": decision.trade_plan_governance_id,
                            "trade_plan_decision": decision.trade_plan_decision,
                            "position_plan_governance_id": decision.position_plan_governance_id,
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _SESSION_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_SESSION_KIND, identity=session.identity
                    ) from exc
                raise


def _row_to_stage(row: Mapping[str, Any]) -> StageRecord:
    return StageRecord(
        stage_name=StageName(str(row["stage_name"])),
        stage_version=cast("str | None", row["stage_version"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        status=StageStatus(str(row["status"])),
        input_authority=str(row["input_authority"]),
        output_identity=cast("str | None", row["output_identity"]),
        error_type=cast("str | None", row["error_type"]),
        error_message=cast("str | None", row["error_message"]),
    )


def _row_to_decision(row: Mapping[str, Any]) -> ResearchDecisionEntry:
    return ResearchDecisionEntry(
        rank=cast("int | None", row["rank"]),
        instrument_symbol=str(row["instrument_symbol"]),
        decision_candidate_governance_id=str(row["decision_candidate_governance_id"]),
        scan_decision=str(row["scan_decision"]),
        trade_plan_governance_id=cast("str | None", row["trade_plan_governance_id"]),
        trade_plan_decision=cast("str | None", row["trade_plan_decision"]),
        position_plan_governance_id=cast("str | None", row["position_plan_governance_id"]),
    )


def _row_to_session(
    row: Mapping[str, Any],
    stage_rows: Sequence[Mapping[str, Any]],
    decision_rows: Sequence[Mapping[str, Any]],
) -> ResearchSession:
    failed_stage = row["failed_stage"]
    return ResearchSession(
        identity=DomainIdentity(
            governance_id=ResearchSessionId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        created_at=row["created_at"],
        as_of=row["as_of"],
        requested_universe=tuple(row["requested_universe"]),
        data_source=str(row["data_source"]),
        dataset_id=cast("str | None", row["dataset_id"]),
        dataset_version=cast("str | None", row["dataset_version"]),
        dataset_sha256=cast("str | None", row["dataset_sha256"]),
        strategy_id=cast("str | None", row["strategy_id"]),
        strategy_version=cast("str | None", row["strategy_version"]),
        ranking_model_id=cast("str | None", row["ranking_model_id"]),
        ranking_model_version=cast("str | None", row["ranking_model_version"]),
        risk_policy_id=cast("str | None", row["risk_policy_id"]),
        risk_policy_version=cast("str | None", row["risk_policy_version"]),
        sizing_policy_id=cast("str | None", row["sizing_policy_id"]),
        sizing_policy_version=cast("str | None", row["sizing_policy_version"]),
        campaign_governance_id=str(row["campaign_governance_id"]),
        run_governance_id=str(row["run_governance_id"]),
        evidence_package_governance_id=str(row["evidence_package_governance_id"]),
        scan_governance_id=cast("str | None", row["scan_governance_id"]),
        status=ResearchSessionStatus(str(row["status"])),
        failed_stage=StageName(str(failed_stage)) if failed_stage is not None else None,
        failure_type=cast("str | None", row["failure_type"]),
        failure_message=cast("str | None", row["failure_message"]),
        completed_at=row["completed_at"],
        stage_manifest=tuple(_row_to_stage(r) for r in stage_rows),
        decisions=tuple(_row_to_decision(r) for r in decision_rows),
        candidate_count=int(row["candidate_count"]),
        accepted_trade_plan_count=int(row["accepted_trade_plan_count"]),
        rejected_trade_plan_count=int(row["rejected_trade_plan_count"]),
        position_plan_count=int(row["position_plan_count"]),
        backtest_run_governance_id=cast("str | None", row["backtest_run_governance_id"]),
        backtest_evaluated_opportunity_count=cast(
            "int | None", row["backtest_evaluated_opportunity_count"]
        ),
        backtest_executed_trade_count=cast("int | None", row["backtest_executed_trade_count"]),
        limitations=tuple(row["limitations"]),
    )
