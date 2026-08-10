"""Usecase-layer JSON serialization helpers for MILESTONE-066."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, cast

__all__ = ["statistical_evidence_report_payload"]


class _BootstrapPolicyView(Protocol):
    policy_id: str
    version: str
    resample_count: int
    seed: int
    confidence_level: Decimal

    @property
    def method(self) -> object: ...


class _BootstrapIntervalView(Protocol):
    metric_name: str
    confidence_level: Decimal
    lower_bound: Decimal
    point_estimate: Decimal
    upper_bound: Decimal
    sample_size: int
    resample_count: int
    seed: int
    policy_version: str

    @property
    def method(self) -> object: ...


class _SensitivityViewView(Protocol):
    sample_size: int
    net_pnl: Decimal
    total_r: Decimal
    mean_r: Decimal | None

    @property
    def label(self) -> object: ...


class _DrawdownPathEvidenceView(Protocol):
    historical_realized_max_drawdown: Decimal
    median_resampled_max_drawdown: Decimal
    upper_tail_resampled_max_drawdown: Decimal
    worst_resampled_max_drawdown: Decimal
    resample_count: int
    seed: int


class StatisticalEvidenceReportPayloadView(Protocol):
    identity: object
    source_study_governance_id: str
    source_study_runtime_id: str
    dataset_bundle_id: str
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    universe_id: str
    universe_version: str
    membership_manifest_hash: str
    strategy_id: str
    strategy_version: str
    ranking_model_id: str
    ranking_model_version: str
    risk_policy_id: str
    risk_policy_version: str
    sizing_policy_id: str
    sizing_policy_version: str
    trade_sample_size: int
    window_sample_size: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal | None
    net_pnl: Decimal
    total_r: Decimal
    mean_r_per_trade: Decimal | None
    median_r_per_trade: Decimal | None
    r_standard_deviation: Decimal | None
    best_trade_r: Decimal | None
    worst_trade_r: Decimal | None
    largest_trade_share_of_positive_pnl: Decimal | None
    profit_factor: Decimal | None
    positive_windows: int
    negative_windows: int
    median_window_net_pnl: Decimal | None
    median_window_total_r: Decimal | None
    bootstrap_policy: _BootstrapPolicyView
    mean_r_interval: _BootstrapIntervalView
    median_r_interval: _BootstrapIntervalView
    aggregate_r_interval: _BootstrapIntervalView
    window_level_interval: _BootstrapIntervalView | None
    sensitivity_views: tuple[_SensitivityViewView, ...]
    drawdown_path_evidence: _DrawdownPathEvidenceView
    limitations: tuple[str, ...]

    @property
    def classification(self) -> object: ...


def _interval_payload(interval: _BootstrapIntervalView) -> dict[str, object]:
    return {
        "metric_name": interval.metric_name,
        "confidence_level": str(interval.confidence_level),
        "lower_bound": str(interval.lower_bound),
        "point_estimate": str(interval.point_estimate),
        "upper_bound": str(interval.upper_bound),
        "sample_size": interval.sample_size,
        "resample_count": interval.resample_count,
        "seed": interval.seed,
        "method": cast("_ValueEnumView", interval.method).value,
        "policy_version": interval.policy_version,
    }


class _ValueEnumView(Protocol):
    value: str


def statistical_evidence_report_payload(report: object) -> dict[str, object]:
    typed = cast(StatisticalEvidenceReportPayloadView, report)
    identity = typed.identity
    return {
        "governance_id": str(identity.governance_id),  # type: ignore[attr-defined]
        "runtime_id": str(identity.runtime_id),  # type: ignore[attr-defined]
        "source_study_governance_id": typed.source_study_governance_id,
        "source_study_runtime_id": typed.source_study_runtime_id,
        "dataset_bundle_id": typed.dataset_bundle_id,
        "dataset_bundle_version": typed.dataset_bundle_version,
        "dataset_bundle_sha256": typed.dataset_bundle_sha256,
        "dataset_source_kind": typed.dataset_source_kind,
        "universe_id": typed.universe_id,
        "universe_version": typed.universe_version,
        "membership_manifest_hash": typed.membership_manifest_hash,
        "strategy_id": typed.strategy_id,
        "strategy_version": typed.strategy_version,
        "ranking_model_id": typed.ranking_model_id,
        "ranking_model_version": typed.ranking_model_version,
        "risk_policy_id": typed.risk_policy_id,
        "risk_policy_version": typed.risk_policy_version,
        "sizing_policy_id": typed.sizing_policy_id,
        "sizing_policy_version": typed.sizing_policy_version,
        "trade_sample_size": typed.trade_sample_size,
        "window_sample_size": typed.window_sample_size,
        "winning_trades": typed.winning_trades,
        "losing_trades": typed.losing_trades,
        "win_rate": str(typed.win_rate) if typed.win_rate is not None else None,
        "net_pnl": str(typed.net_pnl),
        "total_r": str(typed.total_r),
        "mean_r_per_trade": (
            str(typed.mean_r_per_trade) if typed.mean_r_per_trade is not None else None
        ),
        "median_r_per_trade": (
            str(typed.median_r_per_trade) if typed.median_r_per_trade is not None else None
        ),
        "r_standard_deviation": (
            str(typed.r_standard_deviation) if typed.r_standard_deviation is not None else None
        ),
        "best_trade_r": str(typed.best_trade_r) if typed.best_trade_r is not None else None,
        "worst_trade_r": str(typed.worst_trade_r) if typed.worst_trade_r is not None else None,
        "largest_trade_share_of_positive_pnl": (
            str(typed.largest_trade_share_of_positive_pnl)
            if typed.largest_trade_share_of_positive_pnl is not None
            else None
        ),
        "profit_factor": str(typed.profit_factor) if typed.profit_factor is not None else None,
        "positive_windows": typed.positive_windows,
        "negative_windows": typed.negative_windows,
        "median_window_net_pnl": (
            str(typed.median_window_net_pnl) if typed.median_window_net_pnl is not None else None
        ),
        "median_window_total_r": (
            str(typed.median_window_total_r) if typed.median_window_total_r is not None else None
        ),
        "bootstrap_policy": {
            "policy_id": typed.bootstrap_policy.policy_id,
            "version": typed.bootstrap_policy.version,
            "method": cast(_ValueEnumView, typed.bootstrap_policy.method).value,
            "resample_count": typed.bootstrap_policy.resample_count,
            "seed": typed.bootstrap_policy.seed,
            "confidence_level": str(typed.bootstrap_policy.confidence_level),
        },
        "mean_r_interval": _interval_payload(typed.mean_r_interval),
        "median_r_interval": _interval_payload(typed.median_r_interval),
        "aggregate_r_interval": _interval_payload(typed.aggregate_r_interval),
        "window_level_interval": (
            _interval_payload(typed.window_level_interval)
            if typed.window_level_interval is not None
            else None
        ),
        "sensitivity_views": [
            {
                "label": cast(_ValueEnumView, view.label).value,
                "sample_size": view.sample_size,
                "net_pnl": str(view.net_pnl),
                "total_r": str(view.total_r),
                "mean_r": str(view.mean_r) if view.mean_r is not None else None,
            }
            for view in typed.sensitivity_views
        ],
        "drawdown_path_evidence": {
            "historical_realized_max_drawdown": str(
                typed.drawdown_path_evidence.historical_realized_max_drawdown
            ),
            "median_resampled_max_drawdown": str(
                typed.drawdown_path_evidence.median_resampled_max_drawdown
            ),
            "upper_tail_resampled_max_drawdown": str(
                typed.drawdown_path_evidence.upper_tail_resampled_max_drawdown
            ),
            "worst_resampled_max_drawdown": str(
                typed.drawdown_path_evidence.worst_resampled_max_drawdown
            ),
            "resample_count": typed.drawdown_path_evidence.resample_count,
            "seed": typed.drawdown_path_evidence.seed,
        },
        "classification": cast(_ValueEnumView, typed.classification).value,
        "limitations": list(typed.limitations),
    }
