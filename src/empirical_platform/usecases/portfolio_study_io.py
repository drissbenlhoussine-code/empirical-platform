"""Usecase-layer JSON serialization helpers for MILESTONE-067."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol, cast

__all__ = ["portfolio_evidence_report_payload"]


class _CapitalPolicyView(Protocol):
    policy_id: str
    version: str
    initial_capital: Decimal
    currency: str
    max_concurrent_positions: int
    max_capital_utilization_percent: Decimal


class _AllocationDecisionView(Protocol):
    opportunity_sequence: int
    source_window_id: str
    trade_sequence: int
    instrument_symbol: str
    scan_rank: int
    entry_timestamp: datetime
    exit_timestamp: datetime
    risk_amount: Decimal
    net_pnl: Decimal
    rejection_reason: object | None

    @property
    def decision(self) -> object: ...


class _EquityObservationView(Protocol):
    sequence_index: int
    event_timestamp: datetime
    equity: Decimal
    occupied_capital: Decimal
    available_capital: Decimal
    open_position_count: int

    @property
    def event_kind(self) -> object: ...


class _CapitalSensitivityViewView(Protocol):
    capital_policy_id: str
    initial_capital: Decimal
    max_concurrent_positions: int
    allocated_count: int
    rejected_count: int
    ending_capital: Decimal
    realized_pnl: Decimal
    max_drawdown: Decimal

    @property
    def label(self) -> object: ...


class _ValueEnumView(Protocol):
    value: str


class PortfolioEvidenceReportPayloadView(Protocol):
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
    capital_policy: _CapitalPolicyView
    total_opportunities: int
    allocated_count: int
    rejected_count: int
    rejected_insufficient_capital_count: int
    rejected_max_concurrent_count: int
    rejected_max_utilization_count: int
    initial_capital: Decimal
    ending_capital: Decimal
    realized_pnl: Decimal
    portfolio_return_percent: Decimal
    peak_equity: Decimal
    max_drawdown: Decimal
    max_drawdown_percent: Decimal | None
    max_concurrent_positions_observed: int
    average_concurrent_positions: Decimal | None
    peak_occupied_capital: Decimal
    peak_capital_utilization_percent: Decimal | None
    largest_instrument_positive_contribution_symbol: str | None
    largest_instrument_positive_contribution_amount: Decimal | None
    largest_instrument_negative_contribution_symbol: str | None
    largest_instrument_negative_contribution_amount: Decimal | None
    largest_position_contribution_trade_sequence: int | None
    largest_position_contribution_amount: Decimal | None
    largest_window_contribution_window_id: str | None
    largest_window_contribution_amount: Decimal | None
    allocation_decisions: tuple[_AllocationDecisionView, ...]
    equity_curve: tuple[_EquityObservationView, ...]
    capital_sensitivity_views: tuple[_CapitalSensitivityViewView, ...]


def _decision_payload(decision: _AllocationDecisionView) -> dict[str, object]:
    return {
        "opportunity_sequence": decision.opportunity_sequence,
        "source_window_id": decision.source_window_id,
        "trade_sequence": decision.trade_sequence,
        "instrument_symbol": decision.instrument_symbol,
        "scan_rank": decision.scan_rank,
        "entry_timestamp": decision.entry_timestamp.isoformat(),
        "exit_timestamp": decision.exit_timestamp.isoformat(),
        "risk_amount": str(decision.risk_amount),
        "net_pnl": str(decision.net_pnl),
        "decision": cast(_ValueEnumView, decision.decision).value,
        "rejection_reason": (
            cast(_ValueEnumView, decision.rejection_reason).value
            if decision.rejection_reason is not None
            else None
        ),
    }


def _equity_payload(point: _EquityObservationView) -> dict[str, object]:
    return {
        "sequence_index": point.sequence_index,
        "event_timestamp": point.event_timestamp.isoformat(),
        "event_kind": cast(_ValueEnumView, point.event_kind).value,
        "equity": str(point.equity),
        "occupied_capital": str(point.occupied_capital),
        "available_capital": str(point.available_capital),
        "open_position_count": point.open_position_count,
    }


def _sensitivity_payload(view: _CapitalSensitivityViewView) -> dict[str, object]:
    return {
        "label": cast(_ValueEnumView, view.label).value,
        "capital_policy_id": view.capital_policy_id,
        "initial_capital": str(view.initial_capital),
        "max_concurrent_positions": view.max_concurrent_positions,
        "allocated_count": view.allocated_count,
        "rejected_count": view.rejected_count,
        "ending_capital": str(view.ending_capital),
        "realized_pnl": str(view.realized_pnl),
        "max_drawdown": str(view.max_drawdown),
    }


def portfolio_evidence_report_payload(report: object) -> dict[str, object]:
    typed = cast(PortfolioEvidenceReportPayloadView, report)
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
        "capital_policy": {
            "policy_id": typed.capital_policy.policy_id,
            "version": typed.capital_policy.version,
            "initial_capital": str(typed.capital_policy.initial_capital),
            "currency": typed.capital_policy.currency,
            "max_concurrent_positions": typed.capital_policy.max_concurrent_positions,
            "max_capital_utilization_percent": str(
                typed.capital_policy.max_capital_utilization_percent
            ),
        },
        "total_opportunities": typed.total_opportunities,
        "allocated_count": typed.allocated_count,
        "rejected_count": typed.rejected_count,
        "rejected_insufficient_capital_count": typed.rejected_insufficient_capital_count,
        "rejected_max_concurrent_count": typed.rejected_max_concurrent_count,
        "rejected_max_utilization_count": typed.rejected_max_utilization_count,
        "initial_capital": str(typed.initial_capital),
        "ending_capital": str(typed.ending_capital),
        "realized_pnl": str(typed.realized_pnl),
        "portfolio_return_percent": str(typed.portfolio_return_percent),
        "peak_equity": str(typed.peak_equity),
        "max_drawdown": str(typed.max_drawdown),
        "max_drawdown_percent": (
            str(typed.max_drawdown_percent) if typed.max_drawdown_percent is not None else None
        ),
        "max_concurrent_positions_observed": typed.max_concurrent_positions_observed,
        "average_concurrent_positions": (
            str(typed.average_concurrent_positions)
            if typed.average_concurrent_positions is not None
            else None
        ),
        "peak_occupied_capital": str(typed.peak_occupied_capital),
        "peak_capital_utilization_percent": (
            str(typed.peak_capital_utilization_percent)
            if typed.peak_capital_utilization_percent is not None
            else None
        ),
        "largest_instrument_positive_contribution_symbol": (
            typed.largest_instrument_positive_contribution_symbol
        ),
        "largest_instrument_positive_contribution_amount": (
            str(typed.largest_instrument_positive_contribution_amount)
            if typed.largest_instrument_positive_contribution_amount is not None
            else None
        ),
        "largest_instrument_negative_contribution_symbol": (
            typed.largest_instrument_negative_contribution_symbol
        ),
        "largest_instrument_negative_contribution_amount": (
            str(typed.largest_instrument_negative_contribution_amount)
            if typed.largest_instrument_negative_contribution_amount is not None
            else None
        ),
        "largest_position_contribution_trade_sequence": (
            typed.largest_position_contribution_trade_sequence
        ),
        "largest_position_contribution_amount": (
            str(typed.largest_position_contribution_amount)
            if typed.largest_position_contribution_amount is not None
            else None
        ),
        "largest_window_contribution_window_id": typed.largest_window_contribution_window_id,
        "largest_window_contribution_amount": (
            str(typed.largest_window_contribution_amount)
            if typed.largest_window_contribution_amount is not None
            else None
        ),
        "allocation_decisions": [_decision_payload(d) for d in typed.allocation_decisions],
        "equity_curve": [_equity_payload(p) for p in typed.equity_curve],
        "capital_sensitivity_views": [
            _sensitivity_payload(v) for v in typed.capital_sensitivity_views
        ],
    }
