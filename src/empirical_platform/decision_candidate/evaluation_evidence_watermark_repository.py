"""MILESTONE-083 persistence-neutral contract for evaluation evidence watermarks.

There is deliberately NO update and NO delete method, and NO method that
accepts a receipt identity, a timestamp, a cutoff, a sequence or a count from
the caller. The absence of those parameters is the application-layer half of
the exactness guarantee; the database's BEFORE INSERT trigger, which computes
and unconditionally overwrites the stored set itself, is the other half.
"""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)

__all__ = ["EvaluationEvidenceWatermarkRepository"]


class EvaluationEvidenceWatermarkRepository(Protocol):
    """Append-only store of persisted receipt-set evidence watermarks."""

    def capture(self, *, watermark_governance_id: str) -> EvaluationEvidenceWatermark:
        """Persist one watermark, database-computed, for `watermark_governance_id`.

        The caller supplies ONLY the identity. Implementations MUST NOT accept
        a receipt identity, a timestamp, a cutoff, a sequence or a count as a
        parameter here -- the database alone determines
        `receipt_governance_ids`, from one schema-qualified query executed by
        the same INSERT statement, under that statement's own transaction
        snapshot.

        Idempotent BY IDENTITY: a second call with the same
        `watermark_governance_id` returns the already-persisted watermark
        unchanged rather than attempting a second capture. A watermark, once
        persisted, is immutable -- retrying with the same id must never be
        able to produce a different stored set for it, no matter what
        receipts exist at retry time.
        """
        ...

    def get(self, watermark_governance_id: str) -> EvaluationEvidenceWatermark | None:
        """The persisted watermark for this identity, or None if never captured.

        Implementations MUST read the STORED set only. This method MUST NOT
        consult the current receipt inventory in any way -- doing so would
        let a later receipt insertion change what an earlier watermark reads
        as, which is exactly the guarantee this milestone exists to prevent.
        """
        ...
