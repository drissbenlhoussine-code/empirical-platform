"""Concrete PostgreSQL repository for M064 survivorship-aware robustness
studies, plus the instrument-master / universe-authority / membership-record
tables the study's own windows reference for audit.

Full per-trade detail for every canonical window remains reachable through
the unmodified M061 repository; the diagnostic `CURRENT_UNIVERSE_BIAS_STRESS`
study itself remains reachable through the unmodified M063
`robustness_study` repository -- this module never duplicates either.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.instrument_master import InstrumentId, InstrumentMaster
from empirical_platform.decision_candidate.membership import MembershipManifest, MembershipStatus
from empirical_platform.decision_candidate.robustness_study import RegimeLabel, WindowExtreme
from empirical_platform.decision_candidate.survivorship_study import (
    BiasStressComparison,
    CurrentUniverseBiasStressResult,
    SurvivorshipAwareRobustnessStudy,
    SurvivorshipClassification,
    SurvivorshipStudyStatus,
    SurvivorshipWindowResult,
    WindowUniverseSnapshot,
)
from empirical_platform.decision_candidate.universe_authority import UniverseAuthority
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    BacktestRunId,
    DatasetId,
    RobustnessStudyId,
    SurvivorshipStudyId,
)
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_AGGREGATE_KIND = "SurvivorshipAwareRobustnessStudy"
_ROOT_UNIQUE_CONSTRAINTS = {
    "pk_survivorship_study",
    "uq_survivorship_study_governance_id",
}


def _row_to_window_result(
    row: Mapping[str, Any],
    *,
    universe_id: str,
    universe_version: str,
    membership_manifest_hash: str,
) -> SurvivorshipWindowResult:
    backtest_run_governance_id = row["backtest_run_governance_id"]
    backtest_run_runtime_id = row["backtest_run_runtime_id"]
    snapshot = WindowUniverseSnapshot(
        window_id=str(row["window_id"]),
        sequence_index=int(row["sequence_index"]),
        universe_id=universe_id,
        universe_version=universe_version,
        membership_manifest_hash=membership_manifest_hash,
        eligible_instrument_ids=tuple(
            InstrumentId(value) for value in row["eligible_instrument_ids"]
        ),
        evaluated_instrument_ids=tuple(
            InstrumentId(value) for value in row["evaluated_instrument_ids"]
        ),
        missing_data_excluded_instrument_ids=tuple(
            InstrumentId(value) for value in row["missing_data_excluded_instrument_ids"]
        ),
    )
    return SurvivorshipWindowResult(
        snapshot=snapshot,
        data_start_timestamp=row["data_start_timestamp"],
        data_end_timestamp=row["data_end_timestamp"],
        scoring_start_timestamp=row["scoring_start_timestamp"],
        scoring_end_timestamp=row["scoring_end_timestamp"],
        backtest_run_id=(
            BacktestRunId(str(backtest_run_governance_id))
            if backtest_run_governance_id is not None
            else None
        ),
        backtest_run_runtime_id=(
            RuntimeIdentifier(str(backtest_run_runtime_id))
            if backtest_run_runtime_id is not None
            else None
        ),
        regime_label=RegimeLabel(str(row["regime_label"])),
        realized_volatility=cast(Decimal, row["realized_volatility"]),
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
    row: Mapping[str, Any], window_results: tuple[SurvivorshipWindowResult, ...]
) -> SurvivorshipAwareRobustnessStudy:
    bias_stress = CurrentUniverseBiasStressResult(
        stress_study_id=RobustnessStudyId(str(row["stress_study_governance_id"])),
        comparison=BiasStressComparison(str(row["stress_comparison"])),
        full_universe_size=int(row["stress_full_universe_size"]),
        canonical_total_executed_trade_count=int(
            row["stress_canonical_total_executed_trade_count"]
        ),
        stress_total_executed_trade_count=int(row["stress_total_executed_trade_count"]),
        canonical_net_pnl_total=cast(Decimal, row["stress_canonical_net_pnl_total"]),
        stress_net_pnl_total=cast(Decimal, row["stress_net_pnl_total"]),
        canonical_total_r_total=cast(Decimal, row["stress_canonical_total_r_total"]),
        stress_total_r_total=cast(Decimal, row["stress_total_r_total"]),
        canonical_best_window_by_net_pnl=WindowExtreme(
            window_id=str(row["stress_canonical_best_window_by_net_pnl_id"]),
            value=cast(Decimal, row["stress_canonical_best_window_by_net_pnl_value"]),
        ),
        stress_best_window_by_net_pnl=WindowExtreme(
            window_id=str(row["stress_best_window_by_net_pnl_id"]),
            value=cast(Decimal, row["stress_best_window_by_net_pnl_value"]),
        ),
        canonical_worst_window_by_net_pnl=WindowExtreme(
            window_id=str(row["stress_canonical_worst_window_by_net_pnl_id"]),
            value=cast(Decimal, row["stress_canonical_worst_window_by_net_pnl_value"]),
        ),
        stress_worst_window_by_net_pnl=WindowExtreme(
            window_id=str(row["stress_worst_window_by_net_pnl_id"]),
            value=cast(Decimal, row["stress_worst_window_by_net_pnl_value"]),
        ),
    )
    return SurvivorshipAwareRobustnessStudy(
        identity=DomainIdentity(
            governance_id=SurvivorshipStudyId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        dataset_bundle_id=DatasetId(str(row["dataset_bundle_id"])),
        dataset_bundle_version=str(row["dataset_bundle_version"]),
        dataset_bundle_sha256=str(row["dataset_bundle_sha256"]),
        dataset_source_kind=str(row["dataset_source_kind"]),
        universe_id=str(row["universe_id"]),
        universe_version=str(row["universe_version"]),
        universe_membership_model=str(row["universe_membership_model"]),
        membership_manifest_hash=str(row["membership_manifest_hash"]),
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
        regime_policy_id=str(row["regime_policy_id"]),
        regime_policy_version=str(row["regime_policy_version"]),
        corporate_action_handling=str(row["corporate_action_handling"]),
        status=SurvivorshipStudyStatus(str(row["status"])),
        classification=SurvivorshipClassification(str(row["classification"])),
        window_results=window_results,
        window_count=int(row["window_count"]),
        total_evaluated_cutoff_count=int(row["total_evaluated_cutoff_count"]),
        total_simulated_trade_count=int(row["total_simulated_trade_count"]),
        total_executed_trade_count=int(row["total_executed_trade_count"]),
        positive_net_pnl_window_count=int(row["positive_net_pnl_window_count"]),
        negative_net_pnl_window_count=int(row["negative_net_pnl_window_count"]),
        positive_total_r_window_count=int(row["positive_total_r_window_count"]),
        negative_total_r_window_count=int(row["negative_total_r_window_count"]),
        median_window_net_pnl=cast(Decimal, row["median_window_net_pnl"]),
        median_window_total_r=cast(Decimal, row["median_window_total_r"]),
        best_window_by_net_pnl=WindowExtreme(
            window_id=str(row["best_window_by_net_pnl_id"]),
            value=cast(Decimal, row["best_window_by_net_pnl_value"]),
        ),
        worst_window_by_net_pnl=WindowExtreme(
            window_id=str(row["worst_window_by_net_pnl_id"]),
            value=cast(Decimal, row["worst_window_by_net_pnl_value"]),
        ),
        best_window_by_total_r=WindowExtreme(
            window_id=str(row["best_window_by_total_r_id"]),
            value=cast(Decimal, row["best_window_by_total_r_value"]),
        ),
        worst_window_by_total_r=WindowExtreme(
            window_id=str(row["worst_window_by_total_r_id"]),
            value=cast(Decimal, row["worst_window_by_total_r_value"]),
        ),
        all_window_net_pnl_total=cast(Decimal, row["all_window_net_pnl_total"]),
        all_window_total_r_total=cast(Decimal, row["all_window_total_r_total"]),
        excluding_best_window_net_pnl_total=cast(
            Decimal, row["excluding_best_window_net_pnl_total"]
        ),
        excluding_best_window_total_r_total=cast(
            Decimal, row["excluding_best_window_total_r_total"]
        ),
        largest_positive_window_share_of_positive_pnl=cast(
            Decimal | None, row["largest_positive_window_share_of_positive_pnl"]
        ),
        largest_negative_window_share_of_absolute_negative_pnl=cast(
            Decimal | None, row["largest_negative_window_share_of_absolute_negative_pnl"]
        ),
        current_universe_bias_stress=bias_stress,
    )


class PostgresSurvivorshipAwareRobustnessStudyRepository:
    """Concrete, storage-aware repository for immutable survivorship-aware
    robustness studies."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(
        self, identity: DomainIdentity[SurvivorshipStudyId]
    ) -> SurvivorshipAwareRobustnessStudy:
        with self._service.unit_of_work() as work:
            study_rows = work.execute(
                "SELECT * FROM survivorship_study "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not study_rows:
                raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=identity)
            window_rows = work.execute(
                "SELECT * FROM survivorship_window WHERE study_runtime_id = :runtime_id "
                "ORDER BY sequence_index",
                {"runtime_id": str(identity.runtime_id)},
            )
        study_row = study_rows[0]
        window_results = tuple(
            _row_to_window_result(
                row,
                universe_id=str(study_row["universe_id"]),
                universe_version=str(study_row["universe_version"]),
                membership_manifest_hash=str(study_row["membership_manifest_hash"]),
            )
            for row in window_rows
        )
        return _row_to_study(study_row, window_results)

    def add(self, study: SurvivorshipAwareRobustnessStudy) -> None:
        identity = study.identity
        stress = study.current_universe_bias_stress
        study_insert_sql = (
            "INSERT INTO survivorship_study ("
            "runtime_id, governance_id, dataset_bundle_id, dataset_bundle_version, "
            "dataset_bundle_sha256, dataset_source_kind, universe_id, universe_version, "
            "universe_membership_model, membership_manifest_hash, reference_window_size, "
            "strategy_id, strategy_version, ranking_model_id, ranking_model_version, "
            "risk_policy_id, risk_policy_version, sizing_policy_id, sizing_policy_version, "
            "execution_assumption_id, execution_assumption_version, outcome_model_id, "
            "outcome_model_version, cost_model_id, cost_model_version, holding_horizon_bars, "
            "supplied_account_equity, supplied_risk_percent, regime_policy_id, "
            "regime_policy_version, corporate_action_handling, status, classification, "
            "window_count, total_evaluated_cutoff_count, total_simulated_trade_count, "
            "total_executed_trade_count, positive_net_pnl_window_count, "
            "negative_net_pnl_window_count, positive_total_r_window_count, "
            "negative_total_r_window_count, median_window_net_pnl, median_window_total_r, "
            "best_window_by_net_pnl_id, best_window_by_net_pnl_value, "
            "worst_window_by_net_pnl_id, worst_window_by_net_pnl_value, "
            "best_window_by_total_r_id, best_window_by_total_r_value, "
            "worst_window_by_total_r_id, worst_window_by_total_r_value, "
            "all_window_net_pnl_total, all_window_total_r_total, "
            "excluding_best_window_net_pnl_total, excluding_best_window_total_r_total, "
            "largest_positive_window_share_of_positive_pnl, "
            "largest_negative_window_share_of_absolute_negative_pnl, "
            "stress_study_governance_id, stress_comparison, stress_full_universe_size, "
            "stress_canonical_total_executed_trade_count, stress_total_executed_trade_count, "
            "stress_canonical_net_pnl_total, stress_net_pnl_total, "
            "stress_canonical_total_r_total, stress_total_r_total, "
            "stress_canonical_best_window_by_net_pnl_id, "
            "stress_canonical_best_window_by_net_pnl_value, "
            "stress_best_window_by_net_pnl_id, stress_best_window_by_net_pnl_value, "
            "stress_canonical_worst_window_by_net_pnl_id, "
            "stress_canonical_worst_window_by_net_pnl_value, "
            "stress_worst_window_by_net_pnl_id, stress_worst_window_by_net_pnl_value"
            ") VALUES ("
            ":runtime_id, :governance_id, :dataset_bundle_id, :dataset_bundle_version, "
            ":dataset_bundle_sha256, :dataset_source_kind, :universe_id, :universe_version, "
            ":universe_membership_model, :membership_manifest_hash, :reference_window_size, "
            ":strategy_id, :strategy_version, :ranking_model_id, :ranking_model_version, "
            ":risk_policy_id, :risk_policy_version, :sizing_policy_id, :sizing_policy_version, "
            ":execution_assumption_id, :execution_assumption_version, :outcome_model_id, "
            ":outcome_model_version, :cost_model_id, :cost_model_version, :holding_horizon_bars, "
            ":supplied_account_equity, :supplied_risk_percent, :regime_policy_id, "
            ":regime_policy_version, :corporate_action_handling, :status, :classification, "
            ":window_count, :total_evaluated_cutoff_count, :total_simulated_trade_count, "
            ":total_executed_trade_count, :positive_net_pnl_window_count, "
            ":negative_net_pnl_window_count, :positive_total_r_window_count, "
            ":negative_total_r_window_count, :median_window_net_pnl, :median_window_total_r, "
            ":best_window_by_net_pnl_id, :best_window_by_net_pnl_value, "
            ":worst_window_by_net_pnl_id, :worst_window_by_net_pnl_value, "
            ":best_window_by_total_r_id, :best_window_by_total_r_value, "
            ":worst_window_by_total_r_id, :worst_window_by_total_r_value, "
            ":all_window_net_pnl_total, :all_window_total_r_total, "
            ":excluding_best_window_net_pnl_total, :excluding_best_window_total_r_total, "
            ":largest_positive_window_share_of_positive_pnl, "
            ":largest_negative_window_share_of_absolute_negative_pnl, "
            ":stress_study_governance_id, :stress_comparison, :stress_full_universe_size, "
            ":stress_canonical_total_executed_trade_count, :stress_total_executed_trade_count, "
            ":stress_canonical_net_pnl_total, :stress_net_pnl_total, "
            ":stress_canonical_total_r_total, :stress_total_r_total, "
            ":stress_canonical_best_window_by_net_pnl_id, "
            ":stress_canonical_best_window_by_net_pnl_value, "
            ":stress_best_window_by_net_pnl_id, :stress_best_window_by_net_pnl_value, "
            ":stress_canonical_worst_window_by_net_pnl_id, "
            ":stress_canonical_worst_window_by_net_pnl_value, "
            ":stress_worst_window_by_net_pnl_id, :stress_worst_window_by_net_pnl_value"
            ")"
        )
        window_insert_sql = (
            "INSERT INTO survivorship_window ("
            "study_runtime_id, window_id, sequence_index, data_start_timestamp, "
            "data_end_timestamp, scoring_start_timestamp, scoring_end_timestamp, "
            "eligible_instrument_ids, evaluated_instrument_ids, "
            "missing_data_excluded_instrument_ids, backtest_run_governance_id, "
            "backtest_run_runtime_id, regime_label, realized_volatility, "
            "evaluated_cutoff_count, simulated_trade_count, executed_trade_count, win_count, "
            "loss_count, time_exit_count, no_entry_count, gross_pnl, net_pnl, average_net_pnl, "
            "average_r, total_r, win_rate, profit_factor, maximum_realized_pnl_drawdown"
            ") VALUES ("
            ":study_runtime_id, :window_id, :sequence_index, :data_start_timestamp, "
            ":data_end_timestamp, :scoring_start_timestamp, :scoring_end_timestamp, "
            ":eligible_instrument_ids, :evaluated_instrument_ids, "
            ":missing_data_excluded_instrument_ids, :backtest_run_governance_id, "
            ":backtest_run_runtime_id, :regime_label, :realized_volatility, "
            ":evaluated_cutoff_count, :simulated_trade_count, :executed_trade_count, "
            ":win_count, :loss_count, :time_exit_count, :no_entry_count, :gross_pnl, :net_pnl, "
            ":average_net_pnl, :average_r, :total_r, :win_rate, :profit_factor, "
            ":maximum_realized_pnl_drawdown"
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
                        "universe_id": study.universe_id,
                        "universe_version": study.universe_version,
                        "universe_membership_model": study.universe_membership_model,
                        "membership_manifest_hash": study.membership_manifest_hash,
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
                        "regime_policy_id": study.regime_policy_id,
                        "regime_policy_version": study.regime_policy_version,
                        "corporate_action_handling": study.corporate_action_handling,
                        "status": study.status.value,
                        "classification": study.classification.value,
                        "window_count": study.window_count,
                        "total_evaluated_cutoff_count": study.total_evaluated_cutoff_count,
                        "total_simulated_trade_count": study.total_simulated_trade_count,
                        "total_executed_trade_count": study.total_executed_trade_count,
                        "positive_net_pnl_window_count": study.positive_net_pnl_window_count,
                        "negative_net_pnl_window_count": study.negative_net_pnl_window_count,
                        "positive_total_r_window_count": study.positive_total_r_window_count,
                        "negative_total_r_window_count": study.negative_total_r_window_count,
                        "median_window_net_pnl": study.median_window_net_pnl,
                        "median_window_total_r": study.median_window_total_r,
                        "best_window_by_net_pnl_id": study.best_window_by_net_pnl.window_id,
                        "best_window_by_net_pnl_value": study.best_window_by_net_pnl.value,
                        "worst_window_by_net_pnl_id": study.worst_window_by_net_pnl.window_id,
                        "worst_window_by_net_pnl_value": study.worst_window_by_net_pnl.value,
                        "best_window_by_total_r_id": study.best_window_by_total_r.window_id,
                        "best_window_by_total_r_value": study.best_window_by_total_r.value,
                        "worst_window_by_total_r_id": study.worst_window_by_total_r.window_id,
                        "worst_window_by_total_r_value": study.worst_window_by_total_r.value,
                        "all_window_net_pnl_total": study.all_window_net_pnl_total,
                        "all_window_total_r_total": study.all_window_total_r_total,
                        "excluding_best_window_net_pnl_total": (
                            study.excluding_best_window_net_pnl_total
                        ),
                        "excluding_best_window_total_r_total": (
                            study.excluding_best_window_total_r_total
                        ),
                        "largest_positive_window_share_of_positive_pnl": (
                            study.largest_positive_window_share_of_positive_pnl
                        ),
                        "largest_negative_window_share_of_absolute_negative_pnl": (
                            study.largest_negative_window_share_of_absolute_negative_pnl
                        ),
                        "stress_study_governance_id": str(stress.stress_study_id),
                        "stress_comparison": stress.comparison.value,
                        "stress_full_universe_size": stress.full_universe_size,
                        "stress_canonical_total_executed_trade_count": (
                            stress.canonical_total_executed_trade_count
                        ),
                        "stress_total_executed_trade_count": (
                            stress.stress_total_executed_trade_count
                        ),
                        "stress_canonical_net_pnl_total": stress.canonical_net_pnl_total,
                        "stress_net_pnl_total": stress.stress_net_pnl_total,
                        "stress_canonical_total_r_total": stress.canonical_total_r_total,
                        "stress_total_r_total": stress.stress_total_r_total,
                        "stress_canonical_best_window_by_net_pnl_id": (
                            stress.canonical_best_window_by_net_pnl.window_id
                        ),
                        "stress_canonical_best_window_by_net_pnl_value": (
                            stress.canonical_best_window_by_net_pnl.value
                        ),
                        "stress_best_window_by_net_pnl_id": (
                            stress.stress_best_window_by_net_pnl.window_id
                        ),
                        "stress_best_window_by_net_pnl_value": (
                            stress.stress_best_window_by_net_pnl.value
                        ),
                        "stress_canonical_worst_window_by_net_pnl_id": (
                            stress.canonical_worst_window_by_net_pnl.window_id
                        ),
                        "stress_canonical_worst_window_by_net_pnl_value": (
                            stress.canonical_worst_window_by_net_pnl.value
                        ),
                        "stress_worst_window_by_net_pnl_id": (
                            stress.stress_worst_window_by_net_pnl.window_id
                        ),
                        "stress_worst_window_by_net_pnl_value": (
                            stress.stress_worst_window_by_net_pnl.value
                        ),
                    },
                )
                for result in study.window_results:
                    snapshot = result.snapshot
                    work.execute(
                        window_insert_sql,
                        {
                            "study_runtime_id": str(identity.runtime_id),
                            "window_id": snapshot.window_id,
                            "sequence_index": snapshot.sequence_index,
                            "data_start_timestamp": result.data_start_timestamp,
                            "data_end_timestamp": result.data_end_timestamp,
                            "scoring_start_timestamp": result.scoring_start_timestamp,
                            "scoring_end_timestamp": result.scoring_end_timestamp,
                            "eligible_instrument_ids": [
                                str(iid) for iid in snapshot.eligible_instrument_ids
                            ],
                            "evaluated_instrument_ids": [
                                str(iid) for iid in snapshot.evaluated_instrument_ids
                            ],
                            "missing_data_excluded_instrument_ids": [
                                str(iid) for iid in snapshot.missing_data_excluded_instrument_ids
                            ],
                            "backtest_run_governance_id": (
                                str(result.backtest_run_id)
                                if result.backtest_run_id is not None
                                else None
                            ),
                            "backtest_run_runtime_id": (
                                str(result.backtest_run_runtime_id)
                                if result.backtest_run_runtime_id is not None
                                else None
                            ),
                            "regime_label": result.regime_label.value,
                            "realized_volatility": result.realized_volatility,
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
                            "maximum_realized_pnl_drawdown": (result.maximum_realized_pnl_drawdown),
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _ROOT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_AGGREGATE_KIND, identity=identity
                    ) from exc
                raise


class PostgresInstrumentMasterRepository:
    """Concrete, storage-aware repository for the small instrument-master
    reference table -- write-once per instrument, read for audit."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def add_all(self, master: InstrumentMaster) -> None:
        insert_sql = (
            "INSERT INTO instrument_master ("
            "instrument_id, canonical_symbol, instrument_type, exchange_or_venue, "
            "external_identifier"
            ") VALUES ("
            ":instrument_id, :canonical_symbol, :instrument_type, :exchange_or_venue, "
            ":external_identifier"
            ") ON CONFLICT (instrument_id) DO NOTHING"
        )
        with self._service.unit_of_work() as work:
            for entry in master.entries:
                work.execute(
                    insert_sql,
                    {
                        "instrument_id": str(entry.instrument_id),
                        "canonical_symbol": str(entry.canonical_symbol),
                        "instrument_type": entry.instrument_type.value,
                        "exchange_or_venue": entry.exchange_or_venue,
                        "external_identifier": entry.external_identifier,
                    },
                )


class PostgresUniverseMembershipRepository:
    """Concrete, storage-aware repository for `universe_authority` and
    `membership_record` -- write-once per universe version."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def add_universe(self, authority: UniverseAuthority) -> None:
        insert_sql = (
            "INSERT INTO universe_authority (universe_id, universe_version, source_kind) "
            "VALUES (:universe_id, :universe_version, :source_kind) "
            "ON CONFLICT (universe_id, universe_version) DO NOTHING"
        )
        with self._service.unit_of_work() as work:
            work.execute(
                insert_sql,
                {
                    "universe_id": authority.universe_id,
                    "universe_version": authority.universe_version,
                    "source_kind": authority.source_kind,
                },
            )

    def add_membership(self, manifest: MembershipManifest) -> None:
        insert_sql = (
            "INSERT INTO membership_record ("
            "universe_id, universe_version, instrument_id, effective_from, effective_to, "
            "membership_status, source_kind"
            ") VALUES ("
            ":universe_id, :universe_version, :instrument_id, :effective_from, :effective_to, "
            ":membership_status, :source_kind"
            ") ON CONFLICT (universe_id, universe_version, instrument_id, effective_from) "
            "DO NOTHING"
        )
        with self._service.unit_of_work() as work:
            for record in manifest.records:
                work.execute(
                    insert_sql,
                    {
                        "universe_id": record.universe_id,
                        "universe_version": record.universe_version,
                        "instrument_id": str(record.instrument_id),
                        "effective_from": record.effective_from,
                        "effective_to": record.effective_to,
                        "membership_status": record.membership_status.value,
                        "source_kind": record.source_kind,
                    },
                )

    def membership_status_values(self) -> tuple[str, ...]:
        return tuple(status.value for status in MembershipStatus)
