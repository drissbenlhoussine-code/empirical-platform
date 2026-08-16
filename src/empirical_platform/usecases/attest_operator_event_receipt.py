"""MILESTONE-082 attestation command and attested-snapshot query."""

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
from empirical_platform.decision_candidate.operator_position_ledger_repository import (
    OperatorPositionLedgerRepository,
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

    There is DELIBERATELY no timestamp parameter. The attestation instant is
    taken by the persistence boundary AFTER it reads the event back as
    committed; letting a caller supply it would recreate exactly the
    operator-supplied-time weakness this milestone exists to close.
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
    point-in-time KNOWLEDGE claim the system-assigned label cannot support; this
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
    """Builds the receipt-cutoff snapshot from the M082 receipts.

    The ledger is read only to resolve the detail of events that a qualifying
    receipt already names. The domain builder is receipts-first, so no ledger
    row without such a receipt can reach the artifact -- see Owner review
    finding 1, which retracted the earlier ledger-first construction.
    """

    __slots__ = ("_ledger", "_receipts")

    def __init__(
        self,
        *,
        operator_position_ledger_repository: OperatorPositionLedgerRepository,
        operator_event_receipt_repository: OperatorEventReceiptRepository,
    ) -> None:
        self._ledger = operator_position_ledger_repository
        self._receipts = operator_event_receipt_repository

    def handle(self, query: GetAttestedEvidenceReportQuery) -> AttestedEvidenceReport:
        return build_attested_evidence_report(
            events=self._ledger.list_all(),
            receipts=self._receipts.list_all(),
            receipt_label_cutoff=query.receipt_label_cutoff,
        )
