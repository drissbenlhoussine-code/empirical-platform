"""Real end-to-end statistical evidence report retrieval composition
root."""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import StatisticalEvidenceReportId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_statistical_evidence_report import (
    GetStatisticalEvidenceReportHandler,
    GetStatisticalEvidenceReportQuery,
)
from empirical_platform.usecases.statistical_evidence_io import statistical_evidence_report_payload


def run_get_statistical_evidence_report(
    *,
    report_governance_id: str,
    report_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Retrieve one statistical evidence report end-to-end against real
    PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetStatisticalEvidenceReportHandler(
            repository=runtime.statistical_evidence_reports
        )
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            GetStatisticalEvidenceReportQuery(
                identity=DomainIdentity(
                    governance_id=StatisticalEvidenceReportId(report_governance_id),
                    runtime_id=RuntimeIdentifier(report_runtime_id),
                )
            )
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-statistical-evidence-report <governance_id> <runtime_id>"
        )
    report = run_get_statistical_evidence_report(
        report_governance_id=sys.argv[1], report_runtime_id=sys.argv[2]
    )
    print(json.dumps(statistical_evidence_report_payload(report), sort_keys=True))


if __name__ == "__main__":
    main()
