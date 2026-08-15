"""MILESTONE-078 — Research decision follow-through audit.

The platform can propose (M057-M060), record what the operator asserts they
hold (M076), and judge today's proposals against that held exposure (M077) --
and then it loses the thread. Nothing joins a research session's approved plans
back to the operator's own ledger, so no one can ask what became of what the
research recommended.

Plan lineage already exists: an `OPENED` event may cite the position plan the
operator says it came from. A repository-wide search shows it is consumed in
exactly two ways -- M077's double-counting suppression, over OPEN positions of
TODAY's session only, and single-position display. This module answers the
remaining question.

WHAT A STATUS MEANS, AND WHAT IT DOES NOT
-----------------------------------------
`NO_ASSERTED_POSITION_RECORDED` means NOTHING WAS WRITTEN DOWN citing that plan.

It does NOT mean the operator ignored the plan, rejected it, failed to act on
it, or did anything else. The ledger records assertions, not conduct, and its
silence is not evidence about what a human did. This is the single most
important semantic in this module.

There is deliberately no FOLLOWED / NOT_FOLLOWED / ADHERENCE / COMPLIANCE
vocabulary anywhere here: those words judge the operator, and the data cannot
support a judgement.

NO MONEY
--------
This module reads no price and performs no arithmetic over money. It emits
statuses, counts, quantities and identifiers only. Accidental P&L, accidental
valuation and accidental profitability claims are therefore structurally
impossible rather than merely discouraged.

This module is pure: no I/O, no clock, no randomness, no float, no Decimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from empirical_platform.decision_candidate.operator_position_ledger import (
    DerivedPosition,
    DerivedPositionState,
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)

__all__ = [
    "FOLLOW_THROUGH_BANNER",
    "ApprovedPlanReference",
    "FollowThroughOutcome",
    "FollowThroughStatus",
    "FollowThroughUnassessableReason",
    "PlanFollowThroughEntry",
    "ResearchDecisionFollowThrough",
    "UnlinkedAssertedPosition",
    "UnlinkedPositionReason",
    "audit_research_decision_follow_through",
    "cited_plan_by_position",
]

FOLLOW_THROUGH_BANNER = (
    "what this session's approved position plans have RECORDED against them in the "
    "operator's own ledger, as of an explicit timestamp. A recorded assertion is NOT "
    "evidence that any trade occurred: it is what the operator wrote down. The ABSENCE "
    "of a record is NOT evidence that the operator did nothing -- it means nothing was "
    "written down, and this report makes no judgement about the operator's conduct. A "
    "cited plan is what the operator referenced, NOT proof that the plan caused the "
    "position. NOT broker-verified; NOT execution; NOT fills; NOT a market valuation; "
    "NOT realized or unrealized P&L; NOT a profitability claim; NOT advice. This report "
    "contains no monetary value of any kind."
)


class FollowThroughStatus(StrEnum):
    """What the ledger records against one approved plan, and nothing more."""

    #: An operator-asserted position citing this plan is open at `as_of`.
    ASSERTED_POSITION_OPEN = "ASSERTED_POSITION_OPEN"
    #: Such a position exists and is closed at `as_of`. A lifecycle fact only --
    #: it says nothing about a realized result, and no money is attached to it.
    ASSERTED_POSITION_CLOSED = "ASSERTED_POSITION_CLOSED"
    #: Nothing was written down citing this plan. NOT "ignored", NOT "rejected",
    #: NOT "not acted upon" -- the ledger's silence is not evidence about
    #: anything the operator did.
    NO_ASSERTED_POSITION_RECORDED = "NO_ASSERTED_POSITION_RECORDED"


class UnlinkedPositionReason(StrEnum):
    """Why an open asserted position is not matched to this session."""

    #: The opening assertion carried no plan citation at all.
    CITES_NO_PLAN = "CITES_NO_PLAN"
    #: It cites a plan id that is not among this session's approved plans.
    CITES_PLAN_OUTSIDE_THIS_SESSION = "CITES_PLAN_OUTSIDE_THIS_SESSION"


class FollowThroughOutcome(StrEnum):
    """Closed vocabulary for the audit as a whole."""

    AUDITED = "AUDITED"
    NO_APPROVED_POSITION_PLANS = "NO_APPROVED_POSITION_PLANS"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class FollowThroughUnassessableReason(StrEnum):
    """Why the audit was withheld. Absence is never rendered as a pass."""

    #: The ledger could not be read at all. Distinct from an empty ledger,
    # which is a real observation that nothing was recorded.
    LEDGER_UNAVAILABLE = "LEDGER_UNAVAILABLE"
    #: Persisted events do not fold into a coherent sequence.
    LEDGER_INCOHERENT = "LEDGER_INCOHERENT"
    #: The session's own approved plan references cannot serve as a join
    #: authority: an id is blank, or one id carries conflicting authoritative
    #: identity. Owner review of 2c14d0a established that picking a "first"
    #: plan in that case is deterministic but NOT semantically safe -- a ledger
    #: citation of an ambiguous id cannot honestly be attributed to either
    #: candidate, so no audit is performed at all.
    SESSION_PLAN_REFERENCES_INCOHERENT = "SESSION_PLAN_REFERENCES_INCOHERENT"


@dataclass(frozen=True, slots=True)
class ApprovedPlanReference:
    """One approved position plan of the session being audited, as the session
    itself recorded it. Carries no money by construction."""

    rank: int | None
    instrument_symbol: str
    position_plan_governance_id: str


@dataclass(frozen=True, slots=True)
class PlanFollowThroughEntry:
    """What the ledger records against one approved plan."""

    rank: int | None
    instrument_symbol: str
    position_plan_governance_id: str
    status: FollowThroughStatus
    #: Retained separately so a plan cited by both an open and a closed position
    # does not lose the closed one to status precedence.
    open_position_count: int
    closed_position_count: int
    position_governance_ids: tuple[str, ...]
    #: Positions citing this plan whose instrument differs from the plan's own.
    # Reported rather than dropped: the citation is what the operator recorded.
    # Counting it as follow-through without saying so would assert a position
    # against THIS plan's instrument, which is not what happened.
    mismatched_instrument_position_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnlinkedAssertedPosition:
    """An open asserted position that this session's plans do not account for.

    Reported as a citation fact. Deliberately not called unauthorized,
    discretionary or off-plan -- none of which the data can establish.
    """

    position_governance_id: str
    instrument_symbol: str
    open_quantity: int
    reason: UnlinkedPositionReason
    cited_plan_governance_id: str | None


@dataclass(frozen=True, slots=True)
class ResearchDecisionFollowThrough:
    """The whole audit. Contains no monetary value of any kind."""

    outcome: FollowThroughOutcome
    unassessable_reason: FollowThroughUnassessableReason | None
    session_governance_id: str
    as_of: datetime
    approved_plan_count: int
    with_open_asserted_position: int
    with_closed_asserted_position: int
    with_no_asserted_position_recorded: int
    entries: tuple[PlanFollowThroughEntry, ...] = ()
    unlinked_open_positions: tuple[UnlinkedAssertedPosition, ...] = ()
    excluded_future_event_count: int = 0
    limitations: tuple[str, ...] = field(default_factory=tuple)


def cited_plan_by_position(
    events: tuple[OperatorAssertedPositionEvent, ...],
) -> dict[str, str]:
    """Map position key -> the plan its OPENED event cites.

    M076's `DerivedPosition` does not carry lineage and M076 is frozen, so this
    projects it from the same event tuple the caller already read. It does not
    re-implement M076's fold, which remains the sole authority on open vs
    closed.

    A blank or whitespace-only citation is not an identifier -- treating one as
    an id would let a malformed row match a real plan. Carried forward from the
    M077 R04 defect.
    """
    cited: dict[str, str] = {}
    for event in events:
        if event.kind is not OperatorPositionEventKind.OPENED:
            continue
        raw = event.source_position_plan_governance_id
        if raw is None or not raw.strip():
            continue
        cited[event.position_governance_id] = raw.strip()
    return cited


def _plan_reference_incoherence(
    approved_plans: tuple[ApprovedPlanReference, ...],
) -> str | None:
    """Why these references cannot serve as a join authority, or `None`.

    Two conditions disqualify them, and neither can be resolved by choosing a
    winner:

    * a blank or whitespace-only governance id is not an identifier at all;
    * one non-blank id carrying conflicting authoritative identity -- currently
      a differing `instrument_symbol` -- because a citation of that id refers to
      no single plan.

    `rank` is deliberately NOT part of this test. It is the session's
    presentation priority for a decision, not part of what a citation refers to,
    so a rank divergence is reported as a limitation rather than withheld.
    """
    blank = sorted(
        plan.instrument_symbol
        for plan in approved_plans
        if not plan.position_plan_governance_id.strip()
    )
    if blank:
        return (
            f"{len(blank)} approved plan reference(s) carry a blank position plan "
            f"governance id (instrument(s) {', '.join(blank)}); a blank id is not an "
            "identifier and cannot be joined to a ledger citation"
        )

    by_id: dict[str, str] = {}
    for plan in sorted(approved_plans, key=_plan_order):
        key = plan.position_plan_governance_id.strip()
        seen = by_id.setdefault(key, plan.instrument_symbol)
        if seen != plan.instrument_symbol:
            return (
                f"plan id {key} names more than one instrument ({seen}, "
                f"{plan.instrument_symbol}); a ledger citation of {key} refers to neither "
                "in particular, and choosing one by sort order would invent an answer the "
                "session data does not contain"
            )
    return None


def _plan_order(plan: ApprovedPlanReference) -> tuple[int, int, str]:
    """Deterministic priority, identical to M075/M077 so the artifacts cannot
    disagree about order: ranked plans first in rank order, then unranked, then
    symbol as an explicit tiebreak."""
    if plan.rank is None:
        return (1, 0, plan.instrument_symbol)
    return (0, plan.rank, plan.instrument_symbol)


def _position_order(position: DerivedPosition) -> tuple[str, str]:
    return (position.instrument_symbol, position.position_governance_id)


def _unassessable(
    *,
    reason: FollowThroughUnassessableReason,
    session_governance_id: str,
    as_of: datetime,
    approved_plan_count: int,
    limitations: tuple[str, ...],
) -> ResearchDecisionFollowThrough:
    return ResearchDecisionFollowThrough(
        outcome=FollowThroughOutcome.NOT_ASSESSABLE,
        unassessable_reason=reason,
        session_governance_id=session_governance_id,
        as_of=as_of,
        approved_plan_count=approved_plan_count,
        with_open_asserted_position=0,
        with_closed_asserted_position=0,
        with_no_asserted_position_recorded=0,
        limitations=limitations,
    )


def audit_research_decision_follow_through(
    *,
    session_governance_id: str,
    session_as_of: datetime,
    approved_plans: tuple[ApprovedPlanReference, ...],
    events: tuple[OperatorAssertedPositionEvent, ...],
    held_state: DerivedPositionState | None,
    as_of: datetime,
    ledger_available: bool = True,
) -> ResearchDecisionFollowThrough:
    """Audit what this session's approved plans have recorded against them.

    `as_of` is required and inclusive. There is deliberately no default: the
    answer depends entirely on the window, and the one obvious default -- the
    session's own `as_of` -- is the single window guaranteed to show nothing,
    because nothing can have been recorded before the session existed.
    """
    limitations: list[str] = []

    # Deduplicate by plan id, keeping the first in deterministic order, so one
    # plan is one entry however many times the session names it.
    # OWNER CORRECTION (review of 2c14d0a). The plan governance id is the JOIN
    # AUTHORITY between the session and the ledger, so it must be validated as
    # an identity BEFORE any lineage is read. The previous behaviour -- keep the
    # first in deterministic order and emit a limitation -- was deterministic
    # but not semantically safe: when PLAN-X names both AAPL and TSLA, a ledger
    # event citing PLAN-X refers to neither in particular, and choosing AAPL
    # because it sorts first invents an answer the data does not contain.
    incoherence = _plan_reference_incoherence(approved_plans)
    if incoherence is not None:
        limitations.append(incoherence)
        limitations.append(
            f"{len(approved_plans)} raw approved plan reference(s) were present; no plan "
            "count, status, or unlinked classification is reported, because every one of "
            "them would depend on the ambiguous join"
        )
        return _unassessable(
            reason=FollowThroughUnassessableReason.SESSION_PLAN_REFERENCES_INCOHERENT,
            session_governance_id=session_governance_id,
            as_of=as_of,
            approved_plan_count=0,
            limitations=tuple(limitations),
        )

    unique: dict[str, ApprovedPlanReference] = {}
    exact_duplicates = 0
    rank_divergences: list[str] = []
    for plan in sorted(approved_plans, key=_plan_order):
        existing = unique.setdefault(plan.position_plan_governance_id, plan)
        if existing is plan:
            continue
        if existing.rank != plan.rank:
            # Identity is unambiguous here: same id, same instrument. `rank` is
            # the session's operator-facing PRESENTATION priority, not part of
            # what a citation refers to, so a divergence does not make the join
            # ambiguous. It is reported rather than treated as incoherence.
            rank_divergences.append(
                f"plan {plan.position_plan_governance_id} appears with more than one rank "
                f"({existing.rank}, {plan.rank}); rank is presentation priority and not "
                f"part of plan identity, so the deterministically first ({existing.rank}) "
                "orders the report and the join is unaffected"
            )
        else:
            exact_duplicates += 1
    if exact_duplicates:
        # Harmless to the join -- identical id AND identical authoritative
        # identity -- but never hidden.
        limitations.append(
            f"{exact_duplicates} exact duplicate approved plan reference(s) were "
            "deduplicated; each names the same plan with the same instrument and rank, so "
            "the join is unaffected"
        )
    limitations.extend(rank_divergences)
    ordered_plans = tuple(sorted(unique.values(), key=_plan_order))
    plan_ids = frozenset(unique)

    if not ledger_available:
        limitations.append(
            "the operator position ledger could not be read; the audit is withheld "
            "rather than presented as if nothing had been recorded"
        )
        return _unassessable(
            reason=FollowThroughUnassessableReason.LEDGER_UNAVAILABLE,
            session_governance_id=session_governance_id,
            as_of=as_of,
            approved_plan_count=len(ordered_plans),
            limitations=tuple(limitations),
        )

    if held_state is None:
        limitations.append(
            "persisted operator position events do not fold into a coherent sequence; "
            "the audit is withheld"
        )
        return _unassessable(
            reason=FollowThroughUnassessableReason.LEDGER_INCOHERENT,
            session_governance_id=session_governance_id,
            as_of=as_of,
            approved_plan_count=len(ordered_plans),
            limitations=tuple(limitations),
        )

    if as_of < session_as_of:
        limitations.append(
            f"the requested as_of ({as_of.isoformat()}) precedes this session's own "
            f"as_of ({session_as_of.isoformat()}), so the window ends before the session "
            "existed; nothing could have been recorded against its plans in that window"
        )

    limitations.append(
        "a plan with no record is a plan nothing was written down against; it is not a "
        "finding that the operator did not act, and no judgement of conduct is made"
    )
    if held_state.excluded_future_event_count:
        limitations.append(
            f"{held_state.excluded_future_event_count} operator-asserted event(s) stamped "
            "after the requested as_of were excluded"
        )

    cited = cited_plan_by_position(events)
    open_by_plan: dict[str, list[DerivedPosition]] = {}
    closed_by_plan: dict[str, list[DerivedPosition]] = {}
    for position in held_state.open_positions:
        plan_id = cited.get(position.position_governance_id)
        if plan_id is not None:
            open_by_plan.setdefault(plan_id, []).append(position)
    for position in held_state.closed_positions:
        plan_id = cited.get(position.position_governance_id)
        if plan_id is not None:
            closed_by_plan.setdefault(plan_id, []).append(position)

    entries: list[PlanFollowThroughEntry] = []
    for plan in ordered_plans:
        opens = open_by_plan.get(plan.position_plan_governance_id, [])
        closes = closed_by_plan.get(plan.position_plan_governance_id, [])
        if opens:
            # An open position is the currently-true fact and takes precedence,
            # but the closed count is retained so it is never lost.
            status = FollowThroughStatus.ASSERTED_POSITION_OPEN
        elif closes:
            status = FollowThroughStatus.ASSERTED_POSITION_CLOSED
        else:
            status = FollowThroughStatus.NO_ASSERTED_POSITION_RECORDED
        mismatched = tuple(
            sorted(
                position.position_governance_id
                for position in (*opens, *closes)
                if position.instrument_symbol != plan.instrument_symbol
            )
        )
        if mismatched:
            limitations.append(
                f"plan {plan.position_plan_governance_id} ({plan.instrument_symbol}) is "
                f"cited by position(s) {', '.join(mismatched)} recorded on a different "
                "instrument; the citation is reported as the operator recorded it and is "
                "not evidence of a position on this plan's instrument"
            )
        entries.append(
            PlanFollowThroughEntry(
                rank=plan.rank,
                instrument_symbol=plan.instrument_symbol,
                position_plan_governance_id=plan.position_plan_governance_id,
                status=status,
                open_position_count=len(opens),
                closed_position_count=len(closes),
                position_governance_ids=tuple(
                    sorted(position.position_governance_id for position in (*opens, *closes))
                ),
                mismatched_instrument_position_ids=mismatched,
            )
        )

    unlinked: list[UnlinkedAssertedPosition] = []
    for position in sorted(held_state.open_positions, key=_position_order):
        plan_id = cited.get(position.position_governance_id)
        if plan_id is not None and plan_id in plan_ids:
            continue
        unlinked.append(
            UnlinkedAssertedPosition(
                position_governance_id=position.position_governance_id,
                instrument_symbol=position.instrument_symbol,
                open_quantity=position.open_quantity,
                reason=(
                    UnlinkedPositionReason.CITES_NO_PLAN
                    if plan_id is None
                    else UnlinkedPositionReason.CITES_PLAN_OUTSIDE_THIS_SESSION
                ),
                cited_plan_governance_id=plan_id,
            )
        )

    outcome = (
        FollowThroughOutcome.AUDITED
        if ordered_plans
        else FollowThroughOutcome.NO_APPROVED_POSITION_PLANS
    )
    return ResearchDecisionFollowThrough(
        outcome=outcome,
        unassessable_reason=None,
        session_governance_id=session_governance_id,
        as_of=as_of,
        approved_plan_count=len(ordered_plans),
        with_open_asserted_position=sum(
            1 for e in entries if e.status is FollowThroughStatus.ASSERTED_POSITION_OPEN
        ),
        with_closed_asserted_position=sum(
            1 for e in entries if e.status is FollowThroughStatus.ASSERTED_POSITION_CLOSED
        ),
        with_no_asserted_position_recorded=sum(
            1 for e in entries if e.status is FollowThroughStatus.NO_ASSERTED_POSITION_RECORDED
        ),
        entries=tuple(entries),
        unlinked_open_positions=tuple(unlinked),
        excluded_future_event_count=held_state.excluded_future_event_count,
        limitations=tuple(limitations),
    )
