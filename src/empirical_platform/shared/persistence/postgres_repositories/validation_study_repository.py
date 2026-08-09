"""Concrete PostgreSQL repository for M062 historical validation studies."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.decision_candidate.validation_study import (
    HistoricalValidationStudy,
    HistoricalValidationStudyClassification,
    HistoricalValidationStudyStatus,
    ValidationSegment,
    ValidationSegmentResult,
    ValidationSegmentRole,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, DatasetId, ValidationStudyId
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_AGGREGATE_KIND = "HistoricalValidationStudy"
_ROOT_UNIQUE_CONSTRAINTS = {
    "pk_validation_study",
    "uq_validation_study_governance_id",
}


def _row_to_segment_result(row: Mapping[str, Any]) -> ValidationSegmentResult:
    segment = ValidationSegment(
        segment_id=str(row["segment_id"]),
        role=ValidationSegmentRole(str(row["role"])),
        data_start_timestamp=row["data_start_timestamp"],
        data_end_timestamp=row["data_end_timestamp"],
        scoring_start_timestamp=row["scoring_start_timestamp"],
        scoring_end_timestamp=row["scoring_end_timestamp"],
        warmup_bar_count=int(row["warmup_bar_count"]),
        scoring_bar_count=int(row["scoring_bar_count"]),
        buffer_bar_count=int(row["buffer_bar_count"]),
    )
    return ValidationSegmentResult(
        segment=segment,
        backtest_run_id=BacktestRunId(str(row["backtest_run_governance_id"])),
        backtest_run_runtime_id=RuntimeIdentifier(str(row["backtest_run_runtime_id"])),
        evaluated_cutoff_count=int(row["evaluated_cutoff_count"]),
        simulated_trade_count=int(row["simulated_trade_count"]),
        executed_trade_count=int(row["executed_trade_count"]),
        win_count=int(row["win_count"]),
        loss_count=int(row["loss_count"]),
        time_exit_count=int(row["time_exit_count"]),
        no_entry_count=int(row["no_entry_count"]),
        gross_pnl=cast(Decimal, row["gross_pnl"]),
        net_pnl=cast(Decimal, row["net_pnl"]),
        average_net_pnl=cast(Decimal | None, row["average_net_pnl"]),
        average_r=cast(Decimal | None, row["average_r"]),
        total_r=cast(Decimal, row["total_r"]),
        win_rate=cast(Decimal | None, row["win_rate"]),
        profit_factor=cast(Decimal | None, row["profit_factor"]),
        maximum_realized_pnl_drawdown=cast(Decimal | None, row["maximum_realized_pnl_drawdown"]),
    )


def _row_to_study(
    row: Mapping[str, Any],
    segments_by_role: Mapping[ValidationSegmentRole, ValidationSegmentResult],
) -> HistoricalValidationStudy:
    development = segments_by_role[ValidationSegmentRole.DEVELOPMENT_REFERENCE]
    holdout_1 = segments_by_role[ValidationSegmentRole.HOLDOUT_1]
    holdout_2 = segments_by_role[ValidationSegmentRole.HOLDOUT_2]
    return HistoricalValidationStudy(
        identity=DomainIdentity(
            governance_id=ValidationStudyId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        dataset_bundle_id=DatasetId(str(row["dataset_bundle_id"])),
        dataset_bundle_version=str(row["dataset_bundle_version"]),
        dataset_bundle_sha256=str(row["dataset_bundle_sha256"]),
        dataset_source_kind=str(row["dataset_source_kind"]),
        interval=BarInterval(str(row["bar_interval"])),
        instrument_universe=tuple(Instrument(symbol) for symbol in row["instrument_universe"]),
        reference_window_size=int(row["reference_window_size"]),
        strategy_id=str(row["strategy_id"]),
        strategy_version=str(row["strategy_version"]),
        ranking_model_id=str(row["ranking_model_id"]),
        ranking_model_version=str(row["ranking_model_version"]),
        risk_policy_id=str(row["risk_policy_id"]),
        risk_policy_version=str(row["risk_policy_version"]),
        sizing_policy_id=str(row["sizing_policy_id"]),
        sizing_policy_version=str(row["sizing_policy_version"]),
        execution_assumption_id=str(row["execution_assumption_id"]),
        execution_assumption_version=str(row["execution_assumption_version"]),
        outcome_model_id=str(row["outcome_model_id"]),
        outcome_model_version=str(row["outcome_model_version"]),
        cost_model_id=str(row["cost_model_id"]),
        cost_model_version=str(row["cost_model_version"]),
        holding_horizon_bars=int(row["holding_horizon_bars"]),
        supplied_account_equity=cast(Decimal, row["supplied_account_equity"]),
        supplied_risk_percent=cast(Decimal, row["supplied_risk_percent"]),
        survivorship_bias_disclosure=str(row["survivorship_bias_disclosure"]),
        status=HistoricalValidationStudyStatus(str(row["status"])),
        classification=HistoricalValidationStudyClassification(str(row["classification"])),
        development=development,
        holdout_1=holdout_1,
        holdout_2=holdout_2,
        holdout_1_net_pnl_delta=cast(Decimal, row["holdout_1_net_pnl_delta"]),
        holdout_1_total_r_delta=cast(Decimal, row["holdout_1_total_r_delta"]),
        holdout_2_net_pnl_delta=cast(Decimal, row["holdout_2_net_pnl_delta"]),
        holdout_2_total_r_delta=cast(Decimal, row["holdout_2_total_r_delta"]),
    )


class PostgresHistoricalValidationStudyRepository:
    """Concrete, storage-aware repository for immutable validation studies."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, identity: DomainIdentity[ValidationStudyId]) -> HistoricalValidationStudy:
        with self._service.unit_of_work() as work:
            study_rows = work.execute(
                "SELECT * FROM validation_study "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not study_rows:
                raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=identity)
            segment_rows = work.execute(
                "SELECT * FROM validation_segment WHERE study_runtime_id = :runtime_id",
                {"runtime_id": str(identity.runtime_id)},
            )
        segments_by_role = {
            ValidationSegmentRole(str(row["role"])): _row_to_segment_result(row)
            for row in segment_rows
        }
        return _row_to_study(study_rows[0], segments_by_role)

    def add(self, study: HistoricalValidationStudy) -> None:
        identity = study.identity
        study_insert_sql = (
            "INSERT INTO validation_study ("
            "runtime_id, governance_id, dataset_bundle_id, dataset_bundle_version, "
            "dataset_bundle_sha256, dataset_source_kind, bar_interval, instrument_universe, "
            "reference_window_size, strategy_id, strategy_version, ranking_model_id, "
            "ranking_model_version, risk_policy_id, risk_policy_version, sizing_policy_id, "
            "sizing_policy_version, execution_assumption_id, execution_assumption_version, "
            "outcome_model_id, outcome_model_version, cost_model_id, cost_model_version, "
            "holding_horizon_bars, supplied_account_equity, supplied_risk_percent, "
            "survivorship_bias_disclosure, status, classification, "
            "holdout_1_net_pnl_delta, holdout_1_total_r_delta, "
            "holdout_2_net_pnl_delta, holdout_2_total_r_delta"
            ") VALUES ("
            ":runtime_id, :governance_id, :dataset_bundle_id, :dataset_bundle_version, "
            ":dataset_bundle_sha256, :dataset_source_kind, :bar_interval, :instrument_universe, "
            ":reference_window_size, :strategy_id, :strategy_version, :ranking_model_id, "
            ":ranking_model_version, :risk_policy_id, :risk_policy_version, :sizing_policy_id, "
            ":sizing_policy_version, :execution_assumption_id, :execution_assumption_version, "
            ":outcome_model_id, :outcome_model_version, :cost_model_id, :cost_model_version, "
            ":holding_horizon_bars, :supplied_account_equity, :supplied_risk_percent, "
            ":survivorship_bias_disclosure, :status, :classification, "
            ":holdout_1_net_pnl_delta, :holdout_1_total_r_delta, "
            ":holdout_2_net_pnl_delta, :holdout_2_total_r_delta"
            ")"
        )
        segment_insert_sql = (
            "INSERT INTO validation_segment ("
            "study_runtime_id, segment_id, role, data_start_timestamp, data_end_timestamp, "
            "scoring_start_timestamp, scoring_end_timestamp, warmup_bar_count, "
            "scoring_bar_count, buffer_bar_count, backtest_run_governance_id, "
            "backtest_run_runtime_id, evaluated_cutoff_count, simulated_trade_count, "
            "executed_trade_count, win_count, loss_count, time_exit_count, no_entry_count, "
            "gross_pnl, net_pnl, average_net_pnl, average_r, total_r, win_rate, "
            "profit_factor, maximum_realized_pnl_drawdown"
            ") VALUES ("
            ":study_runtime_id, :segment_id, :role, :data_start_timestamp, :data_end_timestamp, "
            ":scoring_start_timestamp, :scoring_end_timestamp, :warmup_bar_count, "
            ":scoring_bar_count, :buffer_bar_count, :backtest_run_governance_id, "
            ":backtest_run_runtime_id, :evaluated_cutoff_count, :simulated_trade_count, "
            ":executed_trade_count, :win_count, :loss_count, :time_exit_count, :no_entry_count, "
            ":gross_pnl, :net_pnl, :average_net_pnl, :average_r, :total_r, :win_rate, "
            ":profit_factor, :maximum_realized_pnl_drawdown"
            ")"
        )
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    study_insert_sql,
                    {
                        "runtime_id": str(identity.runtime_id),
                        "governance_id": str(identity.governance_id),
                        "dataset_bundle_id": str(study.dataset_bundle_id),
                        "dataset_bundle_version": study.dataset_bundle_version,
                        "dataset_bundle_sha256": study.dataset_bundle_sha256,
                        "dataset_source_kind": study.dataset_source_kind,
                        "bar_interval": study.interval.value,
                        "instrument_universe": [
                            str(instrument) for instrument in study.instrument_universe
                        ],
                        "reference_window_size": study.reference_window_size,
                        "strategy_id": study.strategy_id,
                        "strategy_version": study.strategy_version,
                        "ranking_model_id": study.ranking_model_id,
                        "ranking_model_version": study.ranking_model_version,
                        "risk_policy_id": study.risk_policy_id,
                        "risk_policy_version": study.risk_policy_version,
                        "sizing_policy_id": study.sizing_policy_id,
                        "sizing_policy_version": study.sizing_policy_version,
                        "execution_assumption_id": study.execution_assumption_id,
                        "execution_assumption_version": study.execution_assumption_version,
                        "outcome_model_id": study.outcome_model_id,
                        "outcome_model_version": study.outcome_model_version,
                        "cost_model_id": study.cost_model_id,
                        "cost_model_version": study.cost_model_version,
                        "holding_horizon_bars": study.holding_horizon_bars,
                        "supplied_account_equity": study.supplied_account_equity,
                        "supplied_risk_percent": study.supplied_risk_percent,
                        "survivorship_bias_disclosure": study.survivorship_bias_disclosure,
                        "status": study.status.value,
                        "classification": study.classification.value,
                        "holdout_1_net_pnl_delta": study.holdout_1_net_pnl_delta,
                        "holdout_1_total_r_delta": study.holdout_1_total_r_delta,
                        "holdout_2_net_pnl_delta": study.holdout_2_net_pnl_delta,
                        "holdout_2_total_r_delta": study.holdout_2_total_r_delta,
                    },
                )
                for result in (study.development, study.holdout_1, study.holdout_2):
                    segment = result.segment
                    work.execute(
                        segment_insert_sql,
                        {
                            "study_runtime_id": str(identity.runtime_id),
                            "segment_id": segment.segment_id,
                            "role": segment.role.value,
                            "data_start_timestamp": segment.data_start_timestamp,
                            "data_end_timestamp": segment.data_end_timestamp,
                            "scoring_start_timestamp": segment.scoring_start_timestamp,
                            "scoring_end_timestamp": segment.scoring_end_timestamp,
                            "warmup_bar_count": segment.warmup_bar_count,
                            "scoring_bar_count": segment.scoring_bar_count,
                            "buffer_bar_count": segment.buffer_bar_count,
                            "backtest_run_governance_id": str(result.backtest_run_id),
                            "backtest_run_runtime_id": str(result.backtest_run_runtime_id),
                            "evaluated_cutoff_count": result.evaluated_cutoff_count,
                            "simulated_trade_count": result.simulated_trade_count,
                            "executed_trade_count": result.executed_trade_count,
                            "win_count": result.win_count,
                            "loss_count": result.loss_count,
                            "time_exit_count": result.time_exit_count,
                            "no_entry_count": result.no_entry_count,
                            "gross_pnl": result.gross_pnl,
                            "net_pnl": result.net_pnl,
                            "average_net_pnl": result.average_net_pnl,
                            "average_r": result.average_r,
                            "total_r": result.total_r,
                            "win_rate": result.win_rate,
                            "profit_factor": result.profit_factor,
                            "maximum_realized_pnl_drawdown": result.maximum_realized_pnl_drawdown,
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _ROOT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_AGGREGATE_KIND, identity=identity
                    ) from exc
                raise
