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
from empirical_platform.shared.errors.foundation import FoundationError, FoundationErrorCategory
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


def _require_str(value: object, *, field: str, index: int | None = None) -> str:
    """Return `value` only if it really is a string; never coerce it into one.

    AUDIT FINDING M083-AUD-001, fail-closed by design. This function used to
    read `str(value)`. That silently CONVERTED a malformed persisted value
    into a valid-looking governance identity instead of refusing it: a stored
    NULL array element became the receipt identity `'None'`, a `memoryview`
    became `'<memory at 0x...>'`, and an integer became `'1'` -- each of them
    then counted by `captured_receipt_count` as though it were a real M082
    receipt. That directly contradicts the one thing this milestone claims
    (the EXACT receipt-identity set), so the coercion is removed rather than
    documented.

    A NULL array ELEMENT is physically representable here even though the
    column is `NOT NULL`: in PostgreSQL that constraint applies to the array
    value, not to its members, so `ARRAY['real-id', NULL]` is a legal value
    for this column. The capture trigger cannot produce one (it aggregates a
    primary-key column), but the trigger is not the only writer the schema
    admits -- `ALTER TABLE ... DISABLE TRIGGER`, DDL authority and a superuser
    are all explicitly OUTSIDE this milestone's enforcement boundary and are
    named as such in `current-authority.json`'s `structural_limitations`.
    Reading a row back is exactly where that boundary should be noticed, not
    papered over.

    The domain type's own duplicate/canonical-order checks are NOT a
    substitute: they caught the NULL case only INCIDENTALLY, and only for
    identities that happen to sort after `'None'`. `['A-real-id', NULL]` is
    still ascending once stringified, so it passed. An incidental rejection
    for the wrong reason is not a type check.

    No coercion is needed for a well-formed row: this repository reads through
    SQLAlchemy's `result.mappings()` over psycopg, which returns `str` for a
    `VARCHAR` column and `list[str]` for an `ARRAY(String)` column -- measured
    directly against this schema, empty array included.
    """
    if not isinstance(value, str):
        where = field if index is None else f"{field}[{index}]"
        raise FoundationError(
            category=FoundationErrorCategory.PERSISTENCE,
            message=(
                f"persisted evaluation_evidence_watermark value {where} is "
                f"{type(value).__name__}, not str; refusing to coerce a malformed "
                "stored value into a governance identity"
            ),
            layer="persistence",
            operation="evaluation_evidence_watermark.row_mapping",
            context={"field": where, "actual_type": type(value).__name__},
        )
    return value


def _row_to_watermark(row: Mapping[str, Any]) -> EvaluationEvidenceWatermark:
    receipt_ids = row["receipt_governance_ids"]
    if not isinstance(receipt_ids, list | tuple):
        raise FoundationError(
            category=FoundationErrorCategory.PERSISTENCE,
            message=(
                "persisted evaluation_evidence_watermark receipt_governance_ids is "
                f"{type(receipt_ids).__name__}, not an array; refusing to read it as "
                "a receipt-identity set"
            ),
            layer="persistence",
            operation="evaluation_evidence_watermark.row_mapping",
            context={"actual_type": type(receipt_ids).__name__},
        )
    return EvaluationEvidenceWatermark(
        watermark_governance_id=_require_str(
            row["watermark_governance_id"], field="watermark_governance_id"
        ),
        receipt_governance_ids=tuple(
            _require_str(value, field="receipt_governance_ids", index=position)
            for position, value in enumerate(receipt_ids)
        ),
    )
