"""Real end-to-end EvidencePackage criterion-result composition root.

Composes the frozen MILESTONE-039 vertical slice through the shared
MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.record_evidence_package_criterion_result import (
    RecordEvidencePackageCriterionResultCommand,
    RecordEvidencePackageCriterionResultHandler,
)


def run_record_evidence_package_criterion_result(
    *,
    evidence_package_governance_id: str,
    evidence_package_runtime_id: str,
    expected_persisted_version: int,
    criterion_id: str,
    recorded_at: datetime,
    result_label: str,
    summary: str | None = None,
    evidence_references: tuple[str, ...] = (),
    config: PostgreSQLConfigSnapshot | None = None,
) -> SaveResult:
    """Record one CriterionResult on an EvidencePackage, end-to-end, against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = RecordEvidencePackageCriterionResultHandler(
            evidence_package_repository=runtime.evidence_packages
        )
        entry_point = CommandEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=EvidencePackageId(evidence_package_governance_id),
            runtime_id=RuntimeIdentifier(evidence_package_runtime_id),
        )
        command = RecordEvidencePackageCriterionResultCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(expected_persisted_version),
            criterion_id=criterion_id,
            recorded_at=recorded_at,
            result_label=result_label,
            summary=summary,
            evidence_references=evidence_references,
        )
        return entry_point(command)


def _result_payload(result: SaveResult) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one SaveResult."""
    return {
        "operation": result.operation.value,
        "persisted_version": str(result.persisted_version.value),
    }


def main() -> None:
    """Record one CriterionResult from CLI arguments, and print the result."""
    if len(sys.argv) not in (7, 8):
        raise SystemExit(
            "usage: empirical-platform-record-evidence-package-criterion-result "
            "<governance_id> <runtime_id> <expected_version> <criterion_id> "
            "<recorded_at_iso> <result_label> [summary]"
        )
    result = run_record_evidence_package_criterion_result(
        evidence_package_governance_id=sys.argv[1],
        evidence_package_runtime_id=sys.argv[2],
        expected_persisted_version=int(sys.argv[3]),
        criterion_id=sys.argv[4],
        recorded_at=datetime.fromisoformat(sys.argv[5]),
        result_label=sys.argv[6],
        summary=sys.argv[7] if len(sys.argv) > 7 else None,
    )
    print(json.dumps(_result_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
