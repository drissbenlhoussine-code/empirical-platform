"""Real end-to-end Review creation composition root.

Composes the frozen MILESTONE-042 creation vertical slice through the
shared MILESTONE-053 resource-lifecycle helper. Requires an existing
EvidencePackage (enforced by the database foreign key on
`review.target_evidence_package_id`, not validated here -- see the frozen
`CreateReviewCommand`'s own docstring).
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ReviewId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.create_review import CreateReviewCommand, CreateReviewHandler


def run_create_review(
    *,
    review_governance_id: str,
    target_evidence_package_governance_id: str,
    reviewer_reference: str,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> DomainIdentity[ReviewId]:
    """Create one Review for an existing EvidencePackage, end-to-end, against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    with postgres_repository_runtime(config) as runtime:
        handler = CreateReviewHandler(
            review_repository=runtime.reviews,
            runtime_identifier_generator=resolved_generator,
        )
        entry_point = CommandEntryPoint(handler)
        command = CreateReviewCommand(
            review_governance_id=review_governance_id,
            target_evidence_package_governance_id=target_evidence_package_governance_id,
            reviewer_reference=reviewer_reference,
        )
        return entry_point(command)


def _identity_payload(identity: DomainIdentity[ReviewId]) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one DomainIdentity."""
    return {
        "governance_id": str(identity.governance_id),
        "runtime_id": str(identity.runtime_id),
    }


def main() -> None:
    """Create one Review from CLI arguments, and print its new identity."""
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: empirical-platform-create-review "
            "<review_governance_id> <target_evidence_package_governance_id> <reviewer_reference>"
        )
    identity = run_create_review(
        review_governance_id=sys.argv[1],
        target_evidence_package_governance_id=sys.argv[2],
        reviewer_reference=sys.argv[3],
    )
    print(json.dumps(_identity_payload(identity), sort_keys=True))


if __name__ == "__main__":
    main()
