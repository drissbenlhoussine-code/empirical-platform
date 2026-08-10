"""Run one post-hoc statistical evidence analysis end-to-end.

MILESTONE-066. Loads one already-persisted M064
`SurvivorshipAwareRobustnessStudy`, loads the individual M061
`HistoricalBacktestRun`s referenced by its own windows (each fetched
through the unmodified, frozen `HistoricalBacktestRunRepository` -- never
a second persistence path for backtest runs), and builds/persists one
immutable `StatisticalEvidenceReport`. Never re-runs, re-ranks, re-sizes,
or re-optimizes anything upstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.historical_backtest_repository import (
    HistoricalBacktestRunRepository,
)
from empirical_platform.decision_candidate.statistical_evidence import (
    DEFAULT_BOOTSTRAP_POLICY,
    BootstrapMethod,
    BootstrapPolicy,
    StatisticalEvidenceReport,
    build_statistical_evidence_report,
)
from empirical_platform.decision_candidate.statistical_evidence_repository import (
    StatisticalEvidenceReportRepository,
)
from empirical_platform.decision_candidate.survivorship_study_repository import (
    SurvivorshipAwareRobustnessStudyRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import StatisticalEvidenceReportId, SurvivorshipStudyId
from empirical_platform.shared.identifiers import RuntimeIdentifier, RuntimeIdentifierGenerator

__all__ = [
    "BootstrapMethod",
    "BootstrapPolicy",
    "RunStatisticalEvidenceAnalysisCommand",
    "RunStatisticalEvidenceAnalysisHandler",
    "StatisticalEvidenceReport",
    "build_run_statistical_evidence_analysis_command",
]


@dataclass(frozen=True, slots=True)
class RunStatisticalEvidenceAnalysisCommand:
    """Request to statistically evaluate one already-persisted
    survivorship-aware robustness study."""

    identity: DomainIdentity[StatisticalEvidenceReportId]
    source_study_identity: DomainIdentity[SurvivorshipStudyId]
    bootstrap_policy: BootstrapPolicy


class RunStatisticalEvidenceAnalysisHandler:
    """Load the upstream study and its window backtest runs, build one
    statistical evidence report, and persist it -- through the
    unmodified M064 `SurvivorshipAwareRobustnessStudyRepository` and the
    unmodified M061 `HistoricalBacktestRunRepository`, never a second
    persistence path for either."""

    __slots__ = ("_reports", "_studies", "_historical_backtests")

    def __init__(
        self,
        *,
        report_repository: StatisticalEvidenceReportRepository,
        study_repository: SurvivorshipAwareRobustnessStudyRepository,
        historical_backtest_run_repository: HistoricalBacktestRunRepository,
    ) -> None:
        self._reports = report_repository
        self._studies = study_repository
        self._historical_backtests = historical_backtest_run_repository

    def handle(self, command: RunStatisticalEvidenceAnalysisCommand) -> StatisticalEvidenceReport:
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
        report = build_statistical_evidence_report(
            identity=command.identity,
            study=study,
            window_runs=window_runs,
            bootstrap_policy=command.bootstrap_policy,
        )
        self._reports.add(report)
        return report


def build_run_statistical_evidence_analysis_command(
    *,
    report_governance_id: str,
    source_study_governance_id: str,
    source_study_runtime_id: str,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    bootstrap_policy: BootstrapPolicy = DEFAULT_BOOTSTRAP_POLICY,
) -> RunStatisticalEvidenceAnalysisCommand:
    """Build one real M066 command from plain application-layer inputs."""
    return RunStatisticalEvidenceAnalysisCommand(
        identity=DomainIdentity(
            governance_id=StatisticalEvidenceReportId(report_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        source_study_identity=DomainIdentity(
            governance_id=SurvivorshipStudyId(source_study_governance_id),
            runtime_id=RuntimeIdentifier(source_study_runtime_id),
        ),
        bootstrap_policy=bootstrap_policy,
    )
