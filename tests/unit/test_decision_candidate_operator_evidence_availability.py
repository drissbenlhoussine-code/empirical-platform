"""MILESTONE-079 unit tests.

Written from the epistemic claims in
`MILESTONE_079_OPERATOR_EVIDENCE_AVAILABILITY_SNAPSHOT_SCOPE_AND_DESIGN.md`,
not from the implementation's shape.

The timeline every temporal test is built on:

    T1  effective, early
    T2  effective, later
    T3  recorded, latest   -- the backfill that must stay invisible at K < T3
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.operator_evidence_availability import (
    EVIDENCE_AVAILABILITY_BANNER,
    EvidenceSnapshotOutcome,
    EvidenceUnassessableReason,
    KnownPositionStatus,
    OperatorEvidenceSnapshot,
    build_operator_evidence_snapshot,
    events_known_by,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
    derive_position_state,
)

T1 = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
T3 = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)


def event(
    *,
    gid: str,
    pos: str = "POS-1",
    symbol: str = "AAPL",
    kind: OperatorPositionEventKind = OperatorPositionEventKind.OPENED,
    quantity: int = 10,
    price: str = "100",
    effective: datetime,
    recorded: datetime,
) -> OperatorAssertedPositionEvent:
    return OperatorAssertedPositionEvent(
        governance_id=gid,
        runtime_id=f"rt-{gid}",
        position_governance_id=pos,
        instrument_symbol=symbol,
        kind=kind,
        quantity=quantity,
        asserted_price=Decimal(price),
        event_timestamp=effective,
        recorded_at=recorded,
    )


def snapshot(
    *,
    events: tuple[OperatorAssertedPositionEvent, ...] = (),
    effective: datetime = LATER,
    knowledge: datetime = LATER,
    ledger_available: bool = True,
) -> OperatorEvidenceSnapshot:
    return build_operator_evidence_snapshot(
        events=events,
        effective_as_of=effective,
        knowledge_as_of=knowledge,
        ledger_available=ledger_available,
    )


# --------------------------------------------------------------------------
# The firewall itself
# --------------------------------------------------------------------------


def test_effective_before_cutoff_and_recorded_before_cutoff_is_visible() -> None:
    result = snapshot(events=(event(gid="E1", effective=T1, recorded=T1),))
    assert result.outcome is EvidenceSnapshotOutcome.EVIDENCE_SNAPSHOT_AVAILABLE
    assert result.entries[0].status is KnownPositionStatus.KNOWN_OPEN
    assert result.visible_event_count == 1


def test_effective_before_cutoff_but_recorded_after_cutoff_is_invisible() -> None:
    """The firewall. This is the whole milestone in one assertion."""
    result = snapshot(
        events=(event(gid="E1", effective=T1, recorded=T3),),
        effective=LATER,
        knowledge=T2,
    )
    assert result.outcome is EvidenceSnapshotOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF
    assert result.entries == ()
    assert result.excluded_by_knowledge_cutoff == 1
    assert result.excluded_by_effective_cutoff == 0


def test_effective_after_cutoff_but_recorded_before_cutoff_is_invisible() -> None:
    result = snapshot(
        events=(event(gid="E1", effective=LATER, recorded=T1),),
        effective=T2,
        knowledge=T3,
    )
    assert result.entries == ()
    assert result.excluded_by_effective_cutoff == 1
    assert result.excluded_by_knowledge_cutoff == 0


def test_the_two_exclusion_counts_are_reported_separately() -> None:
    """Design review C05: an operator must be able to tell 'had not happened
    yet' from 'had not been recorded yet'."""
    result = snapshot(
        events=(
            event(gid="E1", pos="P1", effective=LATER, recorded=T1),
            event(gid="E2", pos="P2", effective=T1, recorded=T3),
        ),
        effective=T2,
        knowledge=T2,
    )
    assert result.excluded_by_effective_cutoff == 1
    assert result.excluded_by_knowledge_cutoff == 1


def test_the_same_effective_cutoff_gives_different_answers_at_two_knowledge_cutoffs() -> None:
    """The look-ahead case M078 documented, proven prevented."""
    events = (event(gid="E1", effective=T1, recorded=T3),)
    before = snapshot(events=events, effective=LATER, knowledge=T2)
    after = snapshot(events=events, effective=LATER, knowledge=LATER)
    assert before.known_open_count == 0
    assert after.known_open_count == 1
    assert before.effective_as_of == after.effective_as_of


# --------------------------------------------------------------------------
# Boundaries
# --------------------------------------------------------------------------


def test_exact_knowledge_boundary_is_inclusive() -> None:
    result = snapshot(events=(event(gid="E1", effective=T1, recorded=T2),), knowledge=T2)
    assert result.visible_event_count == 1


def test_one_microsecond_after_the_knowledge_boundary_is_excluded() -> None:
    result = snapshot(
        events=(event(gid="E1", effective=T1, recorded=T2 + timedelta(microseconds=1)),),
        knowledge=T2,
    )
    assert result.visible_event_count == 0
    assert result.excluded_by_knowledge_cutoff == 1


def test_exact_effective_boundary_is_inclusive() -> None:
    result = snapshot(events=(event(gid="E1", effective=T2, recorded=T1),), effective=T2)
    assert result.visible_event_count == 1


def test_one_microsecond_after_the_effective_boundary_is_excluded() -> None:
    result = snapshot(
        events=(event(gid="E1", effective=T2 + timedelta(microseconds=1), recorded=T1),),
        effective=T2,
    )
    assert result.excluded_by_effective_cutoff == 1


def test_same_instant_with_different_offsets_agrees_on_both_dimensions() -> None:
    offset_effective = T1.astimezone(timezone(timedelta(hours=-5)))
    offset_recorded = T2.astimezone(timezone(timedelta(hours=9)))
    assert offset_effective == T1 and offset_recorded == T2
    a = snapshot(events=(event(gid="E1", effective=T1, recorded=T2),), knowledge=T2)
    b = snapshot(
        events=(event(gid="E1", effective=offset_effective, recorded=offset_recorded),),
        knowledge=T2,
    )
    assert a.visible_event_count == b.visible_event_count == 1
    assert a.entries[0].status is b.entries[0].status


# --------------------------------------------------------------------------
# The central adversarial case: incomplete knowledge prefix
# --------------------------------------------------------------------------


def _backfilled_open_with_earlier_close() -> tuple[OperatorAssertedPositionEvent, ...]:
    """OPENED effective T1 recorded T3; CLOSED effective T2 recorded T2.

    At K = T2 the close is visible and its opening is not.
    """
    return (
        event(gid="E1", effective=T1, recorded=T3, quantity=10),
        event(
            gid="E2",
            kind=OperatorPositionEventKind.CLOSED,
            quantity=10,
            price="110",
            effective=T2,
            recorded=T2,
        ),
    )


def test_close_visible_without_its_opening_is_incomplete_knowledge_not_corruption() -> None:
    result = snapshot(events=_backfilled_open_with_earlier_close(), effective=LATER, knowledge=T2)
    entry = result.entries[0]
    assert entry.status is KnownPositionStatus.INCOMPLETE_KNOWLEDGE_SEQUENCE
    assert entry.position is None, "no state may be invented"
    assert result.incomplete_knowledge_count == 1
    assert result.incoherent_position_count == 0


def test_reduction_visible_without_its_opening_is_incomplete_knowledge() -> None:
    events = (
        event(gid="E1", effective=T1, recorded=T3, quantity=10),
        event(
            gid="E2",
            kind=OperatorPositionEventKind.REDUCED,
            quantity=4,
            effective=T2,
            recorded=T2,
        ),
    )
    result = snapshot(events=events, effective=LATER, knowledge=T2)
    assert result.entries[0].status is KnownPositionStatus.INCOMPLETE_KNOWLEDGE_SEQUENCE


def test_the_same_key_folds_normally_once_knowledge_advances() -> None:
    events = _backfilled_open_with_earlier_close()
    later = snapshot(events=events, effective=LATER, knowledge=LATER)
    assert later.entries[0].status is KnownPositionStatus.KNOWN_CLOSED
    assert later.incomplete_knowledge_count == 0


def test_one_incomplete_key_does_not_withhold_the_whole_snapshot() -> None:
    """Design review B06."""
    events = (
        *_backfilled_open_with_earlier_close(),
        event(gid="E3", pos="P2", symbol="TSLA", effective=T1, recorded=T1),
    )
    result = snapshot(events=events, effective=LATER, knowledge=T2)
    assert result.outcome is EvidenceSnapshotOutcome.EVIDENCE_SNAPSHOT_AVAILABLE
    assert result.known_open_count == 1
    assert result.incomplete_knowledge_count == 1


def test_incompleteness_does_not_mask_genuinely_incoherent_data() -> None:
    """Design review T07. A key that fails to fold even UNFILTERED is corrupt,
    not merely truncated, and must not hide behind an innocent status."""
    events = (
        event(gid="E1", effective=T1, recorded=T1, quantity=10),
        event(gid="E2", effective=T2, recorded=T2, quantity=5),  # second OPENED
    )
    result = snapshot(events=events, effective=LATER, knowledge=LATER)
    entry = result.entries[0]
    assert entry.status is KnownPositionStatus.LEDGER_INCOHERENT_FOR_POSITION
    assert entry.position is None
    assert result.incoherent_position_count == 1
    assert result.incomplete_knowledge_count == 0
    assert any("genuinely incoherent" in line for line in result.limitations)


def test_the_discriminator_leaks_no_state_from_the_unfiltered_fold() -> None:
    result = snapshot(events=_backfilled_open_with_earlier_close(), effective=LATER, knowledge=T2)
    assert result.entries[0].position is None
    assert result.known_open_count == 0
    assert result.known_closed_count == 0


# --------------------------------------------------------------------------
# Absence, malformed input, determinism
# --------------------------------------------------------------------------


def test_nothing_recorded_by_the_cutoff_is_not_nothing_happened() -> None:
    result = snapshot(events=(event(gid="E1", effective=T1, recorded=T3),), knowledge=T1)
    assert result.outcome is EvidenceSnapshotOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF
    assert any("not an absence of activity" in line for line in result.limitations)


def test_unavailable_ledger_is_withheld() -> None:
    result = snapshot(ledger_available=False)
    assert result.outcome is EvidenceSnapshotOutcome.NOT_ASSESSABLE
    assert result.unassessable_reason is EvidenceUnassessableReason.LEDGER_UNAVAILABLE


def test_empty_ledger_is_reported_not_withheld() -> None:
    assert snapshot(events=()).outcome is (
        EvidenceSnapshotOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF
    )


@pytest.mark.parametrize("naive_field", ["effective", "knowledge"])
def test_naive_cutoffs_are_rejected_as_request_errors(naive_field: str) -> None:
    naive = datetime(2026, 8, 10, 10, 0)  # noqa: DTZ001 - deliberately naive
    kwargs = {"effective": LATER, "knowledge": LATER}
    kwargs[naive_field] = naive
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshot(**kwargs)  # type: ignore[arg-type]


def test_knowledge_before_effective_is_permitted_and_named() -> None:
    result = snapshot(
        events=(event(gid="E1", effective=T1, recorded=T1),), effective=LATER, knowledge=T2
    )
    assert any("precedes the effective cutoff" in line for line in result.limitations)
    assert result.known_open_count == 1


def test_entry_order_is_deterministic_regardless_of_input_order() -> None:
    a = event(gid="E1", pos="PZ", symbol="ZZZ", effective=T1, recorded=T1)
    b = event(gid="E2", pos="PA", symbol="AAA", effective=T1, recorded=T1)
    forward = snapshot(events=(a, b))
    reverse = snapshot(events=(b, a))
    assert [e.instrument_symbol for e in forward.entries] == ["AAA", "ZZZ"]
    assert forward == reverse


def test_repeated_invocation_is_identical() -> None:
    events = (event(gid="E1", effective=T1, recorded=T1),)
    assert snapshot(events=events) == snapshot(events=events)


def test_counts_agree_with_entries() -> None:
    result = snapshot(
        events=(
            event(gid="E1", pos="P1", symbol="AAA", effective=T1, recorded=T1),
            *_backfilled_open_with_earlier_close(),
        ),
        effective=LATER,
        knowledge=T2,
    )
    assert (
        result.known_open_count
        + result.known_closed_count
        + result.incomplete_knowledge_count
        + result.incoherent_position_count
        == len(result.entries)
    )


def test_events_known_by_is_inclusive_and_pure() -> None:
    events = (
        event(gid="E1", effective=T1, recorded=T1),
        event(gid="E2", pos="P2", effective=T1, recorded=T3),
    )
    assert len(events_known_by(events, T2)) == 1
    assert len(events_known_by(events, T3)) == 2
    assert len(events) == 2, "the input tuple must not be mutated"


# --------------------------------------------------------------------------
# Frozen-contract preservation and honesty
# --------------------------------------------------------------------------


def test_m076_is_not_mutated_and_still_answers_effective_time() -> None:
    """M079 must not change what M076 says about the same ledger."""
    events = (event(gid="E1", effective=T1, recorded=T3),)
    m076 = derive_position_state(events=events, as_of=LATER)
    assert len(m076.open_positions) == 1, "M076 is effective-time and sees the backfill"
    m079 = snapshot(events=events, effective=LATER, knowledge=T2)
    assert m079.known_open_count == 0, "M079 is knowledge-time and does not"
    # And M076 is unchanged by having been called through M079.
    assert len(derive_position_state(events=events, as_of=LATER).open_positions) == 1


def test_m079_matches_m076_when_knowledge_is_the_present() -> None:
    events = (
        event(gid="E1", pos="P1", effective=T1, recorded=T3),
        event(gid="E2", pos="P2", symbol="TSLA", effective=T2, recorded=T2),
    )
    m076 = derive_position_state(events=events, as_of=LATER)
    m079 = snapshot(events=events, effective=LATER, knowledge=LATER)
    assert m079.known_open_count == len(m076.open_positions)


@pytest.mark.parametrize(
    "forbidden", ["VERIFIED", "EXECUTED", "FILLED", "REALIZED", "CONFIRMED", "PROFIT"]
)
def test_forbidden_vocabulary_absent_from_every_closed_enum(forbidden: str) -> None:
    for enum in (KnownPositionStatus, EvidenceSnapshotOutcome, EvidenceUnassessableReason):
        assert all(forbidden not in member.value for member in enum)


def test_known_means_known_to_the_ledger_not_known_to_be_true() -> None:
    result = snapshot(events=(event(gid="E1", effective=T1, recorded=T1),))
    assert any("not known to be true" in line for line in result.limitations)
    assert "NOT known to be true" in EVIDENCE_AVAILABILITY_BANNER


def test_banner_denies_every_claim_m079_does_not_make() -> None:
    for denial in (
        "NOT broker-verified",
        "NOT execution",
        "NOT actual holdings",
        "NOT a market valuation",
        "NOT realized or unrealized P&L",
        "NOT a profitability claim",
        "NOT a causal claim",
        "NOT advice",
        "look-ahead leak",
    ):
        assert denial in EVIDENCE_AVAILABILITY_BANNER


def test_no_field_implies_a_derived_return_or_pnl() -> None:
    result = snapshot(events=(event(gid="E1", effective=T1, recorded=T1),))
    forbidden = ("pnl", "profit", "return", "gain", "loss", "proceeds")
    for holder in (result, *result.entries):
        for f in dataclasses.fields(holder):
            assert not any(word in f.name.lower() for word in forbidden), f.name


# --------------------------------------------------------------------------
# Regressions for defects found by the hostile implementation review
# --------------------------------------------------------------------------


def test_a_position_is_never_silently_dropped_from_the_snapshot() -> None:
    """Implementation review R01. `_fold_one_key` returned `None` on an
    impossible path and the caller `continue`d, which would have dropped a
    position with no entry, no count and no limitation. Every visible key must
    now appear exactly once."""
    events = (
        event(gid="E1", pos="P1", symbol="AAA", effective=T1, recorded=T1),
        event(gid="E2", pos="P2", symbol="BBB", effective=T1, recorded=T1),
        event(gid="E3", pos="P3", symbol="CCC", effective=T1, recorded=T1),
    )
    result = snapshot(events=events)
    assert len(result.entries) == 3
    assert {e.position_governance_id for e in result.entries} == {"P1", "P2", "P3"}
    assert result.known_open_count == 3


def test_corruption_invisible_at_an_earlier_knowledge_cutoff_is_reported_at_a_later_one() -> None:
    """Implementation attack 3. A second OPENED recorded late is not corruption
    from the earlier snapshot's point of view -- and is, from the later one's."""
    events = (
        event(gid="E1", effective=T1, recorded=T1, quantity=10),
        event(gid="E2", effective=T2, recorded=T3, quantity=5),
    )
    early = snapshot(events=events, effective=LATER, knowledge=T2)
    late = snapshot(events=events, effective=LATER, knowledge=LATER)
    assert early.entries[0].status is KnownPositionStatus.KNOWN_OPEN
    assert late.entries[0].status is KnownPositionStatus.LEDGER_INCOHERENT_FOR_POSITION


def test_incomplete_and_incoherent_keys_are_reported_side_by_side() -> None:
    events = (
        event(gid="A1", pos="PA", effective=T1, recorded=T3, quantity=10),
        event(
            gid="A2",
            pos="PA",
            kind=OperatorPositionEventKind.CLOSED,
            quantity=10,
            price="110",
            effective=T2,
            recorded=T2,
        ),
        event(gid="B1", pos="PB", symbol="TSLA", effective=T1, recorded=T1, quantity=10),
        event(gid="B2", pos="PB", symbol="TSLA", effective=T2, recorded=T1, quantity=5),
    )
    result = snapshot(events=events, effective=LATER, knowledge=T2)
    by_key = {e.position_governance_id: e for e in result.entries}
    assert by_key["PA"].status is KnownPositionStatus.INCOMPLETE_KNOWLEDGE_SEQUENCE
    assert by_key["PB"].status is KnownPositionStatus.LEDGER_INCOHERENT_FOR_POSITION
    assert by_key["PA"].rejection_reason == "POSITION_NOT_OPEN"
    assert by_key["PB"].rejection_reason == "POSITION_ALREADY_OPEN"


def test_evidence_recorded_but_nothing_effective_yet_is_not_no_evidence() -> None:
    """Implementation attack 1. 'Recorded, but hadn't happened by E' and
    'nothing was recorded' are different facts."""
    result = snapshot(
        events=(event(gid="E1", effective=LATER, recorded=T1),), effective=T1, knowledge=T2
    )
    assert result.outcome is EvidenceSnapshotOutcome.EVIDENCE_SNAPSHOT_AVAILABLE
    assert result.entries == ()
    assert result.excluded_by_effective_cutoff == 1
    assert result.excluded_by_knowledge_cutoff == 0
