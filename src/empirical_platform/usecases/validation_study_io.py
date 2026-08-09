"""Usecase-layer parsing and serialization helpers for MILESTONE-062."""

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
from empirical_platform.decision_candidate.validation_study import (
    ValidationDatasetBundle,
    ValidationDatasetBundleAuthority,
    ValidationSegmentRole,
    ValidationSegmentSpec,
)
from empirical_platform.identifiers.types import DatasetId


class _ValueEnumView(Protocol):
    value: str


class ValidationSegmentResultPayloadView(Protocol):
    segment: object
    backtest_run_id: object
    backtest_run_runtime_id: object
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


class HistoricalValidationStudyPayloadView(Protocol):
    identity: object
    dataset_bundle_id: object
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
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
    survivorship_bias_disclosure: str
    status: _ValueEnumView
    classification: _ValueEnumView
    development: ValidationSegmentResultPayloadView
    holdout_1: ValidationSegmentResultPayloadView
    holdout_2: ValidationSegmentResultPayloadView
    holdout_1_net_pnl_delta: Decimal
    holdout_1_total_r_delta: Decimal
    holdout_2_net_pnl_delta: Decimal
    holdout_2_total_r_delta: Decimal


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


def parse_validation_dataset_bundle_file(
    path: str, *, expected_sha256: str
) -> ValidationDatasetBundle:
    """Load a multi-period dataset bundle, refusing to proceed if the file's
    own content does not match the caller-declared `expected_sha256` --
    tamper detection happens before any parsing or study construction is
    attempted (MILESTONE-062 Phase 15)."""
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
            "segments, and an instruments array"
        )

    parsed_series = []
    for instrument_entry in raw["instruments"]:
        symbol = instrument_entry["instrument"]
        bars = tuple(_parse_bar(bar, instrument_symbol=symbol) for bar in instrument_entry["bars"])
        parsed_series.append(HistoricalInstrumentSeries(instrument=Instrument(symbol), bars=bars))
    ordered_series = tuple(sorted(parsed_series, key=lambda series: str(series.instrument)))

    segment_specs = tuple(
        ValidationSegmentSpec(
            segment_id=entry["segment_id"],
            role=ValidationSegmentRole(entry["role"]),
            warmup_bar_count=int(entry["warmup_bar_count"]),
            scoring_bar_count=int(entry["scoring_bar_count"]),
            buffer_bar_count=int(entry["buffer_bar_count"]),
        )
        for entry in raw["segments"]
    )

    authority = ValidationDatasetBundleAuthority(
        dataset_bundle_id=DatasetId(raw["dataset_bundle_id"]),
        dataset_bundle_version=str(raw["dataset_bundle_version"]),
        source_kind=str(raw["source_kind"]),
        sha256=actual_sha256,
        interval=ordered_series[0].interval,
        instrument_count=len(ordered_series),
        total_bars_per_instrument=len(ordered_series[0].bars),
    )
    return ValidationDatasetBundle(
        authority=authority, segment_specs=segment_specs, series=ordered_series
    )


def _segment_result_payload(result: object) -> dict[str, object]:
    typed = cast(ValidationSegmentResultPayloadView, result)
    segment = typed.segment
    return {
        "segment_id": segment.segment_id,  # type: ignore[attr-defined]
        "role": segment.role.value,  # type: ignore[attr-defined]
        "data_start_timestamp": segment.data_start_timestamp.isoformat(),  # type: ignore[attr-defined]
        "data_end_timestamp": segment.data_end_timestamp.isoformat(),  # type: ignore[attr-defined]
        "scoring_start_timestamp": segment.scoring_start_timestamp.isoformat(),  # type: ignore[attr-defined]
        "scoring_end_timestamp": segment.scoring_end_timestamp.isoformat(),  # type: ignore[attr-defined]
        "warmup_bar_count": segment.warmup_bar_count,  # type: ignore[attr-defined]
        "scoring_bar_count": segment.scoring_bar_count,  # type: ignore[attr-defined]
        "buffer_bar_count": segment.buffer_bar_count,  # type: ignore[attr-defined]
        "backtest_run_id": str(typed.backtest_run_id),
        "backtest_run_runtime_id": str(typed.backtest_run_runtime_id),
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


def historical_validation_study_payload(study: object) -> dict[str, object]:
    typed = cast(HistoricalValidationStudyPayloadView, study)
    identity = typed.identity
    return {
        "governance_id": str(identity.governance_id),  # type: ignore[attr-defined]
        "runtime_id": str(identity.runtime_id),  # type: ignore[attr-defined]
        "dataset_bundle_id": str(typed.dataset_bundle_id),
        "dataset_bundle_version": typed.dataset_bundle_version,
        "dataset_bundle_sha256": typed.dataset_bundle_sha256,
        "dataset_source_kind": typed.dataset_source_kind,
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
        "survivorship_bias_disclosure": typed.survivorship_bias_disclosure,
        "status": typed.status.value,
        "classification": typed.classification.value,
        "development": _segment_result_payload(typed.development),
        "holdout_1": _segment_result_payload(typed.holdout_1),
        "holdout_2": _segment_result_payload(typed.holdout_2),
        "holdout_1_net_pnl_delta": str(typed.holdout_1_net_pnl_delta),
        "holdout_1_total_r_delta": str(typed.holdout_1_total_r_delta),
        "holdout_2_net_pnl_delta": str(typed.holdout_2_net_pnl_delta),
        "holdout_2_total_r_delta": str(typed.holdout_2_total_r_delta),
    }
