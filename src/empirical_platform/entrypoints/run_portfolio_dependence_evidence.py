"""Real end-to-end cross-instrument dependence evidence composition
root.

MILESTONE-068. A caller supplies the governance identity of one
already-persisted M067 `PortfolioEvidenceReport` plus the exact dataset
bundle file its own upstream M064/M065 authority declares, and receives
one structured, persisted `PortfolioDependenceReport` -- built entirely
from that report's own already-frozen concurrent-position timeline and
the raw historical bar series. No allocation, strategy, ranking, risk,
or sizing logic is re-run.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.portfolio_dependence_io import (
    portfolio_dependence_report_payload,
)
from empirical_platform.usecases.run_portfolio_dependence_evidence import (
    DEFAULT_DEPENDENCE_ESTIMATION_POLICY,
    DependenceEstimationPolicy,
    RunPortfolioDependenceEvidenceHandler,
    build_run_portfolio_dependence_evidence_command,
)


def run_run_portfolio_dependence_evidence(
    *,
    report_governance_id: str,
    source_portfolio_study_governance_id: str,
    source_portfolio_study_runtime_id: str,
    dataset_bundle_file: str,
    lookback_bar_count: int = 20,
    minimum_overlapping_observations: int = 10,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Run one deterministic cross-instrument dependence evidence
    evaluation end-to-end against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    estimation_policy = DependenceEstimationPolicy(
        policy_id=DEFAULT_DEPENDENCE_ESTIMATION_POLICY.policy_id,
        version=DEFAULT_DEPENDENCE_ESTIMATION_POLICY.version,
        lookback_bar_count=lookback_bar_count,
        minimum_overlapping_observations=minimum_overlapping_observations,
    )
    with postgres_repository_runtime(config) as runtime:
        handler = RunPortfolioDependenceEvidenceHandler(
            report_repository=runtime.portfolio_dependence_reports,
            portfolio_study_repository=runtime.portfolio_studies,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_run_portfolio_dependence_evidence_command(
                report_governance_id=report_governance_id,
                source_portfolio_study_governance_id=source_portfolio_study_governance_id,
                source_portfolio_study_runtime_id=source_portfolio_study_runtime_id,
                dataset_bundle_file=dataset_bundle_file,
                runtime_identifier_generator=resolved_generator,
                estimation_policy=estimation_policy,
            )
        )


def _report_payload(report: object) -> dict[str, object]:
    return portfolio_dependence_report_payload(report)


def main() -> None:
    if len(sys.argv) not in (5, 6, 7):
        raise SystemExit(
            "usage: empirical-platform-run-portfolio-dependence-evidence "
            "<report_governance_id> <source_portfolio_study_governance_id> "
            "<source_portfolio_study_runtime_id> <dataset_bundle_file> "
            "[lookback_bar_count] [minimum_overlapping_observations]"
        )
    result = run_run_portfolio_dependence_evidence(
        report_governance_id=sys.argv[1],
        source_portfolio_study_governance_id=sys.argv[2],
        source_portfolio_study_runtime_id=sys.argv[3],
        dataset_bundle_file=sys.argv[4],
        lookback_bar_count=int(sys.argv[5]) if len(sys.argv) > 5 else 20,
        minimum_overlapping_observations=int(sys.argv[6]) if len(sys.argv) > 6 else 10,
    )
    print(json.dumps(_report_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
