"""Run one post-hoc portfolio capital-allocation evidence evaluation
end-to-end.

MILESTONE-067. Loads one already-persisted M064
`SurvivorshipAwareRobustnessStudy`, loads the individual M061
`HistoricalBacktestRun`s referenced by its own windows (each fetched
through the unmodified, frozen `HistoricalBacktestRunRepository` -- never
a second persistence path for backtest runs), and builds/persists one
immutable `PortfolioEvidenceReport`. Never re-runs, re-ranks, re-sizes,
or re-optimizes anything upstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.historical_backtest_repository import (
    HistoricalBacktestRunRepository,
)
from empirical_platform.decision_candidate.portfolio_study import (
    DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    PortfolioCapitalPolicy,
    PortfolioEvidenceReport,
    build_portfolio_evidence_report,
)
from empirical_platform.decision_candidate.portfolio_study_repository import (
    PortfolioStudyRepository,
)
from empirical_platform.decision_candidate.survivorship_study_repository import (
    SurvivorshipAwareRobustnessStudyRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioStudyId, SurvivorshipStudyId
from empirical_platform.shared.identifiers import RuntimeIdentifier, RuntimeIdentifierGenerator

__all__ = [
    "PortfolioCapitalPolicy",
    "PortfolioEvidenceReport",
    "RunPortfolioHistoricalEvidenceCommand",
    "RunPortfolioHistoricalEvidenceHandler",
    "build_run_portfolio_historical_evidence_command",
]


@dataclass(frozen=True, slots=True)
class RunPortfolioHistoricalEvidenceCommand:
    """Request to evaluate portfolio capital-allocation evidence for one
    already-persisted survivorship-aware robustness study."""

    identity: DomainIdentity[PortfolioStudyId]
    source_study_identity: DomainIdentity[SurvivorshipStudyId]
    capital_policy: PortfolioCapitalPolicy


class RunPortfolioHistoricalEvidenceHandler:
    """Load the upstream study and its window backtest runs, build one
    portfolio evidence report, and persist it -- through the unmodified
    M064 `SurvivorshipAwareRobustnessStudyRepository` and the unmodified
    M061 `HistoricalBacktestRunRepository`, never a second persistence
    path for either."""

    __slots__ = ("_reports", "_studies", "_historical_backtests")

    def __init__(
        self,
        *,
        report_repository: PortfolioStudyRepository,
        study_repository: SurvivorshipAwareRobustnessStudyRepository,
        historical_backtest_run_repository: HistoricalBacktestRunRepository,
    ) -> None:
        self._reports = report_repository
        self._studies = study_repository
        self._historical_backtests = historical_backtest_run_repository

    def handle(self, command: RunPortfolioHistoricalEvidenceCommand) -> PortfolioEvidenceReport:
        study = self._studies.get(command.source_study_identity)
        window_runs = tuple(
            self._historical_backtests.get(
                DomainIdentity(
                    governance_id=window.backtest_run_id,
                    runtime_id=window.backtest_run_runtime_id,
                )
            )
            for window in study.window_results
            if window.backtest_run_id is not None and window.backtest_run_runtime_id is not None
        )
        report = build_portfolio_evidence_report(
            identity=command.identity,
            study=study,
            window_runs=window_runs,
            capital_policy=command.capital_policy,
        )
        self._reports.add(report)
        return report


def build_run_portfolio_historical_evidence_command(
    *,
    report_governance_id: str,
    source_study_governance_id: str,
    source_study_runtime_id: str,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    capital_policy: PortfolioCapitalPolicy = DEFAULT_PORTFOLIO_CAPITAL_POLICY,
) -> RunPortfolioHistoricalEvidenceCommand:
    """Build one real M067 command from plain application-layer inputs."""
    return RunPortfolioHistoricalEvidenceCommand(
        identity=DomainIdentity(
            governance_id=PortfolioStudyId(report_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        source_study_identity=DomainIdentity(
            governance_id=SurvivorshipStudyId(source_study_governance_id),
            runtime_id=RuntimeIdentifier(source_study_runtime_id),
        ),
        capital_policy=capital_policy,
    )
