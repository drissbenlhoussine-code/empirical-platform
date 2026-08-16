"""MILESTONE-082 focused unit tests. Every test names the claim it defends."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.operator_event_receipt import (
    ATTESTED_EVIDENCE_BANNER,
    AttestedEvidenceReport,
    AttestedEvidenceStatus,
    OperatorEventReceipt,
    attested_known_by,
    build_attested_evidence_report,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.usecases.attest_operator_event_receipt import (
    AttestOperatorEventReceiptCommand,
    GetAttestedEvidenceReportQuery,
)
from empirical_platform.usecases.attested_evidence_io import (
    render_attested_evidence_report_json,
    render_attested_evidence_report_text,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)

FORBIDDEN_TOKENS = (
    "COMMIT_TIME",
    "COMMITTED_AT",
    "TRUE_TIME",
    "ACTUAL_TIME",
    "VERIFIED",
    "GUARANTEED",
    "PROOF",
    "TRUSTED_TIME",
    "SEQUENCE",
    "COMMIT_ORDER",
    "RECORDED_AT",
)


def event(
    n: int,
    *,
    position: str = "POS-1",
    symbol: str = "AAPL",
    day: int = 1,
    recorded_day: int | None = None,
) -> OperatorAssertedPositionEvent:
    return OperatorAssertedPositionEvent(
        governance_id=f"EVT-{n}",
        runtime_id=f"RUN-{n}",
        position_governance_id=position,
        instrument_symbol=symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=1,
        asserted_price=Decimal("100"),
        event_timestamp=BASE + timedelta(days=day),
        recorded_at=BASE + timedelta(days=recorded_day if recorded_day is not None else day),
        source_position_plan_governance_id=None,
        note=None,
    )


def receipt(n: int, *, received_day: int) -> OperatorEventReceipt:
    return OperatorEventReceipt(
        receipt_governance_id=f"RCPT-{n}",
        event_governance_id=f"EVT-{n}",
        system_received_at=BASE + timedelta(days=received_day),
        attested_by="test-attester",
        attester_version="M082.1",
    )


def report(
    events: Iterable[OperatorAssertedPositionEvent],
    receipts: Iterable[OperatorEventReceipt],
    *,
    cutoff_day: int,
) -> AttestedEvidenceReport:
    return build_attested_evidence_report(
        events=tuple(events),
        receipts=tuple(receipts),
        attested_as_of=BASE + timedelta(days=cutoff_day),
    )


# --------------------------------------------------------------------------
# The authority level, and its one-directional guarantee
# --------------------------------------------------------------------------


def test_an_event_attested_before_the_cutoff_is_attested() -> None:
    entry = report([event(1)], [receipt(1, received_day=5)], cutoff_day=10).entries[0]
    assert entry.status is AttestedEvidenceStatus.ATTESTED
    assert entry.system_received_at == BASE + timedelta(days=5)


def test_a_receipt_after_the_cutoff_does_not_leak_its_instant() -> None:
    """CLAIM: at this cutoff the platform did not yet hold the receipt."""
    entry = report([event(1)], [receipt(1, received_day=20)], cutoff_day=10).entries[0]
    assert entry.status is AttestedEvidenceStatus.ATTESTED_AFTER_CUTOFF
    assert entry.system_received_at is None
    assert entry.attested_by is None


@pytest.mark.parametrize(("cutoff_day", "expected"), [(4, False), (5, True), (6, True)])
def test_the_cutoff_is_inclusive(cutoff_day: int, expected: bool) -> None:
    known = attested_known_by(
        (event(1),), (receipt(1, received_day=5),), BASE + timedelta(days=cutoff_day)
    )
    assert (len(known) == 1) is expected


def test_attested_known_by_never_reads_recorded_at() -> None:
    """CLAIM: a deliberately false recorded_at cannot influence M082."""
    honest = event(1, day=1, recorded_day=1)
    liar = event(2, day=1, recorded_day=-3650)  # claims it was recorded a decade early
    receipts = (receipt(1, received_day=5), receipt(2, received_day=5))
    known = attested_known_by((honest, liar), receipts, BASE + timedelta(days=10))
    assert {e.governance_id for e in known} == {"EVT-1", "EVT-2"}
    # And with both receipts after the cutoff, the liar gains nothing from its lie.
    late = (receipt(1, received_day=20), receipt(2, received_day=20))
    assert attested_known_by((honest, liar), late, BASE + timedelta(days=10)) == ()


# --------------------------------------------------------------------------
# Legacy absence is never filled in
# --------------------------------------------------------------------------


def test_an_unreceipted_event_reports_absence_and_never_a_backfilled_instant() -> None:
    liar = event(1, day=1, recorded_day=-3650)
    entry = report([liar], [], cutoff_day=10).entries[0]
    assert entry.status is AttestedEvidenceStatus.NO_SYSTEM_RECEIPT_EVIDENCE
    assert entry.system_received_at is None
    assert entry.attested_by is None


def test_an_unreceipted_event_still_appears_in_the_report() -> None:
    rep = report([event(1)], [], cutoff_day=10)
    assert len(rep.entries) == 1
    assert rep.unattested_count == 1
    assert rep.attested_count == 0
    rendered = render_attested_evidence_report_text(rep)
    assert "NOT filled in from recorded_at or event_timestamp" in rendered


def test_counts_partition_the_entries_exactly() -> None:
    rep = report(
        [event(1), event(2, position="POS-2"), event(3, position="POS-3")],
        [receipt(1, received_day=5), receipt(2, received_day=50)],
        cutoff_day=10,
    )
    assert (rep.attested_count, rep.attested_after_cutoff_count, rep.unattested_count) == (1, 1, 1)
    assert rep.attested_count + rep.attested_after_cutoff_count + rep.unattested_count == len(
        rep.entries
    )


# --------------------------------------------------------------------------
# Vocabulary and the honesty surface
# --------------------------------------------------------------------------


@pytest.mark.parametrize("token", FORBIDDEN_TOKENS)
def test_no_forbidden_token_appears_in_any_closed_vocabulary(token: str) -> None:
    """CLAIM: no field, enum or JSON key claims commit time, true time or a sequence."""
    rep = report([event(1)], [receipt(1, received_day=5)], cutoff_day=10)
    payload = render_attested_evidence_report_json(rep)
    surfaces = [
        *(f for f in type(rep).__dataclass_fields__),
        *(f for f in type(rep.entries[0]).__dataclass_fields__),
        *(str(m) for m in AttestedEvidenceStatus),
        *payload,
        *payload["entries"][0],
    ]
    for surface in surfaces:
        assert token not in surface.upper().replace(" ", "_"), surface


def test_the_banner_denies_every_reading_m082_does_not_support() -> None:
    for denial in (
        "does NOT assert the event's COMMIT TIME",
        "SYSTEM-ASSIGNED, never actual time",
        "does NOT assert that the operator's assertion is true",
        "ONE DIRECTION ONLY",
        "UNDERSTATE",
        "can never OVERSTATE",
        "NO receipt are NOT attested",
        "NEVER filled in from recorded_at",
        "NO ordering authority is emitted",
        "does NOT change, wrap or strengthen M079, M080 or M081",
    ):
        assert denial in ATTESTED_EVIDENCE_BANNER, denial


def test_no_monetary_or_performance_value_is_emitted() -> None:
    rep = report([event(1)], [receipt(1, received_day=5)], cutoff_day=10)
    payload = json.dumps(render_attested_evidence_report_json(rep)).lower()
    keys = set(render_attested_evidence_report_json(rep)) | set(
        render_attested_evidence_report_json(rep)["entries"][0]
    )
    for forbidden in ("price", "quantity", "ratio", "result", "profit", "return"):
        assert not any(forbidden in k.lower() for k in keys), forbidden
    assert "%" not in payload


# --------------------------------------------------------------------------
# Structure, ordering and boundaries
# --------------------------------------------------------------------------


def test_entries_are_ordered_deterministically_with_unattested_last() -> None:
    rep = report(
        [event(1), event(2, position="POS-2"), event(3, position="POS-3")],
        [receipt(2, received_day=3), receipt(1, received_day=7)],
        cutoff_day=10,
    )
    assert [e.event_governance_id for e in rep.entries] == ["EVT-2", "EVT-1", "EVT-3"]


def test_a_naive_cutoff_is_refused_everywhere() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_attested_evidence_report(events=(), receipts=(), attested_as_of=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="timezone-aware"):
        attested_known_by((), (), datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="timezone-aware"):
        GetAttestedEvidenceReportQuery(attested_as_of=datetime(2026, 1, 1))


def test_a_naive_receipt_instant_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        OperatorEventReceipt(
            receipt_governance_id="R",
            event_governance_id="E",
            system_received_at=datetime(2026, 1, 1),
            attested_by="x",
            attester_version="M082.1",
        )


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_identities_are_refused(blank: str) -> None:
    with pytest.raises(ValueError):
        OperatorEventReceipt(
            receipt_governance_id=blank,
            event_governance_id="E",
            system_received_at=BASE,
            attested_by="x",
            attester_version="M082.1",
        )
    with pytest.raises(ValueError):
        AttestOperatorEventReceiptCommand(
            receipt_governance_id="R", event_governance_id=blank, attested_by="x"
        )


def test_the_command_has_no_timestamp_parameter() -> None:
    """CLAIM: a caller cannot supply the attestation instant.

    Letting them would recreate the operator-supplied-time weakness this
    milestone exists to close.
    """
    fields = set(AttestOperatorEventReceiptCommand.__dataclass_fields__)
    assert fields == {"receipt_governance_id", "event_governance_id", "attested_by"}
    for suspicious in ("system_received_at", "received_at", "timestamp", "at"):
        assert suspicious not in fields


def test_text_and_json_agree_and_json_is_deterministic() -> None:
    rep = report(
        [event(1), event(2, position="POS-2")], [receipt(1, received_day=5)], cutoff_day=10
    )
    text = render_attested_evidence_report_text(rep)
    payload = render_attested_evidence_report_json(rep)
    assert payload["attested_count"] == rep.attested_count
    for entry in payload["entries"]:
        assert entry["event_governance_id"] in text
    assert json.dumps(payload, sort_keys=True) == json.dumps(
        render_attested_evidence_report_json(rep), sort_keys=True
    )


def test_an_empty_ledger_still_carries_every_limitation() -> None:
    rep = report([], [], cutoff_day=10)
    assert rep.entries == ()
    assert len(rep.limitations) == 10
    assert any("UPPER BOUND WITNESS" in lim for lim in rep.limitations)
    assert any("ONE-DIRECTIONAL" in lim for lim in rep.limitations)
    assert any("track_commit_timestamp" in lim for lim in rep.limitations)
    assert any("M079, M080 and M081 are untouched" in lim for lim in rep.limitations)
