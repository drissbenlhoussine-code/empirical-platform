"""MILESTONE-083 evaluation evidence watermark persistence.

THE DATABASE COMPUTES THE SET, NOT THIS CLASS. `capture` issues one INSERT
naming only `watermark_governance_id`; the BEFORE INSERT trigger installed by
the M083 migration (`evaluation_evidence_watermark_capture_receipt_set`)
overwrites `receipt_governance_ids` unconditionally with its own
schema-qualified query against `public.operator_event_receipt`, inside the
same statement, inside the same transaction. This class never constructs,
reads back for comparison, or trusts any receipt-identity list of its own;
it only reads whatever the trigger persisted.

IMMUTABILITY is the same narrow shape M082 established: a BEFORE UPDATE OR
DELETE trigger refuses both at the row level. TRUNCATE, DROP and superuser
mutation are outside that boundary -- see the migration docstring.

IDENTITY UNIQUENESS IS THE ONLY IDEMPOTENCY MECHANISM. `capture` checks for
an existing watermark first (cheap, and the common case), then attempts the
INSERT; a unique-violation on the primary key means a concurrent caller won
the race, and this reads back and returns THAT row rather than raising. No
row is ever partially written: a failed or rolled-back INSERT leaves nothing,
because the trigger-computed array and every constraint are validated inside
one statement inside one transaction.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.shared.errors.foundation import FoundationError
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

__all__ = ["PostgresEvaluationEvidenceWatermarkRepository"]

_WATERMARK_PRIMARY_KEY_CONSTRAINT = "pk_evaluation_evidence_watermark"


class PostgresEvaluationEvidenceWatermarkRepository:
    """PostgreSQL-backed append-only store of evaluation evidence watermarks."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def capture(self, *, watermark_governance_id: str) -> EvaluationEvidenceWatermark:
        """Persist one database-computed watermark, idempotent by identity.

        Deliberately no ORM-style existence check-then-insert race guard
        beyond what the primary key already provides: the pre-check below is
        purely an optimisation for the common non-racing case, and the
        unique-violation branch is what actually makes concurrent captures of
        the same identity safe.
        """
        existing = self.get(watermark_governance_id)
        if existing is not None:
            return existing

        with self._service.unit_of_work() as work:
            try:
                rows = work.execute(
                    "INSERT INTO public.evaluation_evidence_watermark "
                    "(watermark_governance_id) VALUES (:watermark_governance_id) "
                    "RETURNING watermark_governance_id, receipt_governance_ids",
                    {"watermark_governance_id": watermark_governance_id},
                )
            except FoundationError as exc:
                # A concurrent capture of the SAME identity: the database
                # decides the winner. The loser reports the winner's
                # watermark, not a fault -- mirroring M082's `attest`.
                if unique_violation_constraint_name(exc) != _WATERMARK_PRIMARY_KEY_CONSTRAINT:
                    raise
                conflicted = True
            else:
                conflicted = False
                watermark = _row_to_watermark(rows[0])

        if conflicted:
            winner = self.get(watermark_governance_id)
            if winner is None:  # pragma: no cover - the row must exist to conflict
                raise RuntimeError(
                    f"watermark {watermark_governance_id!r} conflicted but cannot be read back"
                )
            return winner
        return watermark

    def get(self, watermark_governance_id: str) -> EvaluationEvidenceWatermark | None:
        """Read the STORED set only. Never consults the receipt inventory."""
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT watermark_governance_id, receipt_governance_ids "
                    "FROM public.evaluation_evidence_watermark "
                    "WHERE watermark_governance_id = :watermark_governance_id",
                    {"watermark_governance_id": watermark_governance_id},
                )
            )
        if not rows:
            return None
        return _row_to_watermark(rows[0])


def _row_to_watermark(row: Mapping[str, Any]) -> EvaluationEvidenceWatermark:
    receipt_ids = row["receipt_governance_ids"]
    return EvaluationEvidenceWatermark(
        watermark_governance_id=str(row["watermark_governance_id"]),
        receipt_governance_ids=tuple(str(r) for r in receipt_ids),
    )
