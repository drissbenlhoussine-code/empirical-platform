"""MILESTONE-082 -- handler wiring, exercised against an in-memory repository.

No database: these tests establish that each handler delegates to the port it
was given and returns exactly what the port produced, which is the part of the
usecase layer that does not depend on PostgreSQL.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from empirical_platform.decision_candidate.operator_event_receipt import (
    OperatorEventReceipt,
)
from empirical_platform.usecases.attest_operator_event_receipt import (
    AttestOperatorEventReceiptCommand,
    AttestOperatorEventReceiptHandler,
    GetAttestedEvidenceReportHandler,
    GetAttestedEvidenceReportQuery,
)

_CUTOFF = datetime(2026, 5, 1, tzinfo=UTC)


def _receipt(event_governance_id: str, label: datetime) -> OperatorEventReceipt:
    return OperatorEventReceipt(
        receipt_governance_id=f"RC-{event_governance_id}",
        event_governance_id=event_governance_id,
        system_received_at=label,
        attested_by="handler-suite",
        attester_version="M082.1",
    )


class _FakeReceipts:
    """Records what the handler asked for, and answers with fixed rows."""

    def __init__(self, rows: tuple[OperatorEventReceipt, ...] = ()) -> None:
        self.rows = rows
        self.attested: list[tuple[str, str, str]] = []
        self.cutoffs: list[datetime] = []

    def attest(
        self, *, receipt_governance_id: str, event_governance_id: str, attested_by: str
    ) -> OperatorEventReceipt:
        self.attested.append((receipt_governance_id, event_governance_id, attested_by))
        return _receipt(event_governance_id, datetime(2026, 4, 1, tzinfo=UTC))

    def get_for_event(self, event_governance_id: str) -> OperatorEventReceipt | None:
        return next((r for r in self.rows if r.event_governance_id == event_governance_id), None)

    def list_labelled_by(self, receipt_label_cutoff: datetime) -> tuple[OperatorEventReceipt, ...]:
        self.cutoffs.append(receipt_label_cutoff)
        return tuple(r for r in self.rows if r.system_received_at <= receipt_label_cutoff)

    def list_all(self) -> tuple[OperatorEventReceipt, ...]:
        return self.rows


def test_the_attest_handler_passes_the_command_through_unchanged() -> None:
    receipts = _FakeReceipts()
    handler = AttestOperatorEventReceiptHandler(operator_event_receipt_repository=receipts)
    result = handler.handle(
        AttestOperatorEventReceiptCommand(
            receipt_governance_id="RC-1", event_governance_id="EV-1", attested_by="caller"
        )
    )
    assert receipts.attested == [("RC-1", "EV-1", "caller")]
    assert result.event_governance_id == "EV-1"


def test_a_repository_failure_propagates_rather_than_reading_as_absence() -> None:
    """An infrastructure fault is not an absence of evidence."""

    class _Broken(_FakeReceipts):
        def attest(self, **_: object) -> OperatorEventReceipt:
            raise RuntimeError("connection lost")

    handler = AttestOperatorEventReceiptHandler(operator_event_receipt_repository=_Broken())
    with pytest.raises(RuntimeError, match="connection lost"):
        handler.handle(
            AttestOperatorEventReceiptCommand(
                receipt_governance_id="RC-2", event_governance_id="EV-2", attested_by="caller"
            )
        )


def test_the_report_handler_narrows_by_the_cutoff_in_the_repository() -> None:
    rows = (
        _receipt("EV-EARLY", datetime(2026, 4, 1, tzinfo=UTC)),
        _receipt("EV-LATE", datetime(2026, 6, 1, tzinfo=UTC)),
    )
    receipts = _FakeReceipts(rows)
    handler = GetAttestedEvidenceReportHandler(operator_event_receipt_repository=receipts)
    report = handler.handle(GetAttestedEvidenceReportQuery(receipt_label_cutoff=_CUTOFF))

    assert receipts.cutoffs == [_CUTOFF], "the cutoff must reach the store, not be applied after"
    assert report.attested_count == 1
    assert [e.event_governance_id for e in report.entries] == ["EV-EARLY"]
    assert report.receipt_label_cutoff == _CUTOFF


def test_a_receipt_labelled_after_the_cutoff_contributes_nothing() -> None:
    receipts = _FakeReceipts((_receipt("EV-FUTURE", datetime(2026, 9, 1, tzinfo=UTC)),))
    handler = GetAttestedEvidenceReportHandler(operator_event_receipt_repository=receipts)
    report = handler.handle(GetAttestedEvidenceReportQuery(receipt_label_cutoff=_CUTOFF))
    assert report.attested_count == 0
    assert report.entries == ()
