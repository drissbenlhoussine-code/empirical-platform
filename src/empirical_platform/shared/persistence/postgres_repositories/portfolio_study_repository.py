"""Concrete PostgreSQL repository for M067 portfolio capital-allocation
evidence reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

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
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioStudyId
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_REPORT_KIND = "PortfolioEvidenceReport"
_REPORT_UNIQUE_CONSTRAINTS = {
    "pk_portfolio_study",
    "uq_portfolio_study_governance_id",
}


class PostgresPortfolioStudyRepository:
    """Concrete, storage-aware repository for immutable portfolio
    capital-allocation evidence reports, persisted across
    `portfolio_study`, `portfolio_allocation_decision`,
    `portfolio_equity_observation`, and `portfolio_capital_sensitivity`."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, identity: DomainIdentity[PortfolioStudyId]) -> PortfolioEvidenceReport:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM portfolio_study "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                raise AggregateNotFound(aggregate_kind=_REPORT_KIND, identity=identity)
            decision_rows = work.execute(
                "SELECT * FROM portfolio_allocation_decision "
                "WHERE report_runtime_id = :runtime_id ORDER BY opportunity_sequence",
                {"runtime_id": str(identity.runtime_id)},
            )
            equity_rows = work.execute(
                "SELECT * FROM portfolio_equity_observation "
                "WHERE report_runtime_id = :runtime_id ORDER BY sequence_index",
                {"runtime_id": str(identity.runtime_id)},
            )
            sensitivity_rows = work.execute(
                "SELECT * FROM portfolio_capital_sensitivity "
                "WHERE report_runtime_id = :runtime_id ORDER BY label",
                {"runtime_id": str(identity.runtime_id)},
            )
        return _row_to_report(rows[0], decision_rows, equity_rows, sensitivity_rows)

    def add(self, report: PortfolioEvidenceReport) -> None:
        report_insert_sql = (
            "INSERT INTO portfolio_study ("
            "runtime_id, governance_id, source_study_governance_id, source_study_runtime_id, "
            "dataset_bundle_id, dataset_bundle_version, dataset_bundle_sha256, "
            "dataset_source_kind, universe_id, universe_version, membership_manifest_hash, "
            "strategy_id, strategy_version, ranking_model_id, ranking_model_version, "
            "risk_policy_id, risk_policy_version, sizing_policy_id, sizing_policy_version, "
            "capital_policy_id, capital_policy_version, initial_capital, currency, "
            "max_concurrent_positions, max_capital_utilization_percent, total_opportunities, "
            "allocated_count, rejected_count, rejected_insufficient_capital_count, "
            "rejected_max_concurrent_count, rejected_max_utilization_count, ending_capital, "
            "realized_pnl, portfolio_return_percent, peak_equity, max_drawdown, "
            "max_drawdown_percent, max_concurrent_positions_observed, "
            "average_concurrent_positions, peak_occupied_capital, "
            "peak_capital_utilization_percent, largest_instrument_positive_contribution_symbol, "
            "largest_instrument_positive_contribution_amount, "
            "largest_instrument_negative_contribution_symbol, "
            "largest_instrument_negative_contribution_amount, "
            "largest_position_contribution_trade_sequence, largest_position_contribution_amount, "
            "largest_window_contribution_window_id, largest_window_contribution_amount"
            ") VALUES ("
            ":runtime_id, :governance_id, :source_study_governance_id, :source_study_runtime_id, "
            ":dataset_bundle_id, :dataset_bundle_version, :dataset_bundle_sha256, "
            ":dataset_source_kind, :universe_id, :universe_version, :membership_manifest_hash, "
            ":strategy_id, :strategy_version, :ranking_model_id, :ranking_model_version, "
            ":risk_policy_id, :risk_policy_version, :sizing_policy_id, :sizing_policy_version, "
            ":capital_policy_id, :capital_policy_version, :initial_capital, :currency, "
            ":max_concurrent_positions, :max_capital_utilization_percent, :total_opportunities, "
            ":allocated_count, :rejected_count, :rejected_insufficient_capital_count, "
            ":rejected_max_concurrent_count, :rejected_max_utilization_count, :ending_capital, "
            ":realized_pnl, :portfolio_return_percent, :peak_equity, :max_drawdown, "
            ":max_drawdown_percent, :max_concurrent_positions_observed, "
            ":average_concurrent_positions, :peak_occupied_capital, "
            ":peak_capital_utilization_percent, :largest_instrument_positive_contribution_symbol, "
            ":largest_instrument_positive_contribution_amount, "
            ":largest_instrument_negative_contribution_symbol, "
            ":largest_instrument_negative_contribution_amount, "
            ":largest_position_contribution_trade_sequence, "
            ":largest_position_contribution_amount, :largest_window_contribution_window_id, "
            ":largest_window_contribution_amount"
            ")"
        )
        decision_insert_sql = (
            "INSERT INTO portfolio_allocation_decision ("
            "report_runtime_id, opportunity_sequence, source_window_id, trade_sequence, "
            "instrument_symbol, scan_rank, entry_timestamp, exit_timestamp, risk_amount, "
            "net_pnl, decision, rejection_reason"
            ") VALUES ("
            ":report_runtime_id, :opportunity_sequence, :source_window_id, :trade_sequence, "
            ":instrument_symbol, :scan_rank, :entry_timestamp, :exit_timestamp, :risk_amount, "
            ":net_pnl, :decision, :rejection_reason"
            ")"
        )
        equity_insert_sql = (
            "INSERT INTO portfolio_equity_observation ("
            "report_runtime_id, sequence_index, event_timestamp, event_kind, equity, "
            "occupied_capital, available_capital, open_position_count"
            ") VALUES ("
            ":report_runtime_id, :sequence_index, :event_timestamp, :event_kind, :equity, "
            ":occupied_capital, :available_capital, :open_position_count"
            ")"
        )
        sensitivity_insert_sql = (
            "INSERT INTO portfolio_capital_sensitivity ("
            "report_runtime_id, label, capital_policy_id, initial_capital, "
            "max_concurrent_positions, allocated_count, rejected_count, ending_capital, "
            "realized_pnl, max_drawdown"
            ") VALUES ("
            ":report_runtime_id, :label, :capital_policy_id, :initial_capital, "
            ":max_concurrent_positions, :allocated_count, :rejected_count, :ending_capital, "
            ":realized_pnl, :max_drawdown"
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
                        "capital_policy_id": report.capital_policy.policy_id,
                        "capital_policy_version": report.capital_policy.version,
                        "initial_capital": report.initial_capital,
                        "currency": report.capital_policy.currency,
                        "max_concurrent_positions": report.capital_policy.max_concurrent_positions,
                        "max_capital_utilization_percent": (
                            report.capital_policy.max_capital_utilization_percent
                        ),
                        "total_opportunities": report.total_opportunities,
                        "allocated_count": report.allocated_count,
                        "rejected_count": report.rejected_count,
                        "rejected_insufficient_capital_count": (
                            report.rejected_insufficient_capital_count
                        ),
                        "rejected_max_concurrent_count": report.rejected_max_concurrent_count,
                        "rejected_max_utilization_count": report.rejected_max_utilization_count,
                        "ending_capital": report.ending_capital,
                        "realized_pnl": report.realized_pnl,
                        "portfolio_return_percent": report.portfolio_return_percent,
                        "peak_equity": report.peak_equity,
                        "max_drawdown": report.max_drawdown,
                        "max_drawdown_percent": report.max_drawdown_percent,
                        "max_concurrent_positions_observed": (
                            report.max_concurrent_positions_observed
                        ),
                        "average_concurrent_positions": report.average_concurrent_positions,
                        "peak_occupied_capital": report.peak_occupied_capital,
                        "peak_capital_utilization_percent": (
                            report.peak_capital_utilization_percent
                        ),
                        "largest_instrument_positive_contribution_symbol": (
                            report.largest_instrument_positive_contribution_symbol
                        ),
                        "largest_instrument_positive_contribution_amount": (
                            report.largest_instrument_positive_contribution_amount
                        ),
                        "largest_instrument_negative_contribution_symbol": (
                            report.largest_instrument_negative_contribution_symbol
                        ),
                        "largest_instrument_negative_contribution_amount": (
                            report.largest_instrument_negative_contribution_amount
                        ),
                        "largest_position_contribution_trade_sequence": (
                            report.largest_position_contribution_trade_sequence
                        ),
                        "largest_position_contribution_amount": (
                            report.largest_position_contribution_amount
                        ),
                        "largest_window_contribution_window_id": (
                            report.largest_window_contribution_window_id
                        ),
                        "largest_window_contribution_amount": (
                            report.largest_window_contribution_amount
                        ),
                    },
                )
                for decision in report.allocation_decisions:
                    work.execute(
                        decision_insert_sql,
                        {
                            "report_runtime_id": str(report.identity.runtime_id),
                            "opportunity_sequence": decision.opportunity_sequence,
                            "source_window_id": decision.source_window_id,
                            "trade_sequence": decision.trade_sequence,
                            "instrument_symbol": decision.instrument_symbol,
                            "scan_rank": decision.scan_rank,
                            "entry_timestamp": decision.entry_timestamp,
                            "exit_timestamp": decision.exit_timestamp,
                            "risk_amount": decision.risk_amount,
                            "net_pnl": decision.net_pnl,
                            "decision": decision.decision.value,
                            "rejection_reason": (
                                decision.rejection_reason.value
                                if decision.rejection_reason is not None
                                else None
                            ),
                        },
                    )
                for point in report.equity_curve:
                    work.execute(
                        equity_insert_sql,
                        {
                            "report_runtime_id": str(report.identity.runtime_id),
                            "sequence_index": point.sequence_index,
                            "event_timestamp": point.event_timestamp,
                            "event_kind": point.event_kind.value,
                            "equity": point.equity,
                            "occupied_capital": point.occupied_capital,
                            "available_capital": point.available_capital,
                            "open_position_count": point.open_position_count,
                        },
                    )
                for view in report.capital_sensitivity_views:
                    work.execute(
                        sensitivity_insert_sql,
                        {
                            "report_runtime_id": str(report.identity.runtime_id),
                            "label": view.label.value,
                            "capital_policy_id": view.capital_policy_id,
                            "initial_capital": view.initial_capital,
                            "max_concurrent_positions": view.max_concurrent_positions,
                            "allocated_count": view.allocated_count,
                            "rejected_count": view.rejected_count,
                            "ending_capital": view.ending_capital,
                            "realized_pnl": view.realized_pnl,
                            "max_drawdown": view.max_drawdown,
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _REPORT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_REPORT_KIND, identity=report.identity
                    ) from exc
                raise


def _row_to_decision(row: Mapping[str, Any]) -> PortfolioAllocationDecision:
    rejection_reason = row["rejection_reason"]
    return PortfolioAllocationDecision(
        opportunity_sequence=int(row["opportunity_sequence"]),
        source_window_id=str(row["source_window_id"]),
        trade_sequence=int(row["trade_sequence"]),
        instrument_symbol=str(row["instrument_symbol"]),
        scan_rank=int(row["scan_rank"]),
        entry_timestamp=row["entry_timestamp"],
        exit_timestamp=row["exit_timestamp"],
        risk_amount=cast(Decimal, row["risk_amount"]),
        net_pnl=cast(Decimal, row["net_pnl"]),
        decision=PortfolioAllocationOutcome(str(row["decision"])),
        rejection_reason=(
            PortfolioRejectionReason(str(rejection_reason))
            if rejection_reason is not None
            else None
        ),
    )


def _row_to_equity_observation(row: Mapping[str, Any]) -> PortfolioEquityObservation:
    return PortfolioEquityObservation(
        sequence_index=int(row["sequence_index"]),
        event_timestamp=row["event_timestamp"],
        event_kind=PortfolioEventKind(str(row["event_kind"])),
        equity=cast(Decimal, row["equity"]),
        occupied_capital=cast(Decimal, row["occupied_capital"]),
        available_capital=cast(Decimal, row["available_capital"]),
        open_position_count=int(row["open_position_count"]),
    )


def _row_to_sensitivity(row: Mapping[str, Any]) -> CapitalSensitivityView:
    return CapitalSensitivityView(
        label=CapitalSensitivityLabel(str(row["label"])),
        capital_policy_id=str(row["capital_policy_id"]),
        initial_capital=cast(Decimal, row["initial_capital"]),
        max_concurrent_positions=int(row["max_concurrent_positions"]),
        allocated_count=int(row["allocated_count"]),
        rejected_count=int(row["rejected_count"]),
        ending_capital=cast(Decimal, row["ending_capital"]),
        realized_pnl=cast(Decimal, row["realized_pnl"]),
        max_drawdown=cast(Decimal, row["max_drawdown"]),
    )


def _row_to_report(
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
        initial_capital=cast(Decimal, row["initial_capital"]),
        ending_capital=cast(Decimal, row["ending_capital"]),
        realized_pnl=cast(Decimal, row["realized_pnl"]),
        portfolio_return_percent=cast(Decimal, row["portfolio_return_percent"]),
        peak_equity=cast(Decimal, row["peak_equity"]),
        max_drawdown=cast(Decimal, row["max_drawdown"]),
        max_drawdown_percent=cast("Decimal | None", row["max_drawdown_percent"]),
        max_concurrent_positions_observed=int(row["max_concurrent_positions_observed"]),
        average_concurrent_positions=cast("Decimal | None", row["average_concurrent_positions"]),
        peak_occupied_capital=cast(Decimal, row["peak_occupied_capital"]),
        peak_capital_utilization_percent=cast(
            "Decimal | None", row["peak_capital_utilization_percent"]
        ),
        largest_instrument_positive_contribution_symbol=cast(
            "str | None", row["largest_instrument_positive_contribution_symbol"]
        ),
        largest_instrument_positive_contribution_amount=cast(
            "Decimal | None", row["largest_instrument_positive_contribution_amount"]
        ),
        largest_instrument_negative_contribution_symbol=cast(
            "str | None", row["largest_instrument_negative_contribution_symbol"]
        ),
        largest_instrument_negative_contribution_amount=cast(
            "Decimal | None", row["largest_instrument_negative_contribution_amount"]
        ),
        largest_position_contribution_trade_sequence=cast(
            "int | None", row["largest_position_contribution_trade_sequence"]
        ),
        largest_position_contribution_amount=cast(
            "Decimal | None", row["largest_position_contribution_amount"]
        ),
        largest_window_contribution_window_id=cast(
            "str | None", row["largest_window_contribution_window_id"]
        ),
        largest_window_contribution_amount=cast(
            "Decimal | None", row["largest_window_contribution_amount"]
        ),
        allocation_decisions=tuple(_row_to_decision(r) for r in decision_rows),
        equity_curve=tuple(_row_to_equity_observation(r) for r in equity_rows),
        capital_sensitivity_views=tuple(_row_to_sensitivity(r) for r in sensitivity_rows),
    )
