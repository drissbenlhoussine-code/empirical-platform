"""Real end-to-end statistical evidence analysis composition root.

MILESTONE-066. A caller supplies the governance identity of one
already-persisted M064 `SurvivorshipAwareRobustnessStudy` and receives one
structured, persisted `StatisticalEvidenceReport` -- built entirely from
that study's own already-frozen window results and the individual M061
`HistoricalBacktestRun`s they reference. No strategy, ranking, risk,
sizing, or backtest logic is re-run.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.run_statistical_evidence_analysis import (
    BootstrapMethod,
    BootstrapPolicy,
    RunStatisticalEvidenceAnalysisHandler,
    build_run_statistical_evidence_analysis_command,
)
from empirical_platform.usecases.statistical_evidence_io import statistical_evidence_report_payload


def run_run_statistical_evidence_analysis(
    *,
    report_governance_id: str,
    source_study_governance_id: str,
    source_study_runtime_id: str,
    resample_count: int = 2000,
    seed: int = 6066001,
    confidence_level: Decimal = Decimal("0.90"),
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Run one deterministic statistical evidence analysis end-to-end
    against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    bootstrap_policy = BootstrapPolicy(
        policy_id="STATEVID-BOOTSTRAP",
        version="1",
        method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
        resample_count=resample_count,
        seed=seed,
        confidence_level=confidence_level,
    )
    with postgres_repository_runtime(config) as runtime:
        handler = RunStatisticalEvidenceAnalysisHandler(
            report_repository=runtime.statistical_evidence_reports,
            study_repository=runtime.survivorship_studies,
            historical_backtest_run_repository=runtime.historical_backtests,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_run_statistical_evidence_analysis_command(
                report_governance_id=report_governance_id,
                source_study_governance_id=source_study_governance_id,
                source_study_runtime_id=source_study_runtime_id,
                runtime_identifier_generator=resolved_generator,
                bootstrap_policy=bootstrap_policy,
            )
        )


def _report_payload(report: object) -> dict[str, object]:
    return statistical_evidence_report_payload(report)


def main() -> None:
    if len(sys.argv) not in (4, 5, 6, 7):
        raise SystemExit(
            "usage: empirical-platform-run-statistical-evidence-analysis "
            "<report_governance_id> <source_study_governance_id> <source_study_runtime_id> "
            "[resample_count] [seed] [confidence_level]"
        )
    result = run_run_statistical_evidence_analysis(
        report_governance_id=sys.argv[1],
        source_study_governance_id=sys.argv[2],
        source_study_runtime_id=sys.argv[3],
        resample_count=int(sys.argv[4]) if len(sys.argv) > 4 else 2000,
        seed=int(sys.argv[5]) if len(sys.argv) > 5 else 6066001,
        confidence_level=Decimal(sys.argv[6]) if len(sys.argv) > 6 else Decimal("0.90"),
    )
    print(json.dumps(_report_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
