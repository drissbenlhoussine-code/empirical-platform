"""Real end-to-end Review finding-recording composition root.

Composes the frozen MILESTONE-045 vertical slice through the shared
MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ReviewId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.add_review_finding import (
    AddReviewFindingCommand,
    AddReviewFindingHandler,
)


def run_add_review_finding(
    *,
    review_governance_id: str,
    review_runtime_id: str,
    expected_persisted_version: int,
    text: str,
    rationale: str | None = None,
    evidence_references: tuple[str, ...] = (),
    config: PostgreSQLConfigSnapshot | None = None,
) -> SaveResult:
    """Append one finding to a Review, end-to-end, against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = AddReviewFindingHandler(review_repository=runtime.reviews)
        entry_point = CommandEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=ReviewId(review_governance_id),
            runtime_id=RuntimeIdentifier(review_runtime_id),
        )
        command = AddReviewFindingCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(expected_persisted_version),
            text=text,
            rationale=rationale,
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
    """Append one finding from CLI arguments, and print the result."""
    if len(sys.argv) not in (5, 6):
        raise SystemExit(
            "usage: empirical-platform-add-review-finding "
            "<governance_id> <runtime_id> <expected_version> <text> [rationale]"
        )
    result = run_add_review_finding(
        review_governance_id=sys.argv[1],
        review_runtime_id=sys.argv[2],
        expected_persisted_version=int(sys.argv[3]),
        text=sys.argv[4],
        rationale=sys.argv[5] if len(sys.argv) > 5 else None,
    )
    print(json.dumps(_result_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
