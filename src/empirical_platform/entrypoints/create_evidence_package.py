"""Real end-to-end EvidencePackage creation composition root.

Composes the frozen MILESTONE-036 creation vertical slice through the
shared MILESTONE-053 resource-lifecycle helper. Requires an existing Run
(enforced by the database foreign key on `evidence_package.run_id`, not
validated here -- see the frozen `CreateEvidencePackageCommand`'s own
docstring).
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.create_evidence_package import (
    CreateEvidencePackageCommand,
    CreateEvidencePackageHandler,
)


def run_create_evidence_package(
    *,
    evidence_package_governance_id: str,
    run_governance_id: str,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> DomainIdentity[EvidencePackageId]:
    """Create one EvidencePackage for an existing Run, end-to-end, against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    with postgres_repository_runtime(config) as runtime:
        handler = CreateEvidencePackageHandler(
            evidence_package_repository=runtime.evidence_packages,
            runtime_identifier_generator=resolved_generator,
        )
        entry_point = CommandEntryPoint(handler)
        command = CreateEvidencePackageCommand(
            evidence_package_governance_id=evidence_package_governance_id,
            run_governance_id=run_governance_id,
        )
        return entry_point(command)


def _identity_payload(identity: DomainIdentity[EvidencePackageId]) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one DomainIdentity."""
    return {
        "governance_id": str(identity.governance_id),
        "runtime_id": str(identity.runtime_id),
    }


def main() -> None:
    """Create one EvidencePackage from CLI arguments, and print its new identity."""
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-create-evidence-package "
            "<evidence_package_governance_id> <run_governance_id>"
        )
    identity = run_create_evidence_package(
        evidence_package_governance_id=sys.argv[1],
        run_governance_id=sys.argv[2],
    )
    print(json.dumps(_identity_payload(identity), sort_keys=True))


if __name__ == "__main__":
    main()
