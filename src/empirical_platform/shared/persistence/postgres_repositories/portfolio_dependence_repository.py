"""Concrete PostgreSQL repository for M068 cross-instrument dependence /
correlation-aware portfolio risk reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.portfolio_dependence import (
    ConcentrationStressResult,
    ConcurrentExposureState,
    DependenceEstimationPolicy,
    DependenceEvidenceClassification,
    PairDependenceStatus,
    PairwiseDependenceEvidence,
    PortfolioDependenceReport,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioDependenceReportId
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_REPORT_KIND = "PortfolioDependenceReport"
_REPORT_UNIQUE_CONSTRAINTS = {
    "pk_portfolio_dependence_report",
    "uq_portfolio_dependence_report_governance_id",
}


class PostgresPortfolioDependenceReportRepository:
    """Concrete, storage-aware repository for immutable cross-instrument
    dependence reports, persisted across `portfolio_dependence_report`,
    `portfolio_dependence_pair`, and
    `portfolio_dependence_concurrent_state`."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(
        self, identity: DomainIdentity[PortfolioDependenceReportId]
    ) -> PortfolioDependenceReport:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM portfolio_dependence_report "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                raise AggregateNotFound(aggregate_kind=_REPORT_KIND, identity=identity)
            pair_rows = work.execute(
                "SELECT * FROM portfolio_dependence_pair "
                "WHERE report_runtime_id = :runtime_id ORDER BY instrument_a, instrument_b",
                {"runtime_id": str(identity.runtime_id)},
            )
            state_rows = work.execute(
                "SELECT * FROM portfolio_dependence_concurrent_state "
                "WHERE report_runtime_id = :runtime_id ORDER BY state_sequence",
                {"runtime_id": str(identity.runtime_id)},
            )
        return _row_to_report(rows[0], pair_rows, state_rows)

    def add(self, report: PortfolioDependenceReport) -> None:
        report_insert_sql = (
            "INSERT INTO portfolio_dependence_report ("
            "runtime_id, governance_id, source_portfolio_study_governance_id, "
            "source_portfolio_study_runtime_id, source_study_governance_id, "
            "source_study_runtime_id, dataset_bundle_id, dataset_bundle_version, "
            "dataset_bundle_sha256, dataset_source_kind, capital_policy_id, "
            "capital_policy_version, estimation_policy_id, estimation_policy_version, "
            "estimation_lookback_bar_count, estimation_minimum_overlapping_observations, "
            "instrument_count, pair_count, defined_pair_count, undefined_pair_count, "
            "highest_pair_a, highest_pair_b, highest_pair_correlation, lowest_pair_a, "
            "lowest_pair_b, lowest_pair_correlation, concurrent_exposure_state_count, "
            "peak_nominal_concentration, peak_dependence_aware_concentration, "
            "correlation_instability_observed, max_window_instability_delta, "
            "stress_canonical_peak_dependence_aware_concentration, "
            "stress_perfect_correlation_concentration, classification, limitations"
            ") VALUES ("
            ":runtime_id, :governance_id, :source_portfolio_study_governance_id, "
            ":source_portfolio_study_runtime_id, :source_study_governance_id, "
            ":source_study_runtime_id, :dataset_bundle_id, :dataset_bundle_version, "
            ":dataset_bundle_sha256, :dataset_source_kind, :capital_policy_id, "
            ":capital_policy_version, :estimation_policy_id, :estimation_policy_version, "
            ":estimation_lookback_bar_count, :estimation_minimum_overlapping_observations, "
            ":instrument_count, :pair_count, :defined_pair_count, :undefined_pair_count, "
            ":highest_pair_a, :highest_pair_b, :highest_pair_correlation, :lowest_pair_a, "
            ":lowest_pair_b, :lowest_pair_correlation, :concurrent_exposure_state_count, "
            ":peak_nominal_concentration, :peak_dependence_aware_concentration, "
            ":correlation_instability_observed, :max_window_instability_delta, "
            ":stress_canonical_peak_dependence_aware_concentration, "
            ":stress_perfect_correlation_concentration, :classification, :limitations"
            ")"
        )
        pair_insert_sql = (
            "INSERT INTO portfolio_dependence_pair ("
            "report_runtime_id, instrument_a, instrument_b, observation_count, "
            "estimation_start, estimation_end, correlation, status"
            ") VALUES ("
            ":report_runtime_id, :instrument_a, :instrument_b, :observation_count, "
            ":estimation_start, :estimation_end, :correlation, :status"
            ")"
        )
        state_insert_sql = (
            "INSERT INTO portfolio_dependence_concurrent_state ("
            "report_runtime_id, state_sequence, as_of_timestamp, open_instruments, weights, "
            "nominal_concentration, dependence_aware_concentration, undefined_pair_count"
            ") VALUES ("
            ":report_runtime_id, :state_sequence, :as_of_timestamp, :open_instruments, :weights, "
            ":nominal_concentration, :dependence_aware_concentration, :undefined_pair_count"
            ")"
        )
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    report_insert_sql,
                    {
                        "runtime_id": str(report.identity.runtime_id),
                        "governance_id": str(report.identity.governance_id),
                        "source_portfolio_study_governance_id": (
                            report.source_portfolio_study_governance_id
                        ),
                        "source_portfolio_study_runtime_id": (
                            report.source_portfolio_study_runtime_id
                        ),
                        "source_study_governance_id": report.source_study_governance_id,
                        "source_study_runtime_id": report.source_study_runtime_id,
                        "dataset_bundle_id": report.dataset_bundle_id,
                        "dataset_bundle_version": report.dataset_bundle_version,
                        "dataset_bundle_sha256": report.dataset_bundle_sha256,
                        "dataset_source_kind": report.dataset_source_kind,
                        "capital_policy_id": report.capital_policy_id,
                        "capital_policy_version": report.capital_policy_version,
                        "estimation_policy_id": report.estimation_policy.policy_id,
                        "estimation_policy_version": report.estimation_policy.version,
                        "estimation_lookback_bar_count": (
                            report.estimation_policy.lookback_bar_count
                        ),
                        "estimation_minimum_overlapping_observations": (
                            report.estimation_policy.minimum_overlapping_observations
                        ),
                        "instrument_count": report.instrument_count,
                        "pair_count": report.pair_count,
                        "defined_pair_count": report.defined_pair_count,
                        "undefined_pair_count": report.undefined_pair_count,
                        "highest_pair_a": report.highest_pair_a,
                        "highest_pair_b": report.highest_pair_b,
                        "highest_pair_correlation": report.highest_pair_correlation,
                        "lowest_pair_a": report.lowest_pair_a,
                        "lowest_pair_b": report.lowest_pair_b,
                        "lowest_pair_correlation": report.lowest_pair_correlation,
                        "concurrent_exposure_state_count": report.concurrent_exposure_state_count,
                        "peak_nominal_concentration": report.peak_nominal_concentration,
                        "peak_dependence_aware_concentration": (
                            report.peak_dependence_aware_concentration
                        ),
                        "correlation_instability_observed": report.correlation_instability_observed,
                        "max_window_instability_delta": report.max_window_instability_delta,
                        "stress_canonical_peak_dependence_aware_concentration": (
                            report.concentration_stress.canonical_peak_dependence_aware_concentration
                        ),
                        "stress_perfect_correlation_concentration": (
                            report.concentration_stress.stressed_perfect_correlation_concentration
                        ),
                        "classification": report.classification.value,
                        "limitations": list(report.limitations),
                    },
                )
                for pair in report.pairwise_dependence:
                    work.execute(
                        pair_insert_sql,
                        {
                            "report_runtime_id": str(report.identity.runtime_id),
                            "instrument_a": pair.instrument_a,
                            "instrument_b": pair.instrument_b,
                            "observation_count": pair.observation_count,
                            "estimation_start": pair.estimation_start,
                            "estimation_end": pair.estimation_end,
                            "correlation": pair.correlation,
                            "status": pair.status.value,
                        },
                    )
                for state in report.concurrent_exposure_states:
                    work.execute(
                        state_insert_sql,
                        {
                            "report_runtime_id": str(report.identity.runtime_id),
                            "state_sequence": state.state_sequence,
                            "as_of_timestamp": state.as_of_timestamp,
                            "open_instruments": list(state.open_instruments),
                            "weights": list(state.weights),
                            "nominal_concentration": state.nominal_concentration,
                            "dependence_aware_concentration": state.dependence_aware_concentration,
                            "undefined_pair_count": state.undefined_pair_count,
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _REPORT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_REPORT_KIND, identity=report.identity
                    ) from exc
                raise


def _row_to_pair(row: Mapping[str, Any]) -> PairwiseDependenceEvidence:
    return PairwiseDependenceEvidence(
        instrument_a=str(row["instrument_a"]),
        instrument_b=str(row["instrument_b"]),
        observation_count=int(row["observation_count"]),
        estimation_start=row["estimation_start"],
        estimation_end=row["estimation_end"],
        correlation=cast("Decimal | None", row["correlation"]),
        status=PairDependenceStatus(str(row["status"])),
    )


def _row_to_state(row: Mapping[str, Any]) -> ConcurrentExposureState:
    return ConcurrentExposureState(
        state_sequence=int(row["state_sequence"]),
        as_of_timestamp=row["as_of_timestamp"],
        open_instruments=tuple(row["open_instruments"]),
        weights=tuple(cast(Decimal, w) for w in row["weights"]),
        nominal_concentration=cast(Decimal, row["nominal_concentration"]),
        dependence_aware_concentration=cast(
            "Decimal | None", row["dependence_aware_concentration"]
        ),
        undefined_pair_count=int(row["undefined_pair_count"]),
    )


def _row_to_report(
    row: Mapping[str, Any],
    pair_rows: Sequence[Mapping[str, Any]],
    state_rows: Sequence[Mapping[str, Any]],
) -> PortfolioDependenceReport:
    estimation_policy = DependenceEstimationPolicy(
        policy_id=str(row["estimation_policy_id"]),
        version=str(row["estimation_policy_version"]),
        lookback_bar_count=int(row["estimation_lookback_bar_count"]),
        minimum_overlapping_observations=int(row["estimation_minimum_overlapping_observations"]),
    )
    concentration_stress = ConcentrationStressResult(
        canonical_peak_dependence_aware_concentration=cast(
            "Decimal | None", row["stress_canonical_peak_dependence_aware_concentration"]
        ),
        stressed_perfect_correlation_concentration=cast(
            "Decimal | None", row["stress_perfect_correlation_concentration"]
        ),
    )
    return PortfolioDependenceReport(
        identity=DomainIdentity(
            governance_id=PortfolioDependenceReportId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        source_portfolio_study_governance_id=str(row["source_portfolio_study_governance_id"]),
        source_portfolio_study_runtime_id=str(row["source_portfolio_study_runtime_id"]),
        source_study_governance_id=str(row["source_study_governance_id"]),
        source_study_runtime_id=str(row["source_study_runtime_id"]),
        dataset_bundle_id=str(row["dataset_bundle_id"]),
        dataset_bundle_version=str(row["dataset_bundle_version"]),
        dataset_bundle_sha256=str(row["dataset_bundle_sha256"]),
        dataset_source_kind=str(row["dataset_source_kind"]),
        capital_policy_id=str(row["capital_policy_id"]),
        capital_policy_version=str(row["capital_policy_version"]),
        estimation_policy=estimation_policy,
        instrument_count=int(row["instrument_count"]),
        pair_count=int(row["pair_count"]),
        defined_pair_count=int(row["defined_pair_count"]),
        undefined_pair_count=int(row["undefined_pair_count"]),
        highest_pair_a=cast("str | None", row["highest_pair_a"]),
        highest_pair_b=cast("str | None", row["highest_pair_b"]),
        highest_pair_correlation=cast("Decimal | None", row["highest_pair_correlation"]),
        lowest_pair_a=cast("str | None", row["lowest_pair_a"]),
        lowest_pair_b=cast("str | None", row["lowest_pair_b"]),
        lowest_pair_correlation=cast("Decimal | None", row["lowest_pair_correlation"]),
        concurrent_exposure_state_count=int(row["concurrent_exposure_state_count"]),
        peak_nominal_concentration=cast("Decimal | None", row["peak_nominal_concentration"]),
        peak_dependence_aware_concentration=cast(
            "Decimal | None", row["peak_dependence_aware_concentration"]
        ),
        correlation_instability_observed=bool(row["correlation_instability_observed"]),
        max_window_instability_delta=cast("Decimal | None", row["max_window_instability_delta"]),
        concentration_stress=concentration_stress,
        pairwise_dependence=tuple(_row_to_pair(r) for r in pair_rows),
        concurrent_exposure_states=tuple(_row_to_state(r) for r in state_rows),
        classification=DependenceEvidenceClassification(str(row["classification"])),
        limitations=tuple(row["limitations"]),
    )
