"""Real end-to-end portfolio dependence report retrieval composition
root."""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioDependenceReportId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_portfolio_dependence_evidence import (
    GetPortfolioDependenceEvidenceHandler,
    GetPortfolioDependenceEvidenceQuery,
)
from empirical_platform.usecases.portfolio_dependence_io import (
    portfolio_dependence_report_payload,
)


def run_get_portfolio_dependence_evidence(
    *,
    report_governance_id: str,
    report_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Retrieve one portfolio dependence report end-to-end against real
    PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetPortfolioDependenceEvidenceHandler(
            repository=runtime.portfolio_dependence_reports
        )
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            GetPortfolioDependenceEvidenceQuery(
                identity=DomainIdentity(
                    governance_id=PortfolioDependenceReportId(report_governance_id),
                    runtime_id=RuntimeIdentifier(report_runtime_id),
                )
            )
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-portfolio-dependence-evidence "
            "<governance_id> <runtime_id>"
        )
    report = run_get_portfolio_dependence_evidence(
        report_governance_id=sys.argv[1], report_runtime_id=sys.argv[2]
    )
    print(json.dumps(portfolio_dependence_report_payload(report), sort_keys=True))


if __name__ == "__main__":
    main()
