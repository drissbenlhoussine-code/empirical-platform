"""Run one post-hoc cross-instrument dependence evidence evaluation
end-to-end.

MILESTONE-068. Loads one already-persisted M067 `PortfolioEvidenceReport`,
loads the raw per-instrument bar series from the exact dataset bundle
file the upstream M064/M065 study authority already declares (hash
-verified against the upstream report's own persisted
`dataset_bundle_sha256` -- tamper/mismatch detected before any
correlation computation is attempted), and builds/persists one immutable
`PortfolioDependenceReport`. Never re-runs, re-allocates, or
re-optimizes anything upstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.portfolio_dependence import (
    DEFAULT_DEPENDENCE_ESTIMATION_POLICY,
    DependenceEstimationPolicy,
    PortfolioDependenceReport,
    build_portfolio_dependence_report,
)
from empirical_platform.decision_candidate.portfolio_dependence_repository import (
    PortfolioDependenceReportRepository,
)
from empirical_platform.decision_candidate.portfolio_study_repository import (
    PortfolioStudyRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioDependenceReportId, PortfolioStudyId
from empirical_platform.shared.identifiers import RuntimeIdentifier, RuntimeIdentifierGenerator
from empirical_platform.usecases.robustness_study_io import parse_robustness_dataset_bundle_file

__all__ = [
    "DEFAULT_DEPENDENCE_ESTIMATION_POLICY",
    "DependenceEstimationPolicy",
    "PortfolioDependenceReport",
    "RunPortfolioDependenceEvidenceCommand",
    "RunPortfolioDependenceEvidenceHandler",
    "build_run_portfolio_dependence_evidence_command",
]


@dataclass(frozen=True, slots=True)
class RunPortfolioDependenceEvidenceCommand:
    """Request to evaluate cross-instrument dependence evidence for one
    already-persisted portfolio capital-allocation evidence report."""

    identity: DomainIdentity[PortfolioDependenceReportId]
    source_portfolio_study_identity: DomainIdentity[PortfolioStudyId]
    dataset_bundle_file: str
    estimation_policy: DependenceEstimationPolicy


class RunPortfolioDependenceEvidenceHandler:
    """Load the upstream M067 report and the exact dataset bundle its
    own upstream M064/M065 authority declares, build one portfolio
    dependence report, and persist it -- through the unmodified M067
    `PortfolioStudyRepository`, never a second persistence path."""

    __slots__ = ("_reports", "_portfolio_studies")

    def __init__(
        self,
        *,
        report_repository: PortfolioDependenceReportRepository,
        portfolio_study_repository: PortfolioStudyRepository,
    ) -> None:
        self._reports = report_repository
        self._portfolio_studies = portfolio_study_repository

    def handle(
        self, command: RunPortfolioDependenceEvidenceCommand
    ) -> PortfolioDependenceReport:
        portfolio = self._portfolio_studies.get(command.source_portfolio_study_identity)
        bundle = parse_robustness_dataset_bundle_file(
            command.dataset_bundle_file, expected_sha256=portfolio.dataset_bundle_sha256
        )
        series_by_instrument = {
            str(series.instrument.symbol): series for series in bundle.series
        }
        report = build_portfolio_dependence_report(
            identity=command.identity,
            portfolio=portfolio,
            series_by_instrument=series_by_instrument,
            policy=command.estimation_policy,
        )
        self._reports.add(report)
        return report


def build_run_portfolio_dependence_evidence_command(
    *,
    report_governance_id: str,
    source_portfolio_study_governance_id: str,
    source_portfolio_study_runtime_id: str,
    dataset_bundle_file: str,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    estimation_policy: DependenceEstimationPolicy = DEFAULT_DEPENDENCE_ESTIMATION_POLICY,
) -> RunPortfolioDependenceEvidenceCommand:
    """Build one real M068 command from plain application-layer inputs."""
    return RunPortfolioDependenceEvidenceCommand(
        identity=DomainIdentity(
            governance_id=PortfolioDependenceReportId(report_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        source_portfolio_study_identity=DomainIdentity(
            governance_id=PortfolioStudyId(source_portfolio_study_governance_id),
            runtime_id=RuntimeIdentifier(source_portfolio_study_runtime_id),
        ),
        dataset_bundle_file=dataset_bundle_file,
        estimation_policy=estimation_policy,
    )
