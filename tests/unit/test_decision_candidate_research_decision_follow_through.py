"""MILESTONE-078 unit tests.

Written from the claims in
`MILESTONE_078_RESEARCH_DECISION_FOLLOW_THROUGH_SCOPE_AND_DESIGN.md`, not from
the implementation's shape.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
    derive_position_state,
)
from empirical_platform.decision_candidate.research_decision_follow_through import (
    FOLLOW_THROUGH_BANNER,
    ApprovedPlanReference,
    FollowThroughOutcome,
    FollowThroughStatus,
    FollowThroughUnassessableReason,
    ResearchDecisionFollowThrough,
    UnlinkedPositionReason,
    audit_research_decision_follow_through,
    cited_plan_by_position,
)

SESSION_AS_OF = datetime(2026, 4, 10, 16, 0, tzinfo=UTC)
AS_OF = SESSION_AS_OF + timedelta(days=7)


def plan(
    *, pid: str = "PLAN-1", symbol: str = "AAPL", rank: int | None = 1
) -> ApprovedPlanReference:
    return ApprovedPlanReference(
        rank=rank, instrument_symbol=symbol, position_plan_governance_id=pid
    )


def event(
    *,
    gid: str,
    pos: str,
    symbol: str = "AAPL",
    kind: OperatorPositionEventKind = OperatorPositionEventKind.OPENED,
    quantity: int = 10,
    price: str = "100",
    at: datetime | None = None,
    cites: str | None = None,
) -> OperatorAssertedPositionEvent:
    moment = at or (SESSION_AS_OF + timedelta(days=1))
    return OperatorAssertedPositionEvent(
        governance_id=gid,
        runtime_id=f"rt-{gid}",
        position_governance_id=pos,
        instrument_symbol=symbol,
        kind=kind,
        quantity=quantity,
        asserted_price=Decimal(price),
        event_timestamp=moment,
        recorded_at=moment,
        source_position_plan_governance_id=cites,
    )


def audit(
    *,
    plans: tuple[ApprovedPlanReference, ...] = (),
    events: tuple[OperatorAssertedPositionEvent, ...] = (),
    as_of: datetime = AS_OF,
    session_as_of: datetime = SESSION_AS_OF,
    ledger_available: bool = True,
    incoherent: bool = False,
) -> ResearchDecisionFollowThrough:
    state = None if incoherent else derive_position_state(events=events, as_of=as_of)
    return audit_research_decision_follow_through(
        session_governance_id="RESEARCH-7801",
        session_as_of=session_as_of,
        approved_plans=plans,
        events=events,
        held_state=state,
        as_of=as_of,
        ledger_available=ledger_available,
    )


# --------------------------------------------------------------------------
# Nominal statuses
# --------------------------------------------------------------------------


def test_open_asserted_position_is_reported_against_its_plan() -> None:
    result = audit(plans=(plan(),), events=(event(gid="E1", pos="P1", cites="PLAN-1"),))
    assert result.outcome is FollowThroughOutcome.AUDITED
    assert result.entries[0].status is FollowThroughStatus.ASSERTED_POSITION_OPEN
    assert result.with_open_asserted_position == 1
    assert result.entries[0].position_governance_ids == ("P1",)


def test_closed_asserted_position_is_reported_against_its_plan() -> None:
    opened = event(gid="E1", pos="P1", cites="PLAN-1")
    closed = event(
        gid="E2",
        pos="P1",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=10,
        price="110",
        at=SESSION_AS_OF + timedelta(days=2),
    )
    result = audit(plans=(plan(),), events=(opened, closed))
    assert result.entries[0].status is FollowThroughStatus.ASSERTED_POSITION_CLOSED
    assert result.with_closed_asserted_position == 1


def test_plan_with_nothing_recorded_is_reported_as_such() -> None:
    result = audit(plans=(plan(),), events=())
    assert result.entries[0].status is FollowThroughStatus.NO_ASSERTED_POSITION_RECORDED
    assert result.with_no_asserted_position_recorded == 1


def test_a_plan_cited_by_both_an_open_and_a_closed_position_keeps_both_counts() -> None:
    """Design attack D05: status precedence must not lose the closed one."""
    closed_open = event(gid="E1", pos="P1", cites="PLAN-1", at=SESSION_AS_OF + timedelta(days=1))
    closed_close = event(
        gid="E2",
        pos="P1",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=10,
        price="110",
        at=SESSION_AS_OF + timedelta(days=2),
    )
    still_open = event(gid="E3", pos="P2", cites="PLAN-1", at=SESSION_AS_OF + timedelta(days=3))
    result = audit(plans=(plan(),), events=(closed_open, closed_close, still_open))
    entry = result.entries[0]
    assert entry.status is FollowThroughStatus.ASSERTED_POSITION_OPEN
    assert entry.open_position_count == 1
    assert entry.closed_position_count == 1
    assert entry.position_governance_ids == ("P1", "P2")


# --------------------------------------------------------------------------
# Unlinked positions
# --------------------------------------------------------------------------


def test_position_citing_no_plan_is_reported_as_cites_no_plan() -> None:
    result = audit(plans=(plan(),), events=(event(gid="E1", pos="P9", symbol="TSLA"),))
    assert len(result.unlinked_open_positions) == 1
    unlinked = result.unlinked_open_positions[0]
    assert unlinked.reason is UnlinkedPositionReason.CITES_NO_PLAN
    assert unlinked.cited_plan_governance_id is None
    assert unlinked.open_quantity == 10


def test_position_citing_another_sessions_plan_is_a_distinct_fact() -> None:
    """Design attack K07: these are different facts and must not be merged."""
    result = audit(
        plans=(plan(),),
        events=(event(gid="E1", pos="P9", symbol="TSLA", cites="PLAN-OTHER"),),
    )
    unlinked = result.unlinked_open_positions[0]
    assert unlinked.reason is UnlinkedPositionReason.CITES_PLAN_OUTSIDE_THIS_SESSION
    assert unlinked.cited_plan_governance_id == "PLAN-OTHER"


def test_a_matched_open_position_is_not_reported_as_unlinked() -> None:
    result = audit(plans=(plan(),), events=(event(gid="E1", pos="P1", cites="PLAN-1"),))
    assert result.unlinked_open_positions == ()


def test_a_closed_position_is_never_reported_as_unlinked() -> None:
    opened = event(gid="E1", pos="P9", symbol="TSLA")
    closed = event(
        gid="E2",
        pos="P9",
        symbol="TSLA",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=10,
        price="110",
        at=SESSION_AS_OF + timedelta(days=2),
    )
    assert audit(plans=(plan(),), events=(opened, closed)).unlinked_open_positions == ()


# --------------------------------------------------------------------------
# Temporal
# --------------------------------------------------------------------------


def test_events_after_as_of_are_excluded_and_counted() -> None:
    late = event(gid="E1", pos="P1", cites="PLAN-1", at=AS_OF + timedelta(days=1))
    result = audit(plans=(plan(),), events=(late,))
    assert result.entries[0].status is FollowThroughStatus.NO_ASSERTED_POSITION_RECORDED
    assert result.excluded_future_event_count == 1


def test_event_exactly_at_as_of_is_included() -> None:
    exact = event(gid="E1", pos="P1", cites="PLAN-1", at=AS_OF)
    result = audit(plans=(plan(),), events=(exact,))
    assert result.entries[0].status is FollowThroughStatus.ASSERTED_POSITION_OPEN
    assert result.excluded_future_event_count == 0


def test_one_microsecond_after_as_of_is_excluded() -> None:
    late = event(gid="E1", pos="P1", cites="PLAN-1", at=AS_OF + timedelta(microseconds=1))
    assert (
        audit(plans=(plan(),), events=(late,)).entries[0].status
        is FollowThroughStatus.NO_ASSERTED_POSITION_RECORDED
    )


def test_same_instant_with_different_offsets_agrees() -> None:
    utc_moment = SESSION_AS_OF + timedelta(days=1)
    offset_moment = utc_moment.astimezone(timezone(timedelta(hours=-5)))
    assert utc_moment == offset_moment
    a = audit(plans=(plan(),), events=(event(gid="E1", pos="P1", cites="PLAN-1", at=utc_moment),))
    b = audit(
        plans=(plan(),),
        events=(event(gid="E1", pos="P1", cites="PLAN-1", at=offset_moment),),
    )
    assert a.entries[0].status is b.entries[0].status


def test_naive_as_of_is_rejected_at_the_boundary() -> None:
    with pytest.raises(Exception):  # noqa: B017 - M076 owns the exact type
        derive_position_state(events=(), as_of=datetime(2026, 4, 10, 16, 0))


def test_as_of_before_the_session_says_so_rather_than_implying_inaction() -> None:
    """Design attack C09."""
    result = audit(plans=(plan(),), as_of=SESSION_AS_OF - timedelta(days=1))
    assert any("precedes this session's own as_of" in line for line in result.limitations)


# --------------------------------------------------------------------------
# Absence, withholding, malformed data
# --------------------------------------------------------------------------


def test_unavailable_ledger_is_withheld_not_reported_as_nothing_recorded() -> None:
    result = audit(plans=(plan(),), ledger_available=False)
    assert result.outcome is FollowThroughOutcome.NOT_ASSESSABLE
    assert result.unassessable_reason is FollowThroughUnassessableReason.LEDGER_UNAVAILABLE
    assert result.entries == ()


def test_incoherent_ledger_is_withheld() -> None:
    result = audit(plans=(plan(),), incoherent=True)
    assert result.unassessable_reason is FollowThroughUnassessableReason.LEDGER_INCOHERENT


def test_empty_ledger_is_audited_not_withheld() -> None:
    result = audit(plans=(plan(),), events=())
    assert result.outcome is FollowThroughOutcome.AUDITED


def test_session_with_no_approved_plans_still_reports_unlinked_positions() -> None:
    result = audit(plans=(), events=(event(gid="E1", pos="P9", symbol="TSLA"),))
    assert result.outcome is FollowThroughOutcome.NO_APPROVED_POSITION_PLANS
    assert len(result.unlinked_open_positions) == 1


def test_blank_ledger_citation_is_not_an_identifier() -> None:
    """Carried forward from the M077 R04 defect. Uses a VALID plan id: a blank
    PLAN id is a separate condition that withholds the whole audit, and
    conflating the two would test neither properly."""
    result = audit(plans=(plan(),), events=(event(gid="E1", pos="P1", cites=""),))
    assert result.unlinked_open_positions[0].reason is UnlinkedPositionReason.CITES_NO_PLAN


def test_whitespace_citation_is_not_an_identifier() -> None:
    assert cited_plan_by_position((event(gid="E1", pos="P1", cites="   "),)) == {}


def test_citation_whitespace_is_stripped_before_matching() -> None:
    result = audit(plans=(plan(),), events=(event(gid="E1", pos="P1", cites="  PLAN-1  "),))
    assert result.entries[0].status is FollowThroughStatus.ASSERTED_POSITION_OPEN


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_entry_order_is_deterministic_regardless_of_input_order() -> None:
    a = plan(pid="PLAN-A", symbol="AAA", rank=1)
    b = plan(pid="PLAN-B", symbol="BBB", rank=2)
    c = plan(pid="PLAN-C", symbol="CCC", rank=None)
    forward = audit(plans=(a, b, c))
    reverse = audit(plans=(c, b, a))
    assert [e.instrument_symbol for e in forward.entries] == ["AAA", "BBB", "CCC"]
    assert forward == reverse


def test_unlinked_position_order_is_deterministic() -> None:
    events = (
        event(gid="E1", pos="P2", symbol="ZZZ"),
        event(gid="E2", pos="P1", symbol="AAA"),
    )
    result = audit(plans=(plan(),), events=events)
    assert [p.instrument_symbol for p in result.unlinked_open_positions] == ["AAA", "ZZZ"]


def test_duplicate_plan_ids_produce_one_entry() -> None:
    result = audit(plans=(plan(), plan()))
    assert len(result.entries) == 1
    assert result.approved_plan_count == 1


def test_repeated_invocation_is_identical() -> None:
    events = (event(gid="E1", pos="P1", cites="PLAN-1"),)
    assert audit(plans=(plan(),), events=events) == audit(plans=(plan(),), events=events)


def test_counts_agree_with_entries() -> None:
    result = audit(
        plans=(plan(pid="PLAN-A", symbol="AAA"), plan(pid="PLAN-B", symbol="BBB", rank=2)),
        events=(event(gid="E1", pos="P1", cites="PLAN-A"),),
    )
    assert result.approved_plan_count == len(result.entries)
    assert (
        result.with_open_asserted_position
        + result.with_closed_asserted_position
        + result.with_no_asserted_position_recorded
        == len(result.entries)
    )


# --------------------------------------------------------------------------
# Honesty
# --------------------------------------------------------------------------


def test_the_audit_contains_no_monetary_value_anywhere() -> None:
    """The structural guarantee of section 7: no price arithmetic is possible
    when no monetary field exists."""
    result = audit(
        plans=(plan(),),
        events=(event(gid="E1", pos="P1", cites="PLAN-1", price="123.456789"),),
    )
    money_words = ("price", "notional", "capital", "value", "proceeds", "pnl", "profit")
    for holder in (result, *result.entries, *result.unlinked_open_positions):
        for f in dataclasses.fields(holder):
            assert not any(word in f.name.lower() for word in money_words), f.name
            assert not isinstance(getattr(holder, f.name), Decimal)


@pytest.mark.parametrize(
    "forbidden",
    ["EXECUTED", "FILLED", "VERIFIED", "REALIZED", "PROFIT", "PNL", "FOLLOWED", "ADHERENCE"],
)
def test_forbidden_vocabulary_absent_from_every_closed_enum(forbidden: str) -> None:
    for enum in (FollowThroughStatus, UnlinkedPositionReason, FollowThroughOutcome):
        assert all(forbidden not in member.value for member in enum)


def test_the_nothing_recorded_caveat_is_always_present() -> None:
    """Design attack K09 and G02: the status must never stand alone."""
    result = audit(plans=(plan(),), events=())
    assert any("not a finding that the operator did not act" in line for line in result.limitations)


def test_banner_denies_every_claim_m078_does_not_make() -> None:
    for denial in (
        "NOT evidence that any trade occurred",
        "is NOT evidence that the operator did nothing",
        "NOT proof that the plan caused the position",
        "NOT broker-verified",
        "NOT execution",
        "NOT a market valuation",
        "NOT realized or unrealized P&L",
        "NOT a profitability claim",
        "NOT advice",
        "no monetary value of any kind",
    ):
        assert denial in FOLLOW_THROUGH_BANNER


def test_status_names_do_not_judge_the_operator() -> None:
    for member in FollowThroughStatus:
        assert "IGNORED" not in member.value
        assert "NOT_ACTED" not in member.value
        assert member.value.startswith(("ASSERTED_", "NO_ASSERTED_"))


# --------------------------------------------------------------------------
# Regressions for defects found by the hostile implementation review
# --------------------------------------------------------------------------


def test_position_on_a_different_instrument_is_flagged_not_silently_counted() -> None:
    """Implementation review R01. A TSLA position citing an AAPL plan was
    reported as follow-through for that plan with no signal at all, asserting a
    position against an instrument the operator never recorded one on."""
    result = audit(
        plans=(plan(pid="PLAN-1", symbol="AAPL"),),
        events=(event(gid="E1", pos="P1", symbol="TSLA", cites="PLAN-1"),),
    )
    entry = result.entries[0]
    assert entry.mismatched_instrument_position_ids == ("P1",)
    assert any("recorded on a different instrument" in line for line in result.limitations)
    # The citation is still reported -- dropping it would be its own dishonesty.
    assert entry.open_position_count == 1


def test_matching_instrument_produces_no_mismatch_flag() -> None:
    result = audit(
        plans=(plan(pid="PLAN-1", symbol="AAPL"),),
        events=(event(gid="E1", pos="P1", symbol="AAPL", cites="PLAN-1"),),
    )
    assert result.entries[0].mismatched_instrument_position_ids == ()
    assert not any("different instrument" in line for line in result.limitations)


def test_one_plan_id_naming_two_instruments_withholds_the_whole_audit() -> None:
    """Implementation review R02, SUPERSEDED by owner review of 2c14d0a.

    R02's fix -- deduplicate deterministically and emit a limitation -- was
    deterministic but not semantically safe. This test previously asserted that
    weaker behaviour (`approved_plan_count == 1` plus a warning). It is
    corrected in place rather than deleted, because the earlier assertion is
    itself part of the record.
    """
    result = audit(
        plans=(
            plan(pid="DUP", symbol="AAA", rank=1),
            plan(pid="DUP", symbol="BBB", rank=2),
        )
    )
    assert result.outcome is FollowThroughOutcome.NOT_ASSESSABLE
    assert (
        result.unassessable_reason
        is FollowThroughUnassessableReason.SESSION_PLAN_REFERENCES_INCOHERENT
    )
    # No arbitrary "first" plan is audited, and nothing is fabricated.
    assert result.approved_plan_count == 0
    assert result.entries == ()
    assert result.unlinked_open_positions == ()
    assert any("names more than one instrument" in line for line in result.limitations)
    assert any("would invent an answer" in line for line in result.limitations)


def test_duplicate_identical_plan_entries_produce_no_spurious_limitation() -> None:
    result = audit(plans=(plan(), plan()))
    assert result.approved_plan_count == 1
    assert not any("more than one instrument" in line for line in result.limitations)


# --------------------------------------------------------------------------
# Owner correction: the plan governance id is the JOIN AUTHORITY and must be
# validated as an identity before any lineage is read
# --------------------------------------------------------------------------


def test_attack_a_blank_plan_id_withholds_the_audit() -> None:
    result = audit(plans=(plan(pid=""),))
    assert result.outcome is FollowThroughOutcome.NOT_ASSESSABLE
    assert (
        result.unassessable_reason
        is FollowThroughUnassessableReason.SESSION_PLAN_REFERENCES_INCOHERENT
    )
    assert any("blank position plan governance id" in line for line in result.limitations)


def test_attack_b_whitespace_only_plan_id_withholds_the_audit() -> None:
    result = audit(plans=(plan(pid="   "),))
    assert (
        result.unassessable_reason
        is FollowThroughUnassessableReason.SESSION_PLAN_REFERENCES_INCOHERENT
    )


def test_attack_b_one_blank_among_valid_plans_still_withholds() -> None:
    """A single unusable identity poisons the join for the whole session --
    partial auditing would silently report an incomplete picture as complete."""
    result = audit(plans=(plan(pid="PLAN-1", symbol="AAA"), plan(pid="", symbol="BBB", rank=2)))
    assert result.outcome is FollowThroughOutcome.NOT_ASSESSABLE
    assert result.entries == ()


def test_attack_c_conflicting_instruments_never_audit_an_arbitrary_first_plan() -> None:
    result = audit(
        plans=(plan(pid="PLAN-X", symbol="AAPL", rank=1), plan(pid="PLAN-X", symbol="TSLA", rank=2))
    )
    assert result.outcome is FollowThroughOutcome.NOT_ASSESSABLE
    assert result.entries == ()
    assert result.approved_plan_count == 0
    assert result.with_open_asserted_position == 0
    assert result.with_closed_asserted_position == 0
    assert result.with_no_asserted_position_recorded == 0
    # The rejected report must not name a winner anywhere.
    assert not any("AAPL was audited" in line for line in result.limitations)


def test_attack_c_conflict_is_detected_regardless_of_reference_order() -> None:
    forward = audit(
        plans=(plan(pid="PLAN-X", symbol="AAPL", rank=1), plan(pid="PLAN-X", symbol="TSLA", rank=2))
    )
    reverse = audit(
        plans=(plan(pid="PLAN-X", symbol="TSLA", rank=2), plan(pid="PLAN-X", symbol="AAPL", rank=1))
    )
    assert forward.outcome is reverse.outcome is FollowThroughOutcome.NOT_ASSESSABLE
    assert forward == reverse


def test_attack_d_rank_divergence_is_presentation_metadata_not_incoherence() -> None:
    """Explicit decision: `rank` is the session's operator-facing presentation
    priority, not part of what a ledger citation refers to. Same id and same
    instrument means the join is unambiguous, so a rank divergence is reported
    rather than withheld."""
    result = audit(
        plans=(plan(pid="PLAN-1", symbol="AAPL", rank=1), plan(pid="PLAN-1", symbol="AAPL", rank=3))
    )
    assert result.outcome is FollowThroughOutcome.AUDITED
    assert result.approved_plan_count == 1
    assert any("more than one rank" in line for line in result.limitations)
    assert any("not part of plan identity" in line for line in result.limitations)


def test_attack_e_exact_duplicate_reference_is_deduplicated_and_reported() -> None:
    result = audit(plans=(plan(), plan()))
    assert result.outcome is FollowThroughOutcome.AUDITED
    assert result.approved_plan_count == 1
    assert any("exact duplicate approved plan reference" in line for line in result.limitations)


def test_attack_e_unique_plans_produce_no_duplicate_limitation() -> None:
    result = audit(
        plans=(plan(pid="PLAN-A", symbol="AAA"), plan(pid="PLAN-B", symbol="BBB", rank=2))
    )
    assert not any("exact duplicate" in line for line in result.limitations)


def test_attack_f_a_ledger_citation_cannot_resolve_an_ambiguous_plan_id() -> None:
    """The citation is evidence of what the operator referenced, not evidence
    of which of two conflicting plans it meant."""
    result = audit(
        plans=(
            plan(pid="PLAN-X", symbol="AAPL", rank=1),
            plan(pid="PLAN-X", symbol="TSLA", rank=2),
        ),
        events=(event(gid="E1", pos="P1", symbol="AAPL", cites="PLAN-X"),),
    )
    assert result.outcome is FollowThroughOutcome.NOT_ASSESSABLE
    assert result.entries == ()
    # Nor may the position leak out through the unlinked classification.
    assert result.unlinked_open_positions == ()


def test_attack_g_normal_unique_plans_are_unchanged() -> None:
    result = audit(
        plans=(plan(pid="PLAN-A", symbol="AAA"), plan(pid="PLAN-B", symbol="BBB", rank=2)),
        events=(event(gid="E1", pos="P1", symbol="AAA", cites="PLAN-A"),),
    )
    assert result.outcome is FollowThroughOutcome.AUDITED
    assert result.approved_plan_count == 2
    assert result.with_open_asserted_position == 1
    assert result.with_no_asserted_position_recorded == 1


def test_withholding_precedes_the_ledger_checks() -> None:
    """An incoherent session reports the same reason whatever the ledger is
    doing, so the diagnosis never depends on unrelated state."""
    ambiguous = (
        plan(pid="PLAN-X", symbol="AAPL", rank=1),
        plan(pid="PLAN-X", symbol="TSLA", rank=2),
    )
    for kwargs in ({"ledger_available": False}, {"incoherent": True}, {}):
        result = audit(plans=ambiguous, **kwargs)  # type: ignore[arg-type]
        assert (
            result.unassessable_reason
            is FollowThroughUnassessableReason.SESSION_PLAN_REFERENCES_INCOHERENT
        )


def test_the_withheld_result_carries_no_money_and_no_conduct_claim() -> None:
    result = audit(
        plans=(plan(pid="PLAN-X", symbol="AAPL", rank=1), plan(pid="PLAN-X", symbol="TSLA", rank=2))
    )
    rendered = " ".join(result.limitations)
    for forbidden in ("ignored", "failed to", "did not act on", "profit", "P&L"):
        assert forbidden.lower() not in rendered.lower()
