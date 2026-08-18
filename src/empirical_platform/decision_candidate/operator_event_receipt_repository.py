"""MILESTONE-082 persistence-neutral contract for the append-only receipt store.

There is deliberately NO update and NO delete method. The absence of those
methods is the application-layer half of the immutability guarantee; the
database trigger is the other half.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from empirical_platform.decision_candidate.operator_event_receipt import OperatorEventReceipt

__all__ = ["OperatorEventReceiptRepository"]


class OperatorEventReceiptRepository(Protocol):
    """Append-only store of system receipt attestations."""

    def attest(
        self, *, receipt_governance_id: str, event_governance_id: str, attested_by: str
    ) -> OperatorEventReceipt:
        """Attest that the event was READ BACK as already durably committed.

        Implementations MUST run in a transaction of their own, separate from
        the one that appended the event, and MUST read the event back before
        creating the receipt. That ORDERING is the whole claim, and it is
        causal: it holds regardless of any clock. Assigning a timestamp inside
        the ingesting transaction was proved to leak knowledge.

        ON THE SANCTIONED attest() PATH the `system_received_at` an
        implementation records is obtained from the application host clock after
        the read-back, `attester_version` is an application constant, and
        `attested_by` is caller-supplied and passed through unchanged. It is NOT
        a proven bound on the event's commit time, and implementations MUST NOT
        present it as one.

        AS A GENERIC PERSISTED VALUE all three have UNAUTHENTICATED PROVENANCE.
        A row this port never produced is mapped into the same type and cannot
        be told apart, so no reader may infer an origin from a stored row.

        RETRACTED (owner finding 20): this said the recorded label "is a
        SYSTEM-ASSIGNED LABEL" without qualifying which path assigns it.

        Idempotent by event: a second call returns the existing receipt rather
        than creating a second authority.
        """
        ...

    def get_for_event(self, event_governance_id: str) -> OperatorEventReceipt | None:
        """The receipt for one event, or None if it has never been attested."""
        ...

    def list_labelled_by(self, receipt_label_cutoff: datetime) -> tuple[OperatorEventReceipt, ...]:
        """Only receipts labelled at or before the cutoff, narrowed BY THE STORE.

        Implementations MUST apply the cutoff in the query, not after mapping.
        A row beyond the cutoff must never be fetched, mapped or validated --
        owner review finding 9, where a malformed far-future row decided whether
        an earlier-cutoff report could be built at all.
        """
        ...

    def list_all(self) -> tuple[OperatorEventReceipt, ...]:
        """Every receipt, ordered by (system_received_at, event_governance_id).

        Deterministic ordering only. This is NOT an ordering authority. The
        authoritative report uses `list_labelled_by`, never this.
        """
        ...
