"""Concrete PostgreSQL repository for M061 historical backtest runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.historical_backtest import (
    HistoricalBacktestRun,
    HistoricalBacktestRunStatus,
    HistoricalBacktestTrade,
    HistoricalTradeOutcome,
    HistoricalValidationClassification,
    SameBarAmbiguityPolicy,
)
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, DatasetId
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_AGGREGATE_KIND = "HistoricalBacktestRun"
_ROOT_UNIQUE_CONSTRAINTS = {
    "pk_historical_backtest_run",
    "uq_historical_backtest_run_governance_id",
}


def _row_to_trade(row: Mapping[str, Any]) -> HistoricalBacktestTrade:
    r_multiple = cast(Decimal | None, row["r_multiple"])
    return HistoricalBacktestTrade(
        trade_sequence=int(row["trade_sequence"]),
        instrument=Instrument(str(row["instrument_symbol"])),
        evaluation_cutoff=row["evaluation_cutoff"],
        source_scan_reference=str(row["source_scan_reference"]),
        source_decision_candidate_reference=str(row["source_decision_candidate_reference"]),
        source_trade_plan_reference=str(row["source_trade_plan_reference"]),
        source_position_plan_reference=str(row["source_position_plan_reference"]),
        scan_rank=int(row["scan_rank"]),
        ranking_score=cast(Decimal, row["ranking_score"]),
        entry_timestamp=row["entry_timestamp"],
        planned_entry_price=cast(Decimal, row["planned_entry_price"]),
        simulated_entry_price=cast(Decimal | None, row["simulated_entry_price"]),
        planned_stop_price=cast(Decimal, row["planned_stop_price"]),
        planned_target_price=cast(Decimal, row["planned_target_price"]),
        exit_timestamp=row["exit_timestamp"],
        exit_price=cast(Decimal | None, row["exit_price"]),
        outcome=HistoricalTradeOutcome(str(row["outcome"])),
        ambiguity_policy=SameBarAmbiguityPolicy(str(row["ambiguity_policy"])),
        ambiguity_triggered=bool(row["ambiguity_triggered"]),
        quantity=int(row["quantity"]),
        gross_pnl=cast(Decimal, row["gross_pnl"]),
        transaction_costs=cast(Decimal, row["transaction_costs"]),
        net_pnl=cast(Decimal, row["net_pnl"]),
        risk_amount=cast(Decimal, row["risk_amount"]),
        r_multiple=r_multiple,
        holding_bars=int(row["holding_bars"]) if row["holding_bars"] is not None else None,
    )


def _row_to_run(
    row: Mapping[str, Any],
    trades: Sequence[HistoricalBacktestTrade],
) -> HistoricalBacktestRun:
    return HistoricalBacktestRun(
        identity=DomainIdentity(
            governance_id=BacktestRunId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        dataset_id=DatasetId(str(row["dataset_id"])),
        dataset_version=str(row["dataset_version"]),
        dataset_source_kind=str(row["dataset_source_kind"]),
        dataset_sha256=str(row["dataset_sha256"]),
        interval=BarInterval(str(row["bar_interval"])),
        universe=tuple(Instrument(symbol) for symbol in row["universe_symbols"]),
        dataset_start_timestamp=row["dataset_start_timestamp"],
        dataset_end_timestamp=row["dataset_end_timestamp"],
        dataset_total_bars=int(row["dataset_total_bars"]),
        reference_window_size=int(row["reference_window_size"]),
        decision_cadence=str(row["decision_cadence"]),
        strategy_id=str(row["strategy_id"]),
        strategy_version=str(row["strategy_version"]),
        ranking_model_id=str(row["ranking_model_id"]),
        ranking_model_version=str(row["ranking_model_version"]),
        risk_policy_id=str(row["risk_policy_id"]),
        risk_policy_version=str(row["risk_policy_version"]),
        risk_policy_target_projection_percent=cast(
            Decimal, row["risk_policy_target_projection_percent"]
        ),
        risk_policy_minimum_reward_risk_ratio=cast(
            Decimal, row["risk_policy_minimum_reward_risk_ratio"]
        ),
        sizing_policy_id=str(row["sizing_policy_id"]),
        sizing_policy_version=str(row["sizing_policy_version"]),
        sizing_policy_maximum_risk_percent=cast(Decimal, row["sizing_policy_maximum_risk_percent"]),
        sizing_policy_maximum_notional_percent=cast(
            Decimal, row["sizing_policy_maximum_notional_percent"]
        ),
        sizing_policy_allow_fractional_shares=bool(row["sizing_policy_allow_fractional_shares"]),
        supplied_account_equity=cast(Decimal, row["supplied_account_equity"]),
        supplied_risk_percent=cast(Decimal, row["supplied_risk_percent"]),
        execution_assumption_id=str(row["execution_assumption_id"]),
        execution_assumption_version=str(row["execution_assumption_version"]),
        outcome_model_id=str(row["outcome_model_id"]),
        outcome_model_version=str(row["outcome_model_version"]),
        outcome_model_no_overnight=bool(row["outcome_model_no_overnight"]),
        cost_model_id=str(row["cost_model_id"]),
        cost_model_version=str(row["cost_model_version"]),
        cost_model_entry_slippage_bps=cast(Decimal, row["cost_model_entry_slippage_bps"]),
        cost_model_exit_slippage_bps=cast(Decimal, row["cost_model_exit_slippage_bps"]),
        cost_model_fixed_commission_per_side=cast(
            Decimal, row["cost_model_fixed_commission_per_side"]
        ),
        ambiguity_policy=SameBarAmbiguityPolicy(str(row["ambiguity_policy"])),
        holding_horizon_bars=int(row["holding_horizon_bars"]),
        status=HistoricalBacktestRunStatus(str(row["status"])),
        product_classification=HistoricalValidationClassification(
            str(row["product_classification"])
        ),
        evaluated_cutoff_count=int(row["evaluated_cutoff_count"]),
        evaluated_opportunity_count=int(row["evaluated_opportunity_count"]),
        approved_trade_plan_count=int(row["approved_trade_plan_count"]),
        approved_position_plan_count=int(row["approved_position_plan_count"]),
        simulated_trade_count=int(row["simulated_trade_count"]),
        executed_trade_count=int(row["executed_trade_count"]),
        win_count=int(row["win_count"]),
        loss_count=int(row["loss_count"]),
        flat_count=int(row["flat_count"]),
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
        trades=tuple(trades),
    )


class PostgresHistoricalBacktestRunRepository:
    """Concrete, storage-aware repository for immutable historical backtest runs."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, identity: DomainIdentity[BacktestRunId]) -> HistoricalBacktestRun:
        with self._service.unit_of_work() as work:
            run_rows = work.execute(
                "SELECT * FROM historical_backtest_run "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not run_rows:
                raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=identity)
            trade_rows = work.execute(
                "SELECT * FROM historical_backtest_trade "
                "WHERE backtest_run_runtime_id = :runtime_id "
                "ORDER BY trade_sequence",
                {"runtime_id": str(identity.runtime_id)},
            )
        trades = tuple(_row_to_trade(row) for row in trade_rows)
        return _row_to_run(run_rows[0], trades)

    def add(self, run: HistoricalBacktestRun) -> None:
        identity = run.identity
        run_insert_sql = (
            "INSERT INTO historical_backtest_run ("
            "runtime_id, governance_id, dataset_id, dataset_version, dataset_source_kind, "
            "dataset_sha256, bar_interval, universe_symbols, dataset_start_timestamp, "
            "dataset_end_timestamp, dataset_total_bars, reference_window_size, "
            "decision_cadence, strategy_id, strategy_version, ranking_model_id, "
            "ranking_model_version, risk_policy_id, risk_policy_version, "
            "risk_policy_target_projection_percent, "
            "risk_policy_minimum_reward_risk_ratio, "
            "sizing_policy_id, sizing_policy_version, "
            "sizing_policy_maximum_risk_percent, "
            "sizing_policy_maximum_notional_percent, "
            "sizing_policy_allow_fractional_shares, supplied_account_equity, "
            "supplied_risk_percent, execution_assumption_id, "
            "execution_assumption_version, outcome_model_id, outcome_model_version, "
            "outcome_model_no_overnight, cost_model_id, cost_model_version, "
            "cost_model_entry_slippage_bps, cost_model_exit_slippage_bps, "
            "cost_model_fixed_commission_per_side, ambiguity_policy, "
            "holding_horizon_bars, status, product_classification, "
            "evaluated_cutoff_count, evaluated_opportunity_count, "
            "approved_trade_plan_count, approved_position_plan_count, "
            "simulated_trade_count, executed_trade_count, win_count, loss_count, "
            "flat_count, time_exit_count, no_entry_count, gross_pnl, net_pnl, "
            "average_net_pnl, average_r, total_r, win_rate, profit_factor, "
            "maximum_realized_pnl_drawdown"
            ") VALUES ("
            ":runtime_id, :governance_id, :dataset_id, :dataset_version, :dataset_source_kind, "
            ":dataset_sha256, :bar_interval, :universe_symbols, :dataset_start_timestamp, "
            ":dataset_end_timestamp, :dataset_total_bars, :reference_window_size, "
            ":decision_cadence, :strategy_id, :strategy_version, :ranking_model_id, "
            ":ranking_model_version, :risk_policy_id, :risk_policy_version, "
            ":risk_policy_target_projection_percent, "
            ":risk_policy_minimum_reward_risk_ratio, :sizing_policy_id, "
            ":sizing_policy_version, :sizing_policy_maximum_risk_percent, "
            ":sizing_policy_maximum_notional_percent, "
            ":sizing_policy_allow_fractional_shares, :supplied_account_equity, "
            ":supplied_risk_percent, :execution_assumption_id, "
            ":execution_assumption_version, :outcome_model_id, :outcome_model_version, "
            ":outcome_model_no_overnight, :cost_model_id, :cost_model_version, "
            ":cost_model_entry_slippage_bps, :cost_model_exit_slippage_bps, "
            ":cost_model_fixed_commission_per_side, :ambiguity_policy, "
            ":holding_horizon_bars, :status, :product_classification, "
            ":evaluated_cutoff_count, :evaluated_opportunity_count, "
            ":approved_trade_plan_count, :approved_position_plan_count, "
            ":simulated_trade_count, :executed_trade_count, :win_count, "
            ":loss_count, :flat_count, :time_exit_count, :no_entry_count, "
            ":gross_pnl, :net_pnl, :average_net_pnl, :average_r, :total_r, "
            ":win_rate, :profit_factor, :maximum_realized_pnl_drawdown"
            ")"
        )
        trade_insert_sql = (
            "INSERT INTO historical_backtest_trade ("
            "backtest_run_runtime_id, trade_sequence, instrument_symbol, "
            "evaluation_cutoff, source_scan_reference, "
            "source_decision_candidate_reference, source_trade_plan_reference, "
            "source_position_plan_reference, scan_rank, ranking_score, "
            "entry_timestamp, planned_entry_price, simulated_entry_price, "
            "planned_stop_price, planned_target_price, exit_timestamp, exit_price, "
            "outcome, ambiguity_policy, ambiguity_triggered, quantity, gross_pnl, "
            "transaction_costs, net_pnl, risk_amount, r_multiple, holding_bars"
            ") VALUES ("
            ":backtest_run_runtime_id, :trade_sequence, :instrument_symbol, "
            ":evaluation_cutoff, :source_scan_reference, "
            ":source_decision_candidate_reference, :source_trade_plan_reference, "
            ":source_position_plan_reference, :scan_rank, :ranking_score, "
            ":entry_timestamp, :planned_entry_price, :simulated_entry_price, "
            ":planned_stop_price, :planned_target_price, :exit_timestamp, :exit_price, "
            ":outcome, :ambiguity_policy, :ambiguity_triggered, :quantity, :gross_pnl, "
            ":transaction_costs, :net_pnl, :risk_amount, :r_multiple, :holding_bars"
            ")"
        )
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    run_insert_sql,
                    {
                        "runtime_id": str(identity.runtime_id),
                        "governance_id": str(identity.governance_id),
                        "dataset_id": str(run.dataset_id),
                        "dataset_version": run.dataset_version,
                        "dataset_source_kind": run.dataset_source_kind,
                        "dataset_sha256": run.dataset_sha256,
                        "bar_interval": run.interval.value,
                        "universe_symbols": [str(instrument) for instrument in run.universe],
                        "dataset_start_timestamp": run.dataset_start_timestamp,
                        "dataset_end_timestamp": run.dataset_end_timestamp,
                        "dataset_total_bars": run.dataset_total_bars,
                        "reference_window_size": run.reference_window_size,
                        "decision_cadence": run.decision_cadence,
                        "strategy_id": run.strategy_id,
                        "strategy_version": run.strategy_version,
                        "ranking_model_id": run.ranking_model_id,
                        "ranking_model_version": run.ranking_model_version,
                        "risk_policy_id": run.risk_policy_id,
                        "risk_policy_version": run.risk_policy_version,
                        "risk_policy_target_projection_percent": (
                            run.risk_policy_target_projection_percent
                        ),
                        "risk_policy_minimum_reward_risk_ratio": (
                            run.risk_policy_minimum_reward_risk_ratio
                        ),
                        "sizing_policy_id": run.sizing_policy_id,
                        "sizing_policy_version": run.sizing_policy_version,
                        "sizing_policy_maximum_risk_percent": (
                            run.sizing_policy_maximum_risk_percent
                        ),
                        "sizing_policy_maximum_notional_percent": (
                            run.sizing_policy_maximum_notional_percent
                        ),
                        "sizing_policy_allow_fractional_shares": (
                            run.sizing_policy_allow_fractional_shares
                        ),
                        "supplied_account_equity": run.supplied_account_equity,
                        "supplied_risk_percent": run.supplied_risk_percent,
                        "execution_assumption_id": run.execution_assumption_id,
                        "execution_assumption_version": run.execution_assumption_version,
                        "outcome_model_id": run.outcome_model_id,
                        "outcome_model_version": run.outcome_model_version,
                        "outcome_model_no_overnight": run.outcome_model_no_overnight,
                        "cost_model_id": run.cost_model_id,
                        "cost_model_version": run.cost_model_version,
                        "cost_model_entry_slippage_bps": run.cost_model_entry_slippage_bps,
                        "cost_model_exit_slippage_bps": run.cost_model_exit_slippage_bps,
                        "cost_model_fixed_commission_per_side": (
                            run.cost_model_fixed_commission_per_side
                        ),
                        "ambiguity_policy": run.ambiguity_policy.value,
                        "holding_horizon_bars": run.holding_horizon_bars,
                        "status": run.status.value,
                        "product_classification": run.product_classification.value,
                        "evaluated_cutoff_count": run.evaluated_cutoff_count,
                        "evaluated_opportunity_count": run.evaluated_opportunity_count,
                        "approved_trade_plan_count": run.approved_trade_plan_count,
                        "approved_position_plan_count": run.approved_position_plan_count,
                        "simulated_trade_count": run.simulated_trade_count,
                        "executed_trade_count": run.executed_trade_count,
                        "win_count": run.win_count,
                        "loss_count": run.loss_count,
                        "flat_count": run.flat_count,
                        "time_exit_count": run.time_exit_count,
                        "no_entry_count": run.no_entry_count,
                        "gross_pnl": run.gross_pnl,
                        "net_pnl": run.net_pnl,
                        "average_net_pnl": run.average_net_pnl,
                        "average_r": run.average_r,
                        "total_r": run.total_r,
                        "win_rate": run.win_rate,
                        "profit_factor": run.profit_factor,
                        "maximum_realized_pnl_drawdown": run.maximum_realized_pnl_drawdown,
                    },
                )
                for trade in run.trades:
                    work.execute(
                        trade_insert_sql,
                        {
                            "backtest_run_runtime_id": str(identity.runtime_id),
                            "trade_sequence": trade.trade_sequence,
                            "instrument_symbol": str(trade.instrument),
                            "evaluation_cutoff": trade.evaluation_cutoff,
                            "source_scan_reference": trade.source_scan_reference,
                            "source_decision_candidate_reference": (
                                trade.source_decision_candidate_reference
                            ),
                            "source_trade_plan_reference": trade.source_trade_plan_reference,
                            "source_position_plan_reference": (
                                trade.source_position_plan_reference
                            ),
                            "scan_rank": trade.scan_rank,
                            "ranking_score": trade.ranking_score,
                            "entry_timestamp": trade.entry_timestamp,
                            "planned_entry_price": trade.planned_entry_price,
                            "simulated_entry_price": trade.simulated_entry_price,
                            "planned_stop_price": trade.planned_stop_price,
                            "planned_target_price": trade.planned_target_price,
                            "exit_timestamp": trade.exit_timestamp,
                            "exit_price": trade.exit_price,
                            "outcome": trade.outcome.value,
                            "ambiguity_policy": trade.ambiguity_policy.value,
                            "ambiguity_triggered": trade.ambiguity_triggered,
                            "quantity": trade.quantity,
                            "gross_pnl": trade.gross_pnl,
                            "transaction_costs": trade.transaction_costs,
                            "net_pnl": trade.net_pnl,
                            "risk_amount": trade.risk_amount,
                            "r_multiple": trade.r_multiple,
                            "holding_bars": trade.holding_bars,
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _ROOT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_AGGREGATE_KIND, identity=identity
                    ) from exc
                raise
