"""Real end-to-end EvidencePackage retrieval composition root.

Composes the frozen MILESTONE-037 retrieval vertical slice through the
shared MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_evidence_package import (
    EvidencePackageSnapshot,
    GetEvidencePackageHandler,
    GetEvidencePackageQuery,
)


def run_get_evidence_package(
    *,
    evidence_package_governance_id: str,
    evidence_package_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> EvidencePackageSnapshot:
    """Retrieve one EvidencePackage end-to-end against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetEvidencePackageHandler(evidence_package_repository=runtime.evidence_packages)
        entry_point = QueryEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=EvidencePackageId(evidence_package_governance_id),
            runtime_id=RuntimeIdentifier(evidence_package_runtime_id),
        )
        return entry_point(GetEvidencePackageQuery(identity=identity))


def _snapshot_payload(snapshot: EvidencePackageSnapshot) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one EvidencePackageSnapshot."""
    return {
        "governance_id": str(snapshot.identity.governance_id),
        "runtime_id": str(snapshot.identity.runtime_id),
        "run_id": str(snapshot.run_id),
        "state": snapshot.state.value,
    }


def main() -> None:
    """Retrieve one EvidencePackage by identity, supplied as two CLI arguments, and print it."""
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-evidence-package <governance_id> <runtime_id>"
        )
    snapshot = run_get_evidence_package(
        evidence_package_governance_id=sys.argv[1],
        evidence_package_runtime_id=sys.argv[2],
    )
    print(json.dumps(_snapshot_payload(snapshot), sort_keys=True))


if __name__ == "__main__":
    main()
