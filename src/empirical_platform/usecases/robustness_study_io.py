"""Usecase-layer parsing and serialization helpers for MILESTONE-063."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

from empirical_platform.decision_candidate.historical_backtest import (
    HistoricalInstrumentSeries,
    dataset_sha256,
)
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.robustness_study import (
    RobustnessDatasetBundle,
    RobustnessDatasetBundleAuthority,
    RobustnessUniverseAuthority,
    RobustnessWindowSpec,
    regime_breakdown,
)
from empirical_platform.identifiers.types import DatasetId


class _ValueEnumView(Protocol):
    value: str


class RobustnessWindowResultPayloadView(Protocol):
    window: object
    backtest_run_id: object
    backtest_run_runtime_id: object
    regime_label: _ValueEnumView
    realized_volatility: Decimal
    evaluated_cutoff_count: int
    simulated_trade_count: int
    executed_trade_count: int
    win_count: int
    loss_count: int
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


class WindowExtremeView(Protocol):
    window_id: str
    value: Decimal


class HistoricalRobustnessStudyPayloadView(Protocol):
    identity: object
    dataset_bundle_id: object
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    universe_id: str
    universe_version: str
    universe_membership_model: str
    interval: _ValueEnumView
    instrument_universe: tuple[object, ...]
    reference_window_size: int
    strategy_id: str
    strategy_version: str
    ranking_model_id: str
    ranking_model_version: str
    risk_policy_id: str
    risk_policy_version: str
    sizing_policy_id: str
    sizing_policy_version: str
    execution_assumption_id: str
    execution_assumption_version: str
    outcome_model_id: str
    outcome_model_version: str
    cost_model_id: str
    cost_model_version: str
    holding_horizon_bars: int
    supplied_account_equity: Decimal
    supplied_risk_percent: Decimal
    regime_policy_id: str
    regime_policy_version: str
    survivorship_bias_disclosure: str
    status: _ValueEnumView
    classification: _ValueEnumView
    window_results: tuple[RobustnessWindowResultPayloadView, ...]
    window_count: int
    total_evaluated_cutoff_count: int
    total_simulated_trade_count: int
    total_executed_trade_count: int
    positive_net_pnl_window_count: int
    negative_net_pnl_window_count: int
    positive_total_r_window_count: int
    negative_total_r_window_count: int
    median_window_net_pnl: Decimal
    median_window_total_r: Decimal
    best_window_by_net_pnl: WindowExtremeView
    worst_window_by_net_pnl: WindowExtremeView
    best_window_by_total_r: WindowExtremeView
    worst_window_by_total_r: WindowExtremeView
    all_window_net_pnl_total: Decimal
    all_window_total_r_total: Decimal
    excluding_best_window_net_pnl_total: Decimal
    excluding_best_window_total_r_total: Decimal
    largest_positive_window_share_of_positive_pnl: Decimal | None
    largest_negative_window_share_of_absolute_negative_pnl: Decimal | None


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


def parse_robustness_dataset_bundle_file(
    path: str, *, expected_sha256: str
) -> RobustnessDatasetBundle:
    """Load a broad multi-window robustness dataset bundle, refusing to
    proceed if the file's own content does not match the caller-declared
    `expected_sha256` -- tamper detection happens before any parsing or
    study construction is attempted."""
    bundle_path = Path(path)
    raw_bytes = bundle_path.read_bytes()
    actual_sha256 = dataset_sha256(raw_bytes)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"dataset bundle tamper detected: expected sha256 {expected_sha256!r}, "
            f"got {actual_sha256!r}"
        )
    raw = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(raw, dict) or "dataset_bundle_id" not in raw or "instruments" not in raw:
        raise ValueError(
            "dataset bundle file must contain a JSON object with dataset_bundle_id, "
            "windows, and an instruments array"
        )

    parsed_series = []
    for instrument_entry in raw["instruments"]:
        symbol = instrument_entry["instrument"]
        bars = tuple(_parse_bar(bar, instrument_symbol=symbol) for bar in instrument_entry["bars"])
        parsed_series.append(HistoricalInstrumentSeries(instrument=Instrument(symbol), bars=bars))
    ordered_series = tuple(sorted(parsed_series, key=lambda series: str(series.instrument)))

    window_specs = tuple(
        RobustnessWindowSpec(
            window_id=entry["window_id"],
            sequence_index=int(entry["sequence_index"]),
            warmup_bar_count=int(entry["warmup_bar_count"]),
            scoring_bar_count=int(entry["scoring_bar_count"]),
            buffer_bar_count=int(entry["buffer_bar_count"]),
        )
        for entry in raw["windows"]
    )

    authority = RobustnessDatasetBundleAuthority(
        dataset_bundle_id=DatasetId(raw["dataset_bundle_id"]),
        dataset_bundle_version=str(raw["dataset_bundle_version"]),
        source_kind=str(raw["source_kind"]),
        sha256=actual_sha256,
        interval=ordered_series[0].interval,
        instrument_count=len(ordered_series),
        total_bars_per_instrument=len(ordered_series[0].bars),
    )
    universe_authority = RobustnessUniverseAuthority(
        universe_id=str(raw["universe_id"]),
        universe_version=str(raw["universe_version"]),
        membership_model=str(raw["universe_membership_model"]),
        constituents=tuple(Instrument(symbol) for symbol in raw["universe_constituents"]),
    )
    return RobustnessDatasetBundle(
        authority=authority,
        universe_authority=universe_authority,
        window_specs=window_specs,
        series=ordered_series,
    )


def _window_result_payload(result: object) -> dict[str, object]:
    typed = cast(RobustnessWindowResultPayloadView, result)
    window = typed.window
    return {
        "window_id": window.window_id,  # type: ignore[attr-defined]
        "sequence_index": window.sequence_index,  # type: ignore[attr-defined]
        "data_start_timestamp": window.data_start_timestamp.isoformat(),  # type: ignore[attr-defined]
        "data_end_timestamp": window.data_end_timestamp.isoformat(),  # type: ignore[attr-defined]
        "scoring_start_timestamp": window.scoring_start_timestamp.isoformat(),  # type: ignore[attr-defined]
        "scoring_end_timestamp": window.scoring_end_timestamp.isoformat(),  # type: ignore[attr-defined]
        "warmup_bar_count": window.warmup_bar_count,  # type: ignore[attr-defined]
        "scoring_bar_count": window.scoring_bar_count,  # type: ignore[attr-defined]
        "buffer_bar_count": window.buffer_bar_count,  # type: ignore[attr-defined]
        "backtest_run_id": str(typed.backtest_run_id),
        "backtest_run_runtime_id": str(typed.backtest_run_runtime_id),
        "regime_label": typed.regime_label.value,
        "realized_volatility": str(typed.realized_volatility),
        "evaluated_cutoff_count": typed.evaluated_cutoff_count,
        "simulated_trade_count": typed.simulated_trade_count,
        "executed_trade_count": typed.executed_trade_count,
        "win_count": typed.win_count,
        "loss_count": typed.loss_count,
        "time_exit_count": typed.time_exit_count,
        "no_entry_count": typed.no_entry_count,
        "gross_pnl": str(typed.gross_pnl),
        "net_pnl": str(typed.net_pnl),
        "average_net_pnl": (
            str(typed.average_net_pnl) if typed.average_net_pnl is not None else None
        ),
        "average_r": str(typed.average_r) if typed.average_r is not None else None,
        "total_r": str(typed.total_r),
        "win_rate": str(typed.win_rate) if typed.win_rate is not None else None,
        "profit_factor": (str(typed.profit_factor) if typed.profit_factor is not None else None),
        "maximum_realized_pnl_drawdown": (
            str(typed.maximum_realized_pnl_drawdown)
            if typed.maximum_realized_pnl_drawdown is not None
            else None
        ),
    }


def _extreme_payload(extreme: object) -> dict[str, object]:
    typed = cast(WindowExtremeView, extreme)
    return {"window_id": typed.window_id, "value": str(typed.value)}


def historical_robustness_study_payload(study: object) -> dict[str, object]:
    typed = cast(HistoricalRobustnessStudyPayloadView, study)
    identity = typed.identity
    breakdown = regime_breakdown(typed.window_results)  # type: ignore[arg-type]
    return {
        "governance_id": str(identity.governance_id),  # type: ignore[attr-defined]
        "runtime_id": str(identity.runtime_id),  # type: ignore[attr-defined]
        "dataset_bundle_id": str(typed.dataset_bundle_id),
        "dataset_bundle_version": typed.dataset_bundle_version,
        "dataset_bundle_sha256": typed.dataset_bundle_sha256,
        "dataset_source_kind": typed.dataset_source_kind,
        "universe_id": typed.universe_id,
        "universe_version": typed.universe_version,
        "universe_membership_model": typed.universe_membership_model,
        "interval": typed.interval.value,
        "instrument_universe": [str(instrument) for instrument in typed.instrument_universe],
        "reference_window_size": typed.reference_window_size,
        "strategy_id": typed.strategy_id,
        "strategy_version": typed.strategy_version,
        "ranking_model_id": typed.ranking_model_id,
        "ranking_model_version": typed.ranking_model_version,
        "risk_policy_id": typed.risk_policy_id,
        "risk_policy_version": typed.risk_policy_version,
        "sizing_policy_id": typed.sizing_policy_id,
        "sizing_policy_version": typed.sizing_policy_version,
        "execution_assumption_id": typed.execution_assumption_id,
        "execution_assumption_version": typed.execution_assumption_version,
        "outcome_model_id": typed.outcome_model_id,
        "outcome_model_version": typed.outcome_model_version,
        "cost_model_id": typed.cost_model_id,
        "cost_model_version": typed.cost_model_version,
        "holding_horizon_bars": typed.holding_horizon_bars,
        "supplied_account_equity": str(typed.supplied_account_equity),
        "supplied_risk_percent": str(typed.supplied_risk_percent),
        "regime_policy_id": typed.regime_policy_id,
        "regime_policy_version": typed.regime_policy_version,
        "survivorship_bias_disclosure": typed.survivorship_bias_disclosure,
        "status": typed.status.value,
        "classification": typed.classification.value,
        "window_count": typed.window_count,
        "total_evaluated_cutoff_count": typed.total_evaluated_cutoff_count,
        "total_simulated_trade_count": typed.total_simulated_trade_count,
        "total_executed_trade_count": typed.total_executed_trade_count,
        "positive_net_pnl_window_count": typed.positive_net_pnl_window_count,
        "negative_net_pnl_window_count": typed.negative_net_pnl_window_count,
        "positive_total_r_window_count": typed.positive_total_r_window_count,
        "negative_total_r_window_count": typed.negative_total_r_window_count,
        "median_window_net_pnl": str(typed.median_window_net_pnl),
        "median_window_total_r": str(typed.median_window_total_r),
        "best_window_by_net_pnl": _extreme_payload(typed.best_window_by_net_pnl),
        "worst_window_by_net_pnl": _extreme_payload(typed.worst_window_by_net_pnl),
        "best_window_by_total_r": _extreme_payload(typed.best_window_by_total_r),
        "worst_window_by_total_r": _extreme_payload(typed.worst_window_by_total_r),
        "all_window_net_pnl_total": str(typed.all_window_net_pnl_total),
        "all_window_total_r_total": str(typed.all_window_total_r_total),
        "excluding_best_window_net_pnl_total": str(typed.excluding_best_window_net_pnl_total),
        "excluding_best_window_total_r_total": str(typed.excluding_best_window_total_r_total),
        "largest_positive_window_share_of_positive_pnl": (
            str(typed.largest_positive_window_share_of_positive_pnl)
            if typed.largest_positive_window_share_of_positive_pnl is not None
            else None
        ),
        "largest_negative_window_share_of_absolute_negative_pnl": (
            str(typed.largest_negative_window_share_of_absolute_negative_pnl)
            if typed.largest_negative_window_share_of_absolute_negative_pnl is not None
            else None
        ),
        "regime_breakdown": [
            {
                "regime_label": entry.regime_label.value,
                "window_count": entry.window_count,
                "executed_trade_count": entry.executed_trade_count,
                "net_pnl_total": str(entry.net_pnl_total),
                "total_r_total": str(entry.total_r_total),
                "positive_window_count": entry.positive_window_count,
                "negative_window_count": entry.negative_window_count,
            }
            for entry in breakdown
        ],
        "window_results": [_window_result_payload(result) for result in typed.window_results],
    }
