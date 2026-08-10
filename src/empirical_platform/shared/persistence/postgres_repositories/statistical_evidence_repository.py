"""Concrete PostgreSQL repository for M066 statistical evidence
reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.statistical_evidence import (
    BootstrapInterval,
    BootstrapMethod,
    BootstrapPolicy,
    DrawdownPathEvidence,
    SensitivityLabel,
    SensitivityView,
    StatisticalEvidenceClassification,
    StatisticalEvidenceReport,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import StatisticalEvidenceReportId
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_REPORT_KIND = "StatisticalEvidenceReport"
_REPORT_UNIQUE_CONSTRAINTS = {
    "pk_statistical_evidence_report",
    "uq_statistical_evidence_report_governance_id",
}


class PostgresStatisticalEvidenceReportRepository:
    """Concrete, storage-aware repository for immutable statistical
    evidence reports, persisted across `statistical_evidence_report`,
    `statistical_evidence_bootstrap_interval`, and
    `statistical_evidence_sensitivity`."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(
        self, identity: DomainIdentity[StatisticalEvidenceReportId]
    ) -> StatisticalEvidenceReport:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM statistical_evidence_report "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                raise AggregateNotFound(aggregate_kind=_REPORT_KIND, identity=identity)
            interval_rows = work.execute(
                "SELECT * FROM statistical_evidence_bootstrap_interval "
                "WHERE report_runtime_id = :runtime_id ORDER BY metric_name",
                {"runtime_id": str(identity.runtime_id)},
            )
            sensitivity_rows = work.execute(
                "SELECT * FROM statistical_evidence_sensitivity "
                "WHERE report_runtime_id = :runtime_id ORDER BY label",
                {"runtime_id": str(identity.runtime_id)},
            )
        return _row_to_report(rows[0], interval_rows, sensitivity_rows)

    def add(self, report: StatisticalEvidenceReport) -> None:
        report_insert_sql = (
            "INSERT INTO statistical_evidence_report ("
            "runtime_id, governance_id, source_study_governance_id, source_study_runtime_id, "
            "dataset_bundle_id, dataset_bundle_version, dataset_bundle_sha256, "
            "dataset_source_kind, universe_id, universe_version, membership_manifest_hash, "
            "strategy_id, strategy_version, ranking_model_id, ranking_model_version, "
            "risk_policy_id, risk_policy_version, sizing_policy_id, sizing_policy_version, "
            "trade_sample_size, window_sample_size, winning_trades, losing_trades, win_rate, "
            "net_pnl, total_r, mean_r_per_trade, median_r_per_trade, r_standard_deviation, "
            "best_trade_r, worst_trade_r, largest_trade_share_of_positive_pnl, profit_factor, "
            "positive_windows, negative_windows, median_window_net_pnl, median_window_total_r, "
            "bootstrap_policy_id, bootstrap_policy_version, bootstrap_method, "
            "bootstrap_resample_count, bootstrap_seed, bootstrap_confidence_level, "
            "historical_realized_max_drawdown, median_resampled_max_drawdown, "
            "upper_tail_resampled_max_drawdown, worst_resampled_max_drawdown, classification, "
            "limitations"
            ") VALUES ("
            ":runtime_id, :governance_id, :source_study_governance_id, :source_study_runtime_id, "
            ":dataset_bundle_id, :dataset_bundle_version, :dataset_bundle_sha256, "
            ":dataset_source_kind, :universe_id, :universe_version, :membership_manifest_hash, "
            ":strategy_id, :strategy_version, :ranking_model_id, :ranking_model_version, "
            ":risk_policy_id, :risk_policy_version, :sizing_policy_id, :sizing_policy_version, "
            ":trade_sample_size, :window_sample_size, :winning_trades, :losing_trades, "
            ":win_rate, :net_pnl, :total_r, :mean_r_per_trade, :median_r_per_trade, "
            ":r_standard_deviation, :best_trade_r, :worst_trade_r, "
            ":largest_trade_share_of_positive_pnl, :profit_factor, :positive_windows, "
            ":negative_windows, :median_window_net_pnl, :median_window_total_r, "
            ":bootstrap_policy_id, :bootstrap_policy_version, :bootstrap_method, "
            ":bootstrap_resample_count, :bootstrap_seed, :bootstrap_confidence_level, "
            ":historical_realized_max_drawdown, :median_resampled_max_drawdown, "
            ":upper_tail_resampled_max_drawdown, :worst_resampled_max_drawdown, "
            ":classification, :limitations"
            ")"
        )
        interval_insert_sql = (
            "INSERT INTO statistical_evidence_bootstrap_interval ("
            "report_runtime_id, metric_name, confidence_level, lower_bound, point_estimate, "
            "upper_bound, sample_size, resample_count, seed, method, policy_version"
            ") VALUES ("
            ":report_runtime_id, :metric_name, :confidence_level, :lower_bound, "
            ":point_estimate, :upper_bound, :sample_size, :resample_count, :seed, :method, "
            ":policy_version"
            ")"
        )
        sensitivity_insert_sql = (
            "INSERT INTO statistical_evidence_sensitivity ("
            "report_runtime_id, label, sample_size, net_pnl, total_r, mean_r"
            ") VALUES ("
            ":report_runtime_id, :label, :sample_size, :net_pnl, :total_r, :mean_r"
            ")"
        )
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    report_insert_sql,
                    {
                        "runtime_id": str(report.identity.runtime_id),
                        "governance_id": str(report.identity.governance_id),
                        "source_study_governance_id": report.source_study_governance_id,
                        "source_study_runtime_id": report.source_study_runtime_id,
                        "dataset_bundle_id": report.dataset_bundle_id,
                        "dataset_bundle_version": report.dataset_bundle_version,
                        "dataset_bundle_sha256": report.dataset_bundle_sha256,
                        "dataset_source_kind": report.dataset_source_kind,
                        "universe_id": report.universe_id,
                        "universe_version": report.universe_version,
                        "membership_manifest_hash": report.membership_manifest_hash,
                        "strategy_id": report.strategy_id,
                        "strategy_version": report.strategy_version,
                        "ranking_model_id": report.ranking_model_id,
                        "ranking_model_version": report.ranking_model_version,
                        "risk_policy_id": report.risk_policy_id,
                        "risk_policy_version": report.risk_policy_version,
                        "sizing_policy_id": report.sizing_policy_id,
                        "sizing_policy_version": report.sizing_policy_version,
                        "trade_sample_size": report.trade_sample_size,
                        "window_sample_size": report.window_sample_size,
                        "winning_trades": report.winning_trades,
                        "losing_trades": report.losing_trades,
                        "win_rate": report.win_rate,
                        "net_pnl": report.net_pnl,
                        "total_r": report.total_r,
                        "mean_r_per_trade": report.mean_r_per_trade,
                        "median_r_per_trade": report.median_r_per_trade,
                        "r_standard_deviation": report.r_standard_deviation,
                        "best_trade_r": report.best_trade_r,
                        "worst_trade_r": report.worst_trade_r,
                        "largest_trade_share_of_positive_pnl": (
                            report.largest_trade_share_of_positive_pnl
                        ),
                        "profit_factor": report.profit_factor,
                        "positive_windows": report.positive_windows,
                        "negative_windows": report.negative_windows,
                        "median_window_net_pnl": report.median_window_net_pnl,
                        "median_window_total_r": report.median_window_total_r,
                        "bootstrap_policy_id": report.bootstrap_policy.policy_id,
                        "bootstrap_policy_version": report.bootstrap_policy.version,
                        "bootstrap_method": report.bootstrap_policy.method.value,
                        "bootstrap_resample_count": report.bootstrap_policy.resample_count,
                        "bootstrap_seed": report.bootstrap_policy.seed,
                        "bootstrap_confidence_level": report.bootstrap_policy.confidence_level,
                        "historical_realized_max_drawdown": (
                            report.drawdown_path_evidence.historical_realized_max_drawdown
                        ),
                        "median_resampled_max_drawdown": (
                            report.drawdown_path_evidence.median_resampled_max_drawdown
                        ),
                        "upper_tail_resampled_max_drawdown": (
                            report.drawdown_path_evidence.upper_tail_resampled_max_drawdown
                        ),
                        "worst_resampled_max_drawdown": (
                            report.drawdown_path_evidence.worst_resampled_max_drawdown
                        ),
                        "classification": report.classification.value,
                        "limitations": list(report.limitations),
                    },
                )
                intervals = [
                    report.mean_r_interval,
                    report.median_r_interval,
                    report.aggregate_r_interval,
                ]
                if report.window_level_interval is not None:
                    intervals.append(report.window_level_interval)
                for interval in intervals:
                    work.execute(
                        interval_insert_sql,
                        {
                            "report_runtime_id": str(report.identity.runtime_id),
                            "metric_name": interval.metric_name,
                            "confidence_level": interval.confidence_level,
                            "lower_bound": interval.lower_bound,
                            "point_estimate": interval.point_estimate,
                            "upper_bound": interval.upper_bound,
                            "sample_size": interval.sample_size,
                            "resample_count": interval.resample_count,
                            "seed": interval.seed,
                            "method": interval.method.value,
                            "policy_version": interval.policy_version,
                        },
                    )
                for view in report.sensitivity_views:
                    work.execute(
                        sensitivity_insert_sql,
                        {
                            "report_runtime_id": str(report.identity.runtime_id),
                            "label": view.label.value,
                            "sample_size": view.sample_size,
                            "net_pnl": view.net_pnl,
                            "total_r": view.total_r,
                            "mean_r": view.mean_r,
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _REPORT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_REPORT_KIND, identity=report.identity
                    ) from exc
                raise


def _row_to_interval(row: Mapping[str, Any]) -> BootstrapInterval:
    return BootstrapInterval(
        metric_name=str(row["metric_name"]),
        confidence_level=cast(Decimal, row["confidence_level"]),
        lower_bound=cast(Decimal, row["lower_bound"]),
        point_estimate=cast(Decimal, row["point_estimate"]),
        upper_bound=cast(Decimal, row["upper_bound"]),
        sample_size=int(row["sample_size"]),
        resample_count=int(row["resample_count"]),
        seed=int(row["seed"]),
        method=BootstrapMethod(str(row["method"])),
        policy_version=str(row["policy_version"]),
    )


def _row_to_sensitivity(row: Mapping[str, Any]) -> SensitivityView:
    return SensitivityView(
        label=SensitivityLabel(str(row["label"])),
        sample_size=int(row["sample_size"]),
        net_pnl=cast(Decimal, row["net_pnl"]),
        total_r=cast(Decimal, row["total_r"]),
        mean_r=cast(Decimal | None, row["mean_r"]),
    )


def _row_to_report(
    row: Mapping[str, Any],
    interval_rows: Sequence[Mapping[str, Any]],
    sensitivity_rows: Sequence[Mapping[str, Any]],
) -> StatisticalEvidenceReport:
    intervals = {str(r["metric_name"]): _row_to_interval(r) for r in interval_rows}
    bootstrap_policy = BootstrapPolicy(
        policy_id=str(row["bootstrap_policy_id"]),
        version=str(row["bootstrap_policy_version"]),
        method=BootstrapMethod(str(row["bootstrap_method"])),
        resample_count=int(row["bootstrap_resample_count"]),
        seed=int(row["bootstrap_seed"]),
        confidence_level=cast(Decimal, row["bootstrap_confidence_level"]),
    )
    return StatisticalEvidenceReport(
        identity=DomainIdentity(
            governance_id=StatisticalEvidenceReportId(str(row["governance_id"])),
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
        trade_sample_size=int(row["trade_sample_size"]),
        window_sample_size=int(row["window_sample_size"]),
        winning_trades=int(row["winning_trades"]),
        losing_trades=int(row["losing_trades"]),
        win_rate=cast("Decimal | None", row["win_rate"]),
        net_pnl=cast(Decimal, row["net_pnl"]),
        total_r=cast(Decimal, row["total_r"]),
        mean_r_per_trade=cast("Decimal | None", row["mean_r_per_trade"]),
        median_r_per_trade=cast("Decimal | None", row["median_r_per_trade"]),
        r_standard_deviation=cast("Decimal | None", row["r_standard_deviation"]),
        best_trade_r=cast("Decimal | None", row["best_trade_r"]),
        worst_trade_r=cast("Decimal | None", row["worst_trade_r"]),
        largest_trade_share_of_positive_pnl=cast(
            "Decimal | None", row["largest_trade_share_of_positive_pnl"]
        ),
        profit_factor=cast("Decimal | None", row["profit_factor"]),
        positive_windows=int(row["positive_windows"]),
        negative_windows=int(row["negative_windows"]),
        median_window_net_pnl=cast("Decimal | None", row["median_window_net_pnl"]),
        median_window_total_r=cast("Decimal | None", row["median_window_total_r"]),
        bootstrap_policy=bootstrap_policy,
        mean_r_interval=intervals["mean_r_per_trade"],
        median_r_interval=intervals["median_r_per_trade"],
        aggregate_r_interval=intervals["aggregate_r"],
        window_level_interval=intervals.get("window_total_r"),
        sensitivity_views=tuple(_row_to_sensitivity(r) for r in sensitivity_rows),
        drawdown_path_evidence=DrawdownPathEvidence(
            historical_realized_max_drawdown=cast(Decimal, row["historical_realized_max_drawdown"]),
            median_resampled_max_drawdown=cast(Decimal, row["median_resampled_max_drawdown"]),
            upper_tail_resampled_max_drawdown=cast(
                Decimal, row["upper_tail_resampled_max_drawdown"]
            ),
            worst_resampled_max_drawdown=cast(Decimal, row["worst_resampled_max_drawdown"]),
            resample_count=int(row["bootstrap_resample_count"]),
            seed=int(row["bootstrap_seed"]),
        ),
        classification=StatisticalEvidenceClassification(str(row["classification"])),
        limitations=tuple(row["limitations"]),
    )
