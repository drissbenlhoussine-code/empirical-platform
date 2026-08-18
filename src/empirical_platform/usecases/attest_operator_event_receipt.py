"""MILESTONE-082 attestation command and receipt-label-cutoff view query."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.operator_event_receipt import (
    AttestedEvidenceReport,
    OperatorEventReceipt,
    build_attested_evidence_report,
)
from empirical_platform.decision_candidate.operator_event_receipt_repository import (
    OperatorEventReceiptRepository,
)

__all__ = [
    "AttestOperatorEventReceiptCommand",
    "AttestOperatorEventReceiptHandler",
    "GetAttestedEvidenceReportHandler",
    "GetAttestedEvidenceReportQuery",
]


@dataclass(frozen=True, slots=True)
class AttestOperatorEventReceiptCommand:
    """Attest one already-committed M076 event.

    There is DELIBERATELY no timestamp parameter. ON THE SANCTIONED attest()
    PATH the persistence boundary issues the clock CALL that produces the LABEL
    only AFTER it reads the event back as committed; letting a caller supply it
    would recreate exactly the operator-supplied-time weakness this milestone
    exists to close.

    That ordering is CAUSAL and applies to the call, not to the value: the label
    the call returns proves no wall-clock chronology, and AS A GENERIC PERSISTED
    VALUE it has UNAUTHENTICATED PROVENANCE.

    SUPERSEDED (owner finding 22): this said "the attestation instant is taken
    by the persistence boundary AFTER it reads the event back", naming the label
    an instant and attributing the call's ordering to the value.
    """

    receipt_governance_id: str
    event_governance_id: str
    attested_by: str

    def __post_init__(self) -> None:
        for label, value in (
            ("receipt_governance_id", self.receipt_governance_id),
            ("event_governance_id", self.event_governance_id),
            ("attested_by", self.attested_by),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")


class AttestOperatorEventReceiptHandler:
    """Writes one receipt through the append-only receipt repository."""

    __slots__ = ("_receipts",)

    def __init__(
        self, *, operator_event_receipt_repository: OperatorEventReceiptRepository
    ) -> None:
        self._receipts = operator_event_receipt_repository

    def handle(self, command: AttestOperatorEventReceiptCommand) -> OperatorEventReceipt:
        # A database-level failure PROPAGATES, as in M079 through M081: an
        # infrastructure fault is not an absence of evidence, and disguising it
        # would be a false diagnosis about the operator's data.
        return self._receipts.attest(
            receipt_governance_id=command.receipt_governance_id,
            event_governance_id=command.event_governance_id,
            attested_by=command.attested_by,
        )


@dataclass(frozen=True, slots=True)
class GetAttestedEvidenceReportQuery:
    """The cutoff is required. Defaulting it would choose an epistemic stance.

    RENAMED from `attested_as_of` by Owner review finding 2. "As of" asserted a
    point-in-time KNOWLEDGE claim the persisted label cannot support; this
    field selects receipts by their LABEL and nothing more.
    """

    receipt_label_cutoff: datetime

    def __post_init__(self) -> None:
        if (
            self.receipt_label_cutoff.tzinfo is None
            or self.receipt_label_cutoff.utcoffset() is None
        ):
            raise ValueError(
                "receipt_label_cutoff must be timezone-aware; a naive datetime has no instant"
            )


class GetAttestedEvidenceReportHandler:
    """Builds the receipt-label-cutoff view from ONE read of ONE store.

    NO LEDGER DEPENDENCY (owner review findings 7 and 10). This handler used to
    call `ledger.list_all()` and then `receipts.list_all()`. Two consequences,
    both executed:

      * the artifact resolved position and instrument from the CURRENT M076 row,
        so mutating that row after attestation changed the report while the
        receipt stayed identical;
      * the two reads were not atomic. An event and its receipt committing
        between them produced a since-REMOVED type,
        `MissingAttestedEventError` -- an "unreachable" inconsistency during  (QUOTED-DEFECT)
        ordinary sanctioned concurrency.

    One store, one query, narrowed by the cutoff in SQL. Neither failure has a
    mechanism left.
    """

    __slots__ = ("_receipts",)

    def __init__(
        self, *, operator_event_receipt_repository: OperatorEventReceiptRepository
    ) -> None:
        self._receipts = operator_event_receipt_repository

    def handle(self, query: GetAttestedEvidenceReportQuery) -> AttestedEvidenceReport:
        return build_attested_evidence_report(
            receipts=self._receipts.list_labelled_by(query.receipt_label_cutoff),
            receipt_label_cutoff=query.receipt_label_cutoff,
        )
