"""Real end-to-end Review completion composition root.

Composes the frozen MILESTONE-046 vertical slice through the shared
MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ReviewId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.complete_review import (
    CompleteReviewCommand,
    CompleteReviewHandler,
    ReviewDisposition,
)


def run_complete_review(
    *,
    review_governance_id: str,
    review_runtime_id: str,
    expected_persisted_version: int,
    disposition: ReviewDisposition,
    final_disposition_rationale: str,
    actor: str,
    occurred_at: datetime,
    correlation_id: str | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> SaveResult:
    """Complete one Review, end-to-end, against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = CompleteReviewHandler(review_repository=runtime.reviews)
        entry_point = CommandEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=ReviewId(review_governance_id),
            runtime_id=RuntimeIdentifier(review_runtime_id),
        )
        command = CompleteReviewCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(expected_persisted_version),
            disposition=disposition,
            final_disposition_rationale=final_disposition_rationale,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
        )
        return entry_point(command)


def _result_payload(result: SaveResult) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one SaveResult."""
    return {
        "operation": result.operation.value,
        "persisted_version": str(result.persisted_version.value),
    }


def main() -> None:
    """Complete one Review from CLI arguments, and print the result."""
    if len(sys.argv) not in (8, 9):
        raise SystemExit(
            "usage: empirical-platform-complete-review "
            "<governance_id> <runtime_id> <expected_version> <disposition> "
            "<final_disposition_rationale> <actor> <occurred_at_iso> [correlation_id]"
        )
    result = run_complete_review(
        review_governance_id=sys.argv[1],
        review_runtime_id=sys.argv[2],
        expected_persisted_version=int(sys.argv[3]),
        disposition=ReviewDisposition(sys.argv[4]),
        final_disposition_rationale=sys.argv[5],
        actor=sys.argv[6],
        occurred_at=datetime.fromisoformat(sys.argv[7]),
        correlation_id=sys.argv[8] if len(sys.argv) > 8 else None,
    )
    print(json.dumps(_result_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
