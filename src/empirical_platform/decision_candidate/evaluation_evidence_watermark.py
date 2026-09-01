"""MILESTONE-083 -- Persisted Receipt-Set Evaluation Evidence Watermark.

WHAT A WATERMARK PROVES, AND ONLY THIS. One persisted watermark row binds a
stable watermark governance identity to the EXACT set of M082
`receipt_governance_id` values visible to the schema-qualified capture query
executed by the INSERT statement that created it, under that statement's own
PostgreSQL transaction snapshot. "Visible" means visible to THAT STATEMENT
under ITS transaction snapshot -- not globally visible to every reader, and
not a claim about any other statement, transaction or point in time. The
BEFORE INSERT trigger installed by the M083 migration computes this set
itself and unconditionally replaces whatever a caller supplied, so the claim
holds for every persisted row, including one a direct SQL caller wrote.

WHAT IT DOES NOT PROVE. Not that any ResearchSession, DecisionCandidate,
brief or evaluation consumed this watermark -- that binding does not exist in
this milestone and requires a future evaluation-context milestone, not
started. Not evaluation time, capture time, or any wall-clock chronology.
Not receipt commit time or event commit time. Not historical availability at
an arbitrary timestamp or cutoff. Not receipt ordering, a committed prefix,
or any sequence authority -- the set is a SET, canonically ordered only for
deterministic storage and comparison. Not event payload, current or
historical. Not receipt metadata provenance. Not operator truth, broker
truth, fills or trades. Not that every M076 event has a receipt. Not that an
absent receipt did not exist at another time. Not that the set represents
all operator evidence anywhere. Not any future-tail or excluded-receipt
count. Not cryptographic sealing. Not protection against DDL authority,
trigger disabling, TRUNCATE, DROP or superuser mutation -- see the migration
docstring for the exact enforcement boundary.

WHY EXACTLY THIS AND NOT MORE. Attaching today's receipt inventory to an
already-completed ResearchSession would be a POST-HOC association, not
evidence that the decision used that set. M083 builds the primitive; it does
not claim any decision used it. See `external-review/MILESTONE-083/
current-authority.json` for the closed, machine-readable statement of this
authority.

IMMUTABILITY. Once persisted, a watermark's `receipt_governance_ids` never
changes: a later receipt insertion, even a backdated one, cannot alter an
existing watermark. Reading an existing watermark reads its stored set only
and never re-consults the current receipt inventory.
"""

from __future__ import annotations

from dataclasses import dataclass

# Reproduced from `decision_candidate/operator_event_receipt.py` (identical
# 29-codepoint Python 3.13 `str.strip()` blank set) rather than imported --
# `bare str.strip()` already IS this module's own invariant. The M083
# migration freezes the same set locally as SQL escapes; a test asserts the
# two agree character by character.
BLANK_CHARACTERS = (
    "\x09\x0a\x0b\x0c\x0d\x1c"
    "\x1d\x1e\x1f\x20\u0085\u00a0"
    "\u1680\u2000\u2001\u2002\u2003\u2004"
    "\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)

__all__ = [
    "BLANK_CHARACTERS",
    "EvaluationEvidenceWatermark",
]


@dataclass(frozen=True, slots=True)
class EvaluationEvidenceWatermark:
    """One immutable, database-computed receipt-identity set.

    `receipt_governance_ids` is a TUPLE, not a set, because the database
    stores and this type preserves ONE canonical order (ascending, `COLLATE
    "C"`) -- the tuple's order carries no authority of its own beyond being
    deterministic; it is not a commit order, an attestation order, or any
    other sequence claim. Every row this type is ever constructed from was
    computed by the M083 capture trigger, so the invariants checked below
    (no duplicates, ascending order) always hold for a genuine row; they are
    asserted here as a defensive, database-independent check of exactly the
    guarantee the trigger exists to provide, not a second competing
    definition of it.
    """

    watermark_governance_id: str
    receipt_governance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.watermark_governance_id.strip():
            raise ValueError("watermark_governance_id must be non-empty")
        if len(set(self.receipt_governance_ids)) != len(self.receipt_governance_ids):
            raise ValueError("receipt_governance_ids must not contain duplicates")
        if list(self.receipt_governance_ids) != sorted(self.receipt_governance_ids):
            raise ValueError("receipt_governance_ids must be in canonical ascending order")

    @property
    def captured_receipt_count(self) -> int:
        """The count derived from the stored set -- never a separate field."""
        return len(self.receipt_governance_ids)
