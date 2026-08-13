"""MILESTONE-074 -- Read-only M074-owned PostgreSQL query adapter.

Concrete read-only query boundary that composes the existing frozen
`survivorship_study`, `survivorship_window`, `portfolio_study`
(plus its child tables `portfolio_allocation_decision`,
`portfolio_equity_observation`, `portfolio_capital_sensitivity`), and
`instrument_master` tables. Does NOT mutate any persisted row. Does
NOT modify the existing frozen M064 / M067 / InstrumentMaster
PostgreSQL repository classes or their migrations.

This module lives in `shared/persistence/postgres_repositories/` so it
can `SELECT FROM` the existing tables. The architecture-checker
explicitly clears forbidden-prefix rules for files in `shared/` that
are not under the `domain/` subpath (see `tools/check_architecture.py`
`check_path` body), so this file is permitted to issue SQL.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.instrument_master import (
    InstrumentId,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentType,
)
from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.portfolio_study import (
    CapitalSensitivityLabel,
    CapitalSensitivityView,
    PortfolioAllocationDecision,
    PortfolioAllocationOutcome,
    PortfolioCapitalPolicy,
    PortfolioEquityObservation,
    PortfolioEventKind,
    PortfolioEvidenceReport,
    PortfolioRejectionReason,
)
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
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    BacktestRunId,
    DatasetId,
    PortfolioStudyId,
    RobustnessStudyId,
    SurvivorshipStudyId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService


def _row_to_window(
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


def _row_to_portfolio_report(
    row: Mapping[str, Any],
    decision_rows: Sequence[Mapping[str, Any]],
    equity_rows: Sequence[Mapping[str, Any]],
    sensitivity_rows: Sequence[Mapping[str, Any]],
) -> PortfolioEvidenceReport:
    capital_policy = PortfolioCapitalPolicy(
        policy_id=str(row["capital_policy_id"]),
        version=str(row["capital_policy_version"]),
        initial_capital=cast(Decimal, row["initial_capital"]),
        currency=str(row["currency"]),
        max_concurrent_positions=int(row["max_concurrent_positions"]),
        max_capital_utilization_percent=cast(Decimal, row["max_capital_utilization_percent"]),
    )
    decisions: list[PortfolioAllocationDecision] = []
    for d in decision_rows:
        decisions.append(
            PortfolioAllocationDecision(
                opportunity_sequence=int(d["opportunity_sequence"]),
                source_window_id=str(d["source_window_id"]),
                trade_sequence=int(d["trade_sequence"]),
                instrument_symbol=str(d["instrument_symbol"]),
                scan_rank=int(d["scan_rank"]),
                entry_timestamp=d["entry_timestamp"],
                exit_timestamp=d["exit_timestamp"],
                risk_amount=cast(Decimal, d["risk_amount"]),
                net_pnl=cast(Decimal, d["net_pnl"]),
                decision=PortfolioAllocationOutcome(str(d["decision"])),
                rejection_reason=(
                    PortfolioRejectionReason(str(d["rejection_reason"]))
                    if d["rejection_reason"] is not None
                    else None
                ),
            )
        )
    equity: list[PortfolioEquityObservation] = []
    for e in equity_rows:
        equity.append(
            PortfolioEquityObservation(
                sequence_index=int(e["sequence_index"]),
                event_timestamp=e["event_timestamp"],
                event_kind=PortfolioEventKind(str(e["event_kind"])),
                equity=cast(Decimal, e["equity"]),
                occupied_capital=cast(Decimal, e["occupied_capital"]),
                available_capital=cast(Decimal, e["available_capital"]),
                open_position_count=int(e["open_position_count"]),
            )
        )
    sensitivity: list[CapitalSensitivityView] = []
    for s in sensitivity_rows:
        sensitivity.append(
            CapitalSensitivityView(
                label=CapitalSensitivityLabel(str(s["label"])),
                capital_policy_id=str(s["capital_policy_id"]),
                initial_capital=cast(Decimal, s["initial_capital"]),
                max_concurrent_positions=int(s["max_concurrent_positions"]),
                allocated_count=int(s["allocated_count"]),
                rejected_count=int(s["rejected_count"]),
                ending_capital=cast(Decimal, s["ending_capital"]),
                realized_pnl=cast(Decimal, s["realized_pnl"]),
                max_drawdown=cast(Decimal, s["max_drawdown"]),
            )
        )
    return PortfolioEvidenceReport(
        identity=DomainIdentity(
            governance_id=PortfolioStudyId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        source_study_governance_id=str(row["source_study_governance_id"]),
        source_study_runtime_id=str(row["source_study_runtime_id"]),
        dataset_bundle_id=str(row["dataset_bundle_id"]),
        dataset_bundle_version=str(row["dataset_bundle_version"]),
        dataset_bundle_sha256=str(row["dataset_bundle_sha256"]),
        dataset_source_kind=str(row["dataset_source_kind"]),
        universe_id=str(row["universe_id"]),
        universe_version=str(row["universe_version"]),
        membership_manifest_hash=str(row["membership_manifest_hash"]),
        strategy_id=str(row["strategy_id"]),
        strategy_version=str(row["strategy_version"]),
        ranking_model_id=str(row["ranking_model_id"]),
        ranking_model_version=str(row["ranking_model_version"]),
        risk_policy_id=str(row["risk_policy_id"]),
        risk_policy_version=str(row["risk_policy_version"]),
        sizing_policy_id=str(row["sizing_policy_id"]),
        sizing_policy_version=str(row["sizing_policy_version"]),
        capital_policy=capital_policy,
        total_opportunities=int(row["total_opportunities"]),
        allocated_count=int(row["allocated_count"]),
        rejected_count=int(row["rejected_count"]),
        rejected_insufficient_capital_count=int(row["rejected_insufficient_capital_count"]),
        rejected_max_concurrent_count=int(row["rejected_max_concurrent_count"]),
        rejected_max_utilization_count=int(row["rejected_max_utilization_count"]),
        initial_capital=capital_policy.initial_capital,
        ending_capital=cast(Decimal, row["ending_capital"]),
        realized_pnl=cast(Decimal, row["realized_pnl"]),
        portfolio_return_percent=cast(Decimal, row["portfolio_return_percent"]),
        peak_equity=cast(Decimal, row["peak_equity"]),
        max_drawdown=cast(Decimal, row["max_drawdown"]),
        max_drawdown_percent=cast(Decimal | None, row["max_drawdown_percent"]),
        max_concurrent_positions_observed=int(row["max_concurrent_positions_observed"]),
        average_concurrent_positions=cast(Decimal | None, row["average_concurrent_positions"]),
        peak_occupied_capital=cast(Decimal, row["peak_occupied_capital"]),
        peak_capital_utilization_percent=cast(
            Decimal | None, row["peak_capital_utilization_percent"]
        ),
        largest_instrument_positive_contribution_symbol=(
            str(row["largest_instrument_positive_contribution_symbol"])
            if row["largest_instrument_positive_contribution_symbol"] is not None
            else None
        ),
        largest_instrument_positive_contribution_amount=cast(
            Decimal | None, row["largest_instrument_positive_contribution_amount"]
        ),
        largest_instrument_negative_contribution_symbol=(
            str(row["largest_instrument_negative_contribution_symbol"])
            if row["largest_instrument_negative_contribution_symbol"] is not None
            else None
        ),
        largest_instrument_negative_contribution_amount=cast(
            Decimal | None, row["largest_instrument_negative_contribution_amount"]
        ),
        largest_position_contribution_trade_sequence=cast(
            int | None, row["largest_position_contribution_trade_sequence"]
        ),
        largest_position_contribution_amount=cast(
            Decimal | None, row["largest_position_contribution_amount"]
        ),
        largest_window_contribution_window_id=(
            str(row["largest_window_contribution_window_id"])
            if row["largest_window_contribution_window_id"] is not None
            else None
        ),
        largest_window_contribution_amount=cast(
            Decimal | None, row["largest_window_contribution_amount"]
        ),
        allocation_decisions=tuple(decisions),
        equity_curve=tuple(equity),
        capital_sensitivity_views=tuple(sensitivity),
    )


def _row_to_instrument_entry(row: Mapping[str, Any]) -> InstrumentMasterEntry:
    return InstrumentMasterEntry(
        instrument_id=InstrumentId(str(row["instrument_id"])),
        canonical_symbol=Instrument(symbol=str(row["canonical_symbol"])),
        instrument_type=InstrumentType(str(row["instrument_type"])),
        exchange_or_venue=row["exchange_or_venue"],
        external_identifier=row["external_identifier"],
    )


class PostgresHistoricalPortfolioEvidenceQueryRepository:
    """M074-owned read-only PostgreSQL query adapter. Composes the
    existing frozen M064 (survivorship_study, survivorship_window),
    M067 (portfolio_study), and M064-instrument-master tables.

    Does not mutate any persisted row. Does not modify the existing
    frozen `PostgresSurvivorshipAwareRobustnessStudyRepository`,
    `PostgresPortfolioStudyRepository`, or
    `PostgresInstrumentMasterRepository` classes or their migrations.
    """

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def list_survivorship_candidates(self) -> tuple[SurvivorshipAwareRobustnessStudy, ...]:
        with self._service.unit_of_work() as work:
            study_rows = work.execute("SELECT * FROM survivorship_study ORDER BY governance_id")
            studies: list[SurvivorshipAwareRobustnessStudy] = []
            for srow in study_rows:
                window_rows = work.execute(
                    "SELECT * FROM survivorship_window WHERE study_runtime_id = :rid "
                    "ORDER BY sequence_index",
                    {"rid": str(srow["runtime_id"])},
                )
                window_results = tuple(
                    _row_to_window(
                        w,
                        universe_id=str(srow["universe_id"]),
                        universe_version=str(srow["universe_version"]),
                        membership_manifest_hash=str(srow["membership_manifest_hash"]),
                    )
                    for w in window_rows
                )
                studies.append(_row_to_study(srow, window_results))
            return tuple(studies)

    def find_portfolio_report_for(
        self, source_study_runtime_id: str
    ) -> PortfolioEvidenceReport | None:
        with self._service.unit_of_work() as work:
            report_rows = work.execute(
                "SELECT * FROM portfolio_study WHERE source_study_runtime_id = :rid "
                "ORDER BY governance_id LIMIT 1",
                {"rid": source_study_runtime_id},
            )
            if not report_rows:
                return None
            report_row = report_rows[0]
            decision_rows = list(
                work.execute(
                    "SELECT * FROM portfolio_allocation_decision WHERE report_runtime_id = :rid "
                    "ORDER BY opportunity_sequence",
                    {"rid": str(report_row["runtime_id"])},
                )
            )
            equity_rows = list(
                work.execute(
                    "SELECT * FROM portfolio_equity_observation WHERE report_runtime_id = :rid "
                    "ORDER BY sequence_index",
                    {"rid": str(report_row["runtime_id"])},
                )
            )
            sensitivity_rows = list(
                work.execute(
                    "SELECT * FROM portfolio_capital_sensitivity WHERE report_runtime_id = :rid "
                    "ORDER BY label",
                    {"rid": str(report_row["runtime_id"])},
                )
            )
        return _row_to_portfolio_report(report_row, decision_rows, equity_rows, sensitivity_rows)

    def load_instrument_master(self) -> InstrumentMaster | None:
        with self._service.unit_of_work() as work:
            rows = work.execute("SELECT * FROM instrument_master ORDER BY instrument_id")
            if not rows:
                return None
            entries = tuple(_row_to_instrument_entry(row) for row in rows)
        return InstrumentMaster(entries=entries)
