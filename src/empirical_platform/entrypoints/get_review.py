"""Real end-to-end Review retrieval composition root.

Composes the frozen MILESTONE-043 retrieval vertical slice through the
shared MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ReviewId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_review import GetReviewHandler, GetReviewQuery, ReviewSnapshot


def run_get_review(
    *,
    review_governance_id: str,
    review_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> ReviewSnapshot:
    """Retrieve one Review end-to-end against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetReviewHandler(review_repository=runtime.reviews)
        entry_point = QueryEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=ReviewId(review_governance_id),
            runtime_id=RuntimeIdentifier(review_runtime_id),
        )
        return entry_point(GetReviewQuery(identity=identity))


def _snapshot_payload(snapshot: ReviewSnapshot) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one ReviewSnapshot."""
    return {
        "governance_id": str(snapshot.identity.governance_id),
        "runtime_id": str(snapshot.identity.runtime_id),
        "target_evidence_package_id": str(snapshot.target_evidence_package_id),
        "reviewer_reference": snapshot.reviewer_reference,
        "state": snapshot.state.value,
    }


def main() -> None:
    """Retrieve one Review by identity, supplied as two CLI arguments, and print it."""
    if len(sys.argv) != 3:
        raise SystemExit("usage: empirical-platform-get-review <governance_id> <runtime_id>")
    snapshot = run_get_review(
        review_governance_id=sys.argv[1],
        review_runtime_id=sys.argv[2],
    )
    print(json.dumps(_snapshot_payload(snapshot), sort_keys=True))


if __name__ == "__main__":
    main()
