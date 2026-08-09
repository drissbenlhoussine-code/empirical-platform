"""Usecase-layer parsing and serialization helpers for MILESTONE-061."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

from empirical_platform.decision_candidate.historical_backtest import (
    FIXED_TEST_UNIVERSE,
    HistoricalDataset,
    HistoricalDatasetAuthority,
    HistoricalInstrumentSeries,
    HistoricalTradeOutcome,
    dataset_sha256,
)
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.identifiers.types import DatasetId


class _ValueEnumView(Protocol):
    value: str


class HistoricalBacktestTradePayloadView(Protocol):
    trade_sequence: int
    instrument: object
    evaluation_cutoff: datetime
    source_scan_reference: str
    source_decision_candidate_reference: str
    source_trade_plan_reference: str
    source_position_plan_reference: str
    scan_rank: int
    ranking_score: Decimal
    entry_timestamp: datetime | None
    planned_entry_price: Decimal
    simulated_entry_price: Decimal | None
    planned_stop_price: Decimal
    planned_target_price: Decimal
    exit_timestamp: datetime | None
    exit_price: Decimal | None
    outcome: _ValueEnumView
    ambiguity_policy: _ValueEnumView
    ambiguity_triggered: bool
    quantity: int
    gross_pnl: Decimal
    transaction_costs: Decimal
    net_pnl: Decimal
    risk_amount: Decimal
    r_multiple: Decimal | None
    holding_bars: int | None


class HistoricalBacktestRunPayloadView(Protocol):
    identity: _DomainIdentityView
    dataset_id: object
    dataset_version: str
    dataset_source_kind: str
    dataset_sha256: str
    interval: _ValueEnumView
    universe: tuple[object, ...]
    dataset_start_timestamp: datetime
    dataset_end_timestamp: datetime
    dataset_total_bars: int
    reference_window_size: int
    decision_cadence: str
    strategy_id: str
    strategy_version: str
    ranking_model_id: str
    ranking_model_version: str
    risk_policy_id: str
    risk_policy_version: str
    risk_policy_target_projection_percent: Decimal
    risk_policy_minimum_reward_risk_ratio: Decimal
    sizing_policy_id: str
    sizing_policy_version: str
    sizing_policy_maximum_risk_percent: Decimal
    sizing_policy_maximum_notional_percent: Decimal
    sizing_policy_allow_fractional_shares: bool
    supplied_account_equity: Decimal
    supplied_risk_percent: Decimal
    execution_assumption_id: str
    execution_assumption_version: str
    outcome_model_id: str
    outcome_model_version: str
    outcome_model_no_overnight: bool
    cost_model_id: str
    cost_model_version: str
    cost_model_entry_slippage_bps: Decimal
    cost_model_exit_slippage_bps: Decimal
    cost_model_fixed_commission_per_side: Decimal
    ambiguity_policy: _ValueEnumView
    holding_horizon_bars: int
    status: _ValueEnumView
    product_classification: _ValueEnumView
    evaluated_cutoff_count: int
    evaluated_opportunity_count: int
    approved_trade_plan_count: int
    approved_position_plan_count: int
    simulated_trade_count: int
    executed_trade_count: int
    win_count: int
    loss_count: int
    flat_count: int
    time_exit_count: int
    no_entry_count: int
    gross_pnl: Decimal
    net_pnl: Decimal
    average_net_pnl: Decimal | None
    average_r: Decimal | None
    total_r: Decimal
    win_rate: Decimal | None
    profit_factor: Decimal | None
    maximum_realized_pnl_drawdown: Decimal | None
    trades: tuple[HistoricalBacktestTradePayloadView, ...]


class _DomainIdentityView(Protocol):
    governance_id: object
    runtime_id: object


def _parse_bar(entry: dict[str, str], *, instrument_symbol: str) -> Bar:
    return Bar(
        instrument=Instrument(entry.get("instrument", instrument_symbol)),
        interval=BarInterval(entry["interval"]),
        timestamp=datetime.fromisoformat(entry["timestamp"]),
        open=Decimal(entry["open"]),
        high=Decimal(entry["high"]),
        low=Decimal(entry["low"]),
        close=Decimal(entry["close"]),
        volume=int(entry["volume"]),
    )


def parse_historical_backtest_dataset_file(path: str) -> HistoricalDataset:
    dataset_path = Path(path)
    raw_bytes = dataset_path.read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(raw, dict) or "dataset_id" not in raw or "instruments" not in raw:
        raise ValueError(
            "dataset file must contain a JSON object with dataset metadata and an instruments array"
        )

    parsed_series = []
    for instrument_entry in raw["instruments"]:
        symbol = instrument_entry["instrument"]
        bars = tuple(_parse_bar(bar, instrument_symbol=symbol) for bar in instrument_entry["bars"])
        parsed_series.append(
            HistoricalInstrumentSeries(
                instrument=Instrument(symbol),
                bars=bars,
            )
        )
    ordered_series = tuple(sorted(parsed_series, key=lambda series: str(series.instrument)))
    first_bars = ordered_series[0].bars
    authority = HistoricalDatasetAuthority(
        dataset_id=DatasetId(raw["dataset_id"]),
        dataset_version=str(raw["dataset_version"]),
        source_kind=str(raw.get("source_kind", FIXED_TEST_UNIVERSE)),
        interval=ordered_series[0].interval,
        start_timestamp=first_bars[0].timestamp,
        end_timestamp=first_bars[-1].timestamp,
        total_bars=sum(len(series.bars) for series in ordered_series),
        instrument_count=len(ordered_series),
        sha256=dataset_sha256(raw_bytes),
    )
    return HistoricalDataset(authority=authority, series=ordered_series)


def historical_backtest_trade_payload(trade: object) -> dict[str, object]:
    typed_trade = cast(HistoricalBacktestTradePayloadView, trade)
    return {
        "trade_sequence": typed_trade.trade_sequence,
        "instrument": str(typed_trade.instrument),
        "evaluation_cutoff": typed_trade.evaluation_cutoff.isoformat(),
        "source_scan_reference": typed_trade.source_scan_reference,
        "source_decision_candidate_reference": typed_trade.source_decision_candidate_reference,
        "source_trade_plan_reference": typed_trade.source_trade_plan_reference,
        "source_position_plan_reference": typed_trade.source_position_plan_reference,
        "scan_rank": typed_trade.scan_rank,
        "ranking_score": str(typed_trade.ranking_score),
        "entry_timestamp": (
            typed_trade.entry_timestamp.isoformat()
            if typed_trade.entry_timestamp is not None
            else None
        ),
        "planned_entry_price": str(typed_trade.planned_entry_price),
        "simulated_entry_price": (
            str(typed_trade.simulated_entry_price)
            if typed_trade.simulated_entry_price is not None
            else None
        ),
        "planned_stop_price": str(typed_trade.planned_stop_price),
        "planned_target_price": str(typed_trade.planned_target_price),
        "exit_timestamp": (
            typed_trade.exit_timestamp.isoformat()
            if typed_trade.exit_timestamp is not None
            else None
        ),
        "exit_price": (str(typed_trade.exit_price) if typed_trade.exit_price is not None else None),
        "outcome": typed_trade.outcome.value,
        "ambiguity_policy": typed_trade.ambiguity_policy.value,
        "ambiguity_triggered": typed_trade.ambiguity_triggered,
        "quantity": typed_trade.quantity,
        "gross_pnl": str(typed_trade.gross_pnl),
        "transaction_costs": str(typed_trade.transaction_costs),
        "net_pnl": str(typed_trade.net_pnl),
        "risk_amount": str(typed_trade.risk_amount),
        "r_multiple": (str(typed_trade.r_multiple) if typed_trade.r_multiple is not None else None),
        "holding_bars": typed_trade.holding_bars,
    }


def historical_backtest_run_payload(run: object) -> dict[str, object]:
    typed_run = cast(HistoricalBacktestRunPayloadView, run)
    return {
        "governance_id": str(typed_run.identity.governance_id),
        "runtime_id": str(typed_run.identity.runtime_id),
        "dataset_id": str(typed_run.dataset_id),
        "dataset_version": typed_run.dataset_version,
        "dataset_source_kind": typed_run.dataset_source_kind,
        "dataset_sha256": typed_run.dataset_sha256,
        "interval": typed_run.interval.value,
        "universe": [str(instrument) for instrument in typed_run.universe],
        "dataset_start_timestamp": typed_run.dataset_start_timestamp.isoformat(),
        "dataset_end_timestamp": typed_run.dataset_end_timestamp.isoformat(),
        "dataset_total_bars": typed_run.dataset_total_bars,
        "reference_window_size": typed_run.reference_window_size,
        "decision_cadence": typed_run.decision_cadence,
        "strategy_id": typed_run.strategy_id,
        "strategy_version": typed_run.strategy_version,
        "ranking_model_id": typed_run.ranking_model_id,
        "ranking_model_version": typed_run.ranking_model_version,
        "risk_policy_id": typed_run.risk_policy_id,
        "risk_policy_version": typed_run.risk_policy_version,
        "risk_policy_target_projection_percent": str(
            typed_run.risk_policy_target_projection_percent
        ),
        "risk_policy_minimum_reward_risk_ratio": str(
            typed_run.risk_policy_minimum_reward_risk_ratio
        ),
        "sizing_policy_id": typed_run.sizing_policy_id,
        "sizing_policy_version": typed_run.sizing_policy_version,
        "sizing_policy_maximum_risk_percent": str(typed_run.sizing_policy_maximum_risk_percent),
        "sizing_policy_maximum_notional_percent": str(
            typed_run.sizing_policy_maximum_notional_percent
        ),
        "sizing_policy_allow_fractional_shares": typed_run.sizing_policy_allow_fractional_shares,
        "supplied_account_equity": str(typed_run.supplied_account_equity),
        "supplied_risk_percent": str(typed_run.supplied_risk_percent),
        "execution_assumption_id": typed_run.execution_assumption_id,
        "execution_assumption_version": typed_run.execution_assumption_version,
        "outcome_model_id": typed_run.outcome_model_id,
        "outcome_model_version": typed_run.outcome_model_version,
        "outcome_model_no_overnight": typed_run.outcome_model_no_overnight,
        "cost_model_id": typed_run.cost_model_id,
        "cost_model_version": typed_run.cost_model_version,
        "cost_model_entry_slippage_bps": str(typed_run.cost_model_entry_slippage_bps),
        "cost_model_exit_slippage_bps": str(typed_run.cost_model_exit_slippage_bps),
        "cost_model_fixed_commission_per_side": str(typed_run.cost_model_fixed_commission_per_side),
        "ambiguity_policy": typed_run.ambiguity_policy.value,
        "holding_horizon_bars": typed_run.holding_horizon_bars,
        "status": typed_run.status.value,
        "product_classification": typed_run.product_classification.value,
        "evaluated_cutoff_count": typed_run.evaluated_cutoff_count,
        "evaluated_opportunity_count": typed_run.evaluated_opportunity_count,
        "approved_trade_plan_count": typed_run.approved_trade_plan_count,
        "approved_position_plan_count": typed_run.approved_position_plan_count,
        "simulated_trade_count": typed_run.simulated_trade_count,
        "executed_trade_count": typed_run.executed_trade_count,
        "win_count": typed_run.win_count,
        "loss_count": typed_run.loss_count,
        "flat_count": typed_run.flat_count,
        "time_exit_count": typed_run.time_exit_count,
        "no_entry_count": typed_run.no_entry_count,
        "gross_pnl": str(typed_run.gross_pnl),
        "net_pnl": str(typed_run.net_pnl),
        "average_net_pnl": (
            str(typed_run.average_net_pnl) if typed_run.average_net_pnl is not None else None
        ),
        "average_r": str(typed_run.average_r) if typed_run.average_r is not None else None,
        "total_r": str(typed_run.total_r),
        "win_rate": str(typed_run.win_rate) if typed_run.win_rate is not None else None,
        "profit_factor": (
            str(typed_run.profit_factor) if typed_run.profit_factor is not None else None
        ),
        "maximum_realized_pnl_drawdown": (
            str(typed_run.maximum_realized_pnl_drawdown)
            if typed_run.maximum_realized_pnl_drawdown is not None
            else None
        ),
        "winning_trade_count": sum(
            1
            for trade in typed_run.trades
            if trade.outcome.value == HistoricalTradeOutcome.TARGET_HIT.value
        ),
        "trades": [historical_backtest_trade_payload(trade) for trade in typed_run.trades],
    }
