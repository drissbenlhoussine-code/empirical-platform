"""Usecase-layer JSON serialization helpers for MILESTONE-068."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol, cast

__all__ = ["portfolio_dependence_report_payload"]


class _EstimationPolicyView(Protocol):
    policy_id: str
    version: str
    lookback_bar_count: int
    minimum_overlapping_observations: int


class _PairView(Protocol):
    instrument_a: str
    instrument_b: str
    observation_count: int
    estimation_start: datetime
    estimation_end: datetime
    correlation: Decimal | None

    @property
    def status(self) -> object: ...


class _ConcurrentStateView(Protocol):
    state_sequence: int
    as_of_timestamp: datetime
    open_instruments: tuple[str, ...]
    weights: tuple[Decimal, ...]
    nominal_concentration: Decimal
    dependence_aware_concentration: Decimal | None
    undefined_pair_count: int


class _ConcentrationStressView(Protocol):
    canonical_peak_dependence_aware_concentration: Decimal | None
    stressed_perfect_correlation_concentration: Decimal | None


class _ValueEnumView(Protocol):
    value: str


class PortfolioDependenceReportPayloadView(Protocol):
    identity: object
    source_portfolio_study_governance_id: str
    source_portfolio_study_runtime_id: str
    source_study_governance_id: str
    source_study_runtime_id: str
    dataset_bundle_id: str
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    capital_policy_id: str
    capital_policy_version: str
    estimation_policy: _EstimationPolicyView
    instrument_count: int
    pair_count: int
    defined_pair_count: int
    undefined_pair_count: int
    highest_pair_a: str | None
    highest_pair_b: str | None
    highest_pair_correlation: Decimal | None
    lowest_pair_a: str | None
    lowest_pair_b: str | None
    lowest_pair_correlation: Decimal | None
    concurrent_exposure_state_count: int
    peak_nominal_concentration: Decimal | None
    peak_dependence_aware_concentration: Decimal | None
    correlation_instability_observed: bool
    max_window_instability_delta: Decimal | None
    concentration_stress: _ConcentrationStressView
    pairwise_dependence: tuple[_PairView, ...]
    concurrent_exposure_states: tuple[_ConcurrentStateView, ...]
    limitations: tuple[str, ...]

    @property
    def classification(self) -> object: ...


def _pair_payload(pair: _PairView) -> dict[str, object]:
    return {
        "instrument_a": pair.instrument_a,
        "instrument_b": pair.instrument_b,
        "observation_count": pair.observation_count,
        "estimation_start": pair.estimation_start.isoformat(),
        "estimation_end": pair.estimation_end.isoformat(),
        "correlation": str(pair.correlation) if pair.correlation is not None else None,
        "status": cast(_ValueEnumView, pair.status).value,
    }


def _state_payload(state: _ConcurrentStateView) -> dict[str, object]:
    return {
        "state_sequence": state.state_sequence,
        "as_of_timestamp": state.as_of_timestamp.isoformat(),
        "open_instruments": list(state.open_instruments),
        "weights": [str(w) for w in state.weights],
        "nominal_concentration": str(state.nominal_concentration),
        "dependence_aware_concentration": (
            str(state.dependence_aware_concentration)
            if state.dependence_aware_concentration is not None
            else None
        ),
        "undefined_pair_count": state.undefined_pair_count,
    }


def portfolio_dependence_report_payload(report: object) -> dict[str, object]:
    typed = cast(PortfolioDependenceReportPayloadView, report)
    identity = typed.identity
    return {
        "governance_id": str(identity.governance_id),  # type: ignore[attr-defined]
        "runtime_id": str(identity.runtime_id),  # type: ignore[attr-defined]
        "source_portfolio_study_governance_id": typed.source_portfolio_study_governance_id,
        "source_portfolio_study_runtime_id": typed.source_portfolio_study_runtime_id,
        "source_study_governance_id": typed.source_study_governance_id,
        "source_study_runtime_id": typed.source_study_runtime_id,
        "dataset_bundle_id": typed.dataset_bundle_id,
        "dataset_bundle_version": typed.dataset_bundle_version,
        "dataset_bundle_sha256": typed.dataset_bundle_sha256,
        "dataset_source_kind": typed.dataset_source_kind,
        "capital_policy_id": typed.capital_policy_id,
        "capital_policy_version": typed.capital_policy_version,
        "estimation_policy": {
            "policy_id": typed.estimation_policy.policy_id,
            "version": typed.estimation_policy.version,
            "lookback_bar_count": typed.estimation_policy.lookback_bar_count,
            "minimum_overlapping_observations": (
                typed.estimation_policy.minimum_overlapping_observations
            ),
        },
        "instrument_count": typed.instrument_count,
        "pair_count": typed.pair_count,
        "defined_pair_count": typed.defined_pair_count,
        "undefined_pair_count": typed.undefined_pair_count,
        "highest_pair_a": typed.highest_pair_a,
        "highest_pair_b": typed.highest_pair_b,
        "highest_pair_correlation": (
            str(typed.highest_pair_correlation)
            if typed.highest_pair_correlation is not None
            else None
        ),
        "lowest_pair_a": typed.lowest_pair_a,
        "lowest_pair_b": typed.lowest_pair_b,
        "lowest_pair_correlation": (
            str(typed.lowest_pair_correlation)
            if typed.lowest_pair_correlation is not None
            else None
        ),
        "concurrent_exposure_state_count": typed.concurrent_exposure_state_count,
        "peak_nominal_concentration": (
            str(typed.peak_nominal_concentration)
            if typed.peak_nominal_concentration is not None
            else None
        ),
        "peak_dependence_aware_concentration": (
            str(typed.peak_dependence_aware_concentration)
            if typed.peak_dependence_aware_concentration is not None
            else None
        ),
        "correlation_instability_observed": typed.correlation_instability_observed,
        "max_window_instability_delta": (
            str(typed.max_window_instability_delta)
            if typed.max_window_instability_delta is not None
            else None
        ),
        "concentration_stress": {
            "canonical_peak_dependence_aware_concentration": (
                str(typed.concentration_stress.canonical_peak_dependence_aware_concentration)
                if typed.concentration_stress.canonical_peak_dependence_aware_concentration
                is not None
                else None
            ),
            "stressed_perfect_correlation_concentration": (
                str(typed.concentration_stress.stressed_perfect_correlation_concentration)
                if typed.concentration_stress.stressed_perfect_correlation_concentration is not None
                else None
            ),
        },
        "pairwise_dependence": [_pair_payload(p) for p in typed.pairwise_dependence],
        "concurrent_exposure_states": [_state_payload(s) for s in typed.concurrent_exposure_states],
        "classification": cast(_ValueEnumView, typed.classification).value,
        "limitations": list(typed.limitations),
    }
