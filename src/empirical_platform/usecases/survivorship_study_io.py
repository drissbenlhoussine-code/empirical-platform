"""Usecase-layer parsing and serialization helpers for MILESTONE-064."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

from empirical_platform.decision_candidate.instrument_master import (
    InstrumentId,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentType,
)
from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.membership import (
    MembershipManifest,
    MembershipRecord,
    MembershipStatus,
    membership_manifest_hash,
)
from empirical_platform.decision_candidate.robustness_study import RobustnessDatasetBundle
from empirical_platform.usecases.robustness_study_io import (
    parse_robustness_dataset_bundle_file as parse_survivorship_dataset_bundle_file,
)

__all__ = [
    "RobustnessDatasetBundle",
    "parse_instrument_master_file",
    "parse_membership_manifest_file",
    "parse_survivorship_dataset_bundle_file",
    "survivorship_aware_robustness_study_payload",
]


def parse_instrument_master_file(path: str) -> InstrumentMaster:
    """Load the fixed local instrument-master fixture file. No tamper
    detection here -- the master itself contributes no domain state on its
    own (unlike the dataset bundle / membership manifest, which drive
    eligibility and results); it is validated structurally by
    `InstrumentMaster.__post_init__`."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = tuple(
        InstrumentMasterEntry(
            instrument_id=InstrumentId(entry["instrument_id"]),
            canonical_symbol=Instrument(entry["canonical_symbol"]),
            instrument_type=InstrumentType(entry["instrument_type"]),
            exchange_or_venue=entry.get("exchange_or_venue"),
            external_identifier=entry.get("external_identifier"),
        )
        for entry in raw["entries"]
    )
    return InstrumentMaster(entries=entries)


def parse_membership_manifest_file(path: str, *, expected_hash: str) -> MembershipManifest:
    """Load the fixed local membership-manifest fixture file, refusing to
    proceed if its own canonical hash does not match the caller-declared
    `expected_hash` -- tamper detection happens before any manifest object
    is constructed or used."""
    raw_bytes = Path(path).read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    records = tuple(
        MembershipRecord(
            universe_id=raw["universe_id"],
            universe_version=raw["universe_version"],
            instrument_id=InstrumentId(entry["instrument_id"]),
            effective_from=datetime.fromisoformat(entry["effective_from"]),
            effective_to=(
                datetime.fromisoformat(entry["effective_to"]) if entry.get("effective_to") else None
            ),
            membership_status=MembershipStatus(entry["membership_status"]),
            source_kind=entry["source_kind"],
        )
        for entry in raw["records"]
    )
    manifest = MembershipManifest(
        universe_id=raw["universe_id"], universe_version=raw["universe_version"], records=records
    )
    actual_hash = membership_manifest_hash(manifest)
    if actual_hash != expected_hash:
        raise ValueError(
            f"membership manifest tamper detected: expected hash {expected_hash!r}, "
            f"got {actual_hash!r}"
        )
    return manifest


class _ValueEnumView(Protocol):
    value: str


class _WindowUniverseSnapshotView(Protocol):
    window_id: str
    sequence_index: int
    universe_id: str
    universe_version: str
    membership_manifest_hash: str
    eligible_instrument_ids: tuple[object, ...]
    evaluated_instrument_ids: tuple[object, ...]
    missing_data_excluded_instrument_ids: tuple[object, ...]
    eligible_count: int
    evaluated_count: int


class _SurvivorshipWindowResultView(Protocol):
    snapshot: _WindowUniverseSnapshotView
    data_start_timestamp: datetime
    data_end_timestamp: datetime
    scoring_start_timestamp: datetime
    scoring_end_timestamp: datetime
    backtest_run_id: object | None
    backtest_run_runtime_id: object | None
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


class _WindowExtremeView(Protocol):
    window_id: str
    value: Decimal


class _BiasStressView(Protocol):
    stress_study_id: object
    comparison: _ValueEnumView
    full_universe_size: int
    canonical_total_executed_trade_count: int
    stress_total_executed_trade_count: int
    canonical_net_pnl_total: Decimal
    stress_net_pnl_total: Decimal
    canonical_total_r_total: Decimal
    stress_total_r_total: Decimal
    canonical_best_window_by_net_pnl: _WindowExtremeView
    stress_best_window_by_net_pnl: _WindowExtremeView
    canonical_worst_window_by_net_pnl: _WindowExtremeView
    stress_worst_window_by_net_pnl: _WindowExtremeView


class SurvivorshipAwareRobustnessStudyPayloadView(Protocol):
    identity: object
    dataset_bundle_id: object
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    universe_id: str
    universe_version: str
    universe_membership_model: str
    membership_manifest_hash: str
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
    corporate_action_handling: str
    status: _ValueEnumView
    classification: _ValueEnumView
    window_results: tuple[_SurvivorshipWindowResultView, ...]
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
    best_window_by_net_pnl: _WindowExtremeView
    worst_window_by_net_pnl: _WindowExtremeView
    best_window_by_total_r: _WindowExtremeView
    worst_window_by_total_r: _WindowExtremeView
    all_window_net_pnl_total: Decimal
    all_window_total_r_total: Decimal
    excluding_best_window_net_pnl_total: Decimal
    excluding_best_window_total_r_total: Decimal
    largest_positive_window_share_of_positive_pnl: Decimal | None
    largest_negative_window_share_of_absolute_negative_pnl: Decimal | None
    current_universe_bias_stress: _BiasStressView

    def stress_window_comparisons(self) -> tuple[object, ...]: ...


def _extreme_payload(extreme: object) -> dict[str, object]:
    typed = cast(_WindowExtremeView, extreme)
    return {"window_id": typed.window_id, "value": str(typed.value)}


def _snapshot_payload(snapshot: object) -> dict[str, object]:
    typed = cast(_WindowUniverseSnapshotView, snapshot)
    return {
        "window_id": typed.window_id,
        "sequence_index": typed.sequence_index,
        "universe_id": typed.universe_id,
        "universe_version": typed.universe_version,
        "membership_manifest_hash": typed.membership_manifest_hash,
        "eligible_instrument_ids": [str(iid) for iid in typed.eligible_instrument_ids],
        "evaluated_instrument_ids": [str(iid) for iid in typed.evaluated_instrument_ids],
        "missing_data_excluded_instrument_ids": [
            str(iid) for iid in typed.missing_data_excluded_instrument_ids
        ],
        "eligible_count": typed.eligible_count,
        "evaluated_count": typed.evaluated_count,
    }


def _window_result_payload(result: object) -> dict[str, object]:
    typed = cast(_SurvivorshipWindowResultView, result)
    return {
        "snapshot": _snapshot_payload(typed.snapshot),
        "data_start_timestamp": typed.data_start_timestamp.isoformat(),
        "data_end_timestamp": typed.data_end_timestamp.isoformat(),
        "scoring_start_timestamp": typed.scoring_start_timestamp.isoformat(),
        "scoring_end_timestamp": typed.scoring_end_timestamp.isoformat(),
        "backtest_run_id": (
            str(typed.backtest_run_id) if typed.backtest_run_id is not None else None
        ),
        "backtest_run_runtime_id": (
            str(typed.backtest_run_runtime_id)
            if typed.backtest_run_runtime_id is not None
            else None
        ),
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


def _bias_stress_payload(stress: object, comparisons: tuple[object, ...]) -> dict[str, object]:
    typed = cast(_BiasStressView, stress)

    def comparison_payload(entry: object) -> dict[str, object]:
        return {
            "window_id": entry.window_id,  # type: ignore[attr-defined]
            "canonical_eligible_count": entry.canonical_eligible_count,  # type: ignore[attr-defined]
            "canonical_evaluated_count": entry.canonical_evaluated_count,  # type: ignore[attr-defined]
            "stress_eligible_count": entry.stress_eligible_count,  # type: ignore[attr-defined]
            "stress_evaluated_count": entry.stress_evaluated_count,  # type: ignore[attr-defined]
        }

    return {
        "stress_study_id": str(typed.stress_study_id),
        "comparison": typed.comparison.value,
        "full_universe_size": typed.full_universe_size,
        "canonical_total_executed_trade_count": typed.canonical_total_executed_trade_count,
        "stress_total_executed_trade_count": typed.stress_total_executed_trade_count,
        "canonical_net_pnl_total": str(typed.canonical_net_pnl_total),
        "stress_net_pnl_total": str(typed.stress_net_pnl_total),
        "canonical_total_r_total": str(typed.canonical_total_r_total),
        "stress_total_r_total": str(typed.stress_total_r_total),
        "canonical_best_window_by_net_pnl": _extreme_payload(
            typed.canonical_best_window_by_net_pnl
        ),
        "stress_best_window_by_net_pnl": _extreme_payload(typed.stress_best_window_by_net_pnl),
        "canonical_worst_window_by_net_pnl": _extreme_payload(
            typed.canonical_worst_window_by_net_pnl
        ),
        "stress_worst_window_by_net_pnl": _extreme_payload(typed.stress_worst_window_by_net_pnl),
        "window_comparisons": [comparison_payload(entry) for entry in comparisons],
    }


def survivorship_aware_robustness_study_payload(study: object) -> dict[str, object]:
    typed = cast(SurvivorshipAwareRobustnessStudyPayloadView, study)
    identity = typed.identity
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
        "membership_manifest_hash": typed.membership_manifest_hash,
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
        "corporate_action_handling": typed.corporate_action_handling,
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
        "current_universe_bias_stress": _bias_stress_payload(
            typed.current_universe_bias_stress, typed.stress_window_comparisons()
        ),
        "window_results": [_window_result_payload(result) for result in typed.window_results],
    }
