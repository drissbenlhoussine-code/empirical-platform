"""MILESTONE-079. Point-in-time operator evidence snapshot.

Read-only with respect to M076: the ledger is consumed through its frozen
public contract and neither its fold nor its `as_of` semantics are altered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.operator_evidence_availability import (
    OperatorEvidenceSnapshot,
    build_operator_evidence_snapshot,
)
from empirical_platform.decision_candidate.operator_position_ledger_repository import (
    OperatorPositionLedgerRepository,
)

__all__ = [
    "GetOperatorEvidenceSnapshotHandler",
    "GetOperatorEvidenceSnapshotQuery",
]


@dataclass(frozen=True, slots=True)
class GetOperatorEvidenceSnapshotQuery:
    """Both cutoffs are required and inclusive.

    Neither has a default: a default on either dimension would silently choose
    an epistemic stance, and the two answer genuinely different questions.
    """

    effective_as_of: datetime
    knowledge_as_of: datetime

    def __post_init__(self) -> None:
        # Rejected here, at construction, before any I/O -- a malformed REQUEST
        # must never be reported as a claim about the persisted data. The M078
        # R03 lesson, applied to both dimensions.
        for label, moment in (
            ("effective_as_of", self.effective_as_of),
            ("knowledge_as_of", self.knowledge_as_of),
        ):
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise ValueError(f"{label} must be timezone-aware; a naive datetime has no instant")


class GetOperatorEvidenceSnapshotHandler:
    """Read the ledger once and project it at a knowledge cutoff."""

    __slots__ = ("_ledger",)

    def __init__(
        self,
        *,
        operator_position_ledger_repository: OperatorPositionLedgerRepository | None = None,
    ) -> None:
        self._ledger = operator_position_ledger_repository

    def handle(self, query: GetOperatorEvidenceSnapshotQuery) -> OperatorEvidenceSnapshot:
        if self._ledger is None:
            return build_operator_evidence_snapshot(
                events=(),
                effective_as_of=query.effective_as_of,
                knowledge_as_of=query.knowledge_as_of,
                ledger_available=False,
            )
        # A database-level failure propagates: a dead connection is an
        # infrastructure fault, not an absence of evidence.
        return build_operator_evidence_snapshot(
            events=self._ledger.list_all(),
            effective_as_of=query.effective_as_of,
            knowledge_as_of=query.knowledge_as_of,
        )
