"""MILESTONE-082 focused unit tests. Every test names the claim it defends.

CORRECTED AFTER OWNER REVIEW. Finding 1 retracted the ledger-first artifact:
the snapshot is now built from receipts labelled at or before the cutoff, so
ATTESTED_AFTER_CUTOFF, NO_SYSTEM_RECEIPT_EVIDENCE, `attested_after_cutoff_count`
and `unattested_count` no longer exist. Finding 2 retracted the wall-clock upper
bound: the surviving claim is causal, and the tests that asserted the bound are
replaced by tests that assert its ABSENCE.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.operator_event_receipt import (
    ATTESTED_EVIDENCE_BANNER,
    AttestedEvidenceReport,
    MissingAttestedEventError,
    OperatorEventReceipt,
    build_attested_evidence_report,
    events_with_receipt_labelled_by,
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
    "UPPER_BOUND",
    "AS_OF",
    "KNOWN_BY",
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
        receipt_label_cutoff=BASE + timedelta(days=cutoff_day),
    )


def rendered(rep: AttestedEvidenceReport) -> tuple[str, str]:
    return (
        render_attested_evidence_report_text(rep),
        json.dumps(render_attested_evidence_report_json(rep), sort_keys=True),
    )


# --------------------------------------------------------------------------
# FINDING 1 - the snapshot is receipt-cutoff, and nothing later can reach it
# --------------------------------------------------------------------------


def test_an_event_whose_receipt_label_precedes_the_cutoff_appears() -> None:
    entry = report([event(1)], [receipt(1, received_day=5)], cutoff_day=10).entries[0]
    assert entry.event_governance_id == "EVT-1"
    assert entry.system_received_at == BASE + timedelta(days=5)


def test_a_receipt_labelled_after_the_cutoff_is_wholly_unreachable() -> None:
    """OWNER FINDING 1, ATTACK A. Full output must be identical either way."""
    with_late = report(
        [event(1), event(2)],
        [receipt(1, received_day=5), receipt(2, received_day=20)],
        cutoff_day=10,
    )
    without = report([event(1), event(2)], [receipt(1, received_day=5)], cutoff_day=10)
    assert with_late == without
    assert rendered(with_late) == rendered(without)
    assert with_late.attested_count == 1


def test_an_event_added_after_the_cutoff_is_wholly_unreachable() -> None:
    """OWNER FINDING 1, ATTACK B. A future event may not leak its identity."""
    future = event(9, position="POS-FUTURE", symbol="ZZZZ")
    with_future = report([event(1), future], [receipt(1, received_day=5)], cutoff_day=10)
    without = report([event(1)], [receipt(1, received_day=5)], cutoff_day=10)
    assert with_future == without
    text, payload = rendered(with_future)
    assert rendered(with_future) == rendered(without)
    for leak in ("EVT-9", "POS-FUTURE", "ZZZZ"):
        assert leak not in text, leak
        assert leak not in payload, leak


def test_the_report_carries_no_future_tail_count() -> None:
    """OWNER: the snapshot may not know how much evidence it excluded."""
    rep = report(
        [event(1), event(2)],
        [receipt(1, received_day=5), receipt(2, received_day=20)],
        cutoff_day=10,
    )
    fields = set(type(rep).__dataclass_fields__)
    assert fields == {"receipt_label_cutoff", "attested_count", "entries", "limitations"}
    for banned in ("attested_after_cutoff_count", "unattested_count", "excluded_count"):
        assert banned not in fields
        assert banned not in render_attested_evidence_report_json(rep)
    assert rep.attested_count == len(rep.entries)


def test_an_unreceipted_event_is_absent_rather_than_listed() -> None:
    """Absence is the representation; there is no placeholder to backfill."""
    liar = event(1, day=1, recorded_day=-3650)
    rep = report([liar], [], cutoff_day=10)
    assert rep.entries == ()
    assert rep.attested_count == 0
    assert "EVT-1" not in render_attested_evidence_report_text(rep)


def test_the_snapshot_says_it_cannot_report_what_it_excluded() -> None:
    text = render_attested_evidence_report_text(report([event(1)], [], cutoff_day=10))
    assert "cannot say how many events it excluded" in text
    assert "re-evaluating this same cutoff later can return MORE" in text
    assert "RECEIPT-LABEL-CUTOFF VIEW" in text
    # PROBE NOTE. A bare "snapshot" search is wrong here for the same reason the
    # "upper bound" search was wrong last pass: the artifact must be allowed to
    # DENY being a snapshot. Every surviving mention must sit in a denial.
    for line in text.splitlines():
        if "snapshot" in line.lower():
            assert "NOT a historical snapshot" in line or "NOT a stable point-in-time" in line, line


@pytest.mark.parametrize(("cutoff_day", "expected"), [(4, False), (5, True), (6, True)])
def test_the_cutoff_is_inclusive(cutoff_day: int, expected: bool) -> None:
    labelled = events_with_receipt_labelled_by(
        (event(1),), (receipt(1, received_day=5),), BASE + timedelta(days=cutoff_day)
    )
    assert (len(labelled) == 1) is expected
    assert (
        len(report([event(1)], [receipt(1, received_day=5)], cutoff_day=cutoff_day).entries) == 1
    ) is expected


def test_a_receipt_for_an_unsupplied_event_is_refused_not_skipped() -> None:
    with pytest.raises(MissingAttestedEventError, match="was not supplied"):
        report([], [receipt(1, received_day=5)], cutoff_day=10)


# --------------------------------------------------------------------------
# FINDING 2 - the wall-clock bound is retracted; the causal claim survives
# --------------------------------------------------------------------------


def test_a_backward_clock_label_is_honoured_by_the_filter_without_any_bound_claim() -> None:
    """OWNER FINDING 2, domain half of the backward-clock attack.

    A receipt whose LABEL precedes the event's real commit chronology is still
    selected by a cutoff between the two. The code does not pretend otherwise;
    the artifact must therefore claim no wall-clock bound. The PostgreSQL half
    of this attack is
    `test_a_backward_clock_breaks_the_wall_clock_implication`.
    """
    backward = receipt(1, received_day=-30)  # labelled a month before the event
    rep = report([event(1, day=1)], [backward], cutoff_day=-15)
    assert rep.attested_count == 1
    assert rep.entries[0].system_received_at < BASE + timedelta(days=1)


def test_no_artifact_surface_claims_an_upper_bound_or_a_knowledge_time() -> None:
    rep = report([event(1)], [receipt(1, received_day=5)], cutoff_day=10)
    text, payload = rendered(rep)
    for withdrawn in (
        "upper bound witness",
        "UPPER BOUND WITNESS",
        "can never OVERSTATE",
        "one-directional guarantee",
        "durably committed by the cutoff",
    ):
        assert withdrawn not in text, withdrawn
        assert withdrawn not in payload, withdrawn


def test_the_banner_states_the_causal_claim_and_the_retraction() -> None:
    for required in (
        "What a receipt PROVES is CAUSAL and clock-independent",
        "read the event back from COMMITTED persistence",
        "moved BACKWARD",
        "DOES NOT prove the event was durably committed by that cutoff",
        "RETRACTED",
        "does NOT replace M079's recorded_at firewall",
        "RECEIPT-LABEL-CUTOFF VIEW",
        "PREDICATE OVER LABELS IN THE CURRENT PERSISTED RECEIPT SET",
        "REPEATED EVALUATION AT THE SAME CUTOFF CAN CHANGE",
        "structurally absent",
        "committed by a PRIOR transaction",
        "does NOT authenticate the label",
        "CANNOT tell you how much evidence it excluded",
        "NEVER filled in from recorded_at",
        "NO ordering authority is emitted",
    ):
        assert required in ATTESTED_EVIDENCE_BANNER, required


def test_the_limitations_retract_the_bound_and_deny_the_m079_replacement() -> None:
    rep = report([], [], cutoff_day=10)
    joined = " ".join(rep.limitations)
    assert len(rep.limitations) == 17
    assert "RETRACTED CLAIM" in joined
    assert "CAUSAL only" in joined
    assert "does NOT replace M079's recorded_at" in joined
    assert "track_commit_timestamp" in joined
    assert "no monotonicity is enforced" in joined
    assert "CANNOT report how much evidence it excluded" in joined
    assert "NOT a stable point-in-time snapshot" in joined
    assert "REPEATED EVALUATION AT THE SAME CUTOFF CAN CHANGE" in joined
    assert "committed by a PRIOR transaction" in joined
    assert "UNAUTHENTICATED LABELS" in joined
    assert "ROW-LEVEL UPDATE/DELETE ONLY" in joined


def test_events_with_receipt_labelled_by_never_reads_recorded_at() -> None:
    """CLAIM: a deliberately false recorded_at cannot influence M082."""
    honest = event(1, day=1, recorded_day=1)
    liar = event(2, day=1, recorded_day=-3650)  # claims it was recorded a decade early
    receipts = (receipt(1, received_day=5), receipt(2, received_day=5))
    labelled = events_with_receipt_labelled_by((honest, liar), receipts, BASE + timedelta(days=10))
    assert {e.governance_id for e in labelled} == {"EVT-1", "EVT-2"}
    # And with both receipts after the cutoff, the liar gains nothing from its lie.
    late = (receipt(1, received_day=20), receipt(2, received_day=20))
    assert events_with_receipt_labelled_by((honest, liar), late, BASE + timedelta(days=10)) == ()


def test_the_old_overclaiming_names_are_gone() -> None:
    """The renames are part of the correction, not cosmetic."""
    import empirical_platform.decision_candidate.operator_event_receipt as module

    for withdrawn in ("attested_known_by", "AttestedEvidenceStatus"):
        assert not hasattr(module, withdrawn), withdrawn
        assert withdrawn not in module.__all__
    assert "attested_as_of" not in AttestedEvidenceReport.__dataclass_fields__
    assert "attested_as_of" not in GetAttestedEvidenceReportQuery.__dataclass_fields__


# --------------------------------------------------------------------------
# Vocabulary and the honesty surface
# --------------------------------------------------------------------------


@pytest.mark.parametrize("token", FORBIDDEN_TOKENS)
def test_no_forbidden_token_appears_in_any_closed_vocabulary(token: str) -> None:
    """CLAIM: no field or JSON key claims commit time, true time, a sequence,
    an upper bound, or a knowledge-time stance."""
    rep = report([event(1)], [receipt(1, received_day=5)], cutoff_day=10)
    payload = render_attested_evidence_report_json(rep)
    surfaces = [
        *(f for f in type(rep).__dataclass_fields__),
        *(f for f in type(rep.entries[0]).__dataclass_fields__),
        *payload,
        *payload["entries"][0],
    ]
    for surface in surfaces:
        assert token not in surface.upper().replace(" ", "_"), surface


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


def test_entries_are_ordered_deterministically_by_label_then_identity() -> None:
    rep = report(
        [event(1), event(2, position="POS-2"), event(3, position="POS-3")],
        [receipt(2, received_day=3), receipt(1, received_day=7), receipt(3, received_day=3)],
        cutoff_day=10,
    )
    assert [e.event_governance_id for e in rep.entries] == ["EVT-2", "EVT-3", "EVT-1"]


def test_entry_order_does_not_depend_on_input_order() -> None:
    events = [event(1), event(2, position="POS-2"), event(3, position="POS-3")]
    receipts = [receipt(1, received_day=7), receipt(2, received_day=3), receipt(3, received_day=5)]
    forward = report(events, receipts, cutoff_day=10)
    backward = report(list(reversed(events)), list(reversed(receipts)), cutoff_day=10)
    assert forward == backward


def test_a_naive_cutoff_is_refused_everywhere() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_attested_evidence_report(
            events=(), receipts=(), receipt_label_cutoff=datetime(2026, 1, 1)
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        events_with_receipt_labelled_by((), (), datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="timezone-aware"):
        GetAttestedEvidenceReportQuery(receipt_label_cutoff=datetime(2026, 1, 1))


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
        [event(1), event(2, position="POS-2")],
        [receipt(1, received_day=5), receipt(2, received_day=6)],
        cutoff_day=10,
    )
    text = render_attested_evidence_report_text(rep)
    payload = render_attested_evidence_report_json(rep)
    assert payload["attested_count"] == rep.attested_count
    assert payload["receipt_label_cutoff"] == rep.receipt_label_cutoff.isoformat()
    for entry in payload["entries"]:
        assert entry["event_governance_id"] in text
        assert entry["system_received_at"] in text
    assert json.dumps(payload, sort_keys=True) == json.dumps(
        render_attested_evidence_report_json(rep), sort_keys=True
    )


def test_an_empty_snapshot_still_carries_every_limitation() -> None:
    rep = report([], [], cutoff_day=10)
    assert rep.entries == ()
    assert rep.attested_count == 0
    assert len(rep.limitations) == 17
    assert any("CAUSAL only" in lim for lim in rep.limitations)
    assert any("RETRACTED CLAIM" in lim for lim in rep.limitations)
    assert any("track_commit_timestamp" in lim for lim in rep.limitations)
    assert any("does NOT replace M079" in lim for lim in rep.limitations)
