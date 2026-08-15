"""MILESTONE-079 — Operator evidence availability snapshot (point-in-time).

M076 persists TWO timestamps on every operator assertion:

    event_timestamp  when the operator says the event happened  (EFFECTIVE time)
    recorded_at      when the assertion was written down        (RECORDED time)

Both are TIMESTAMPTZ NOT NULL and both are validated timezone-aware. But a
repository-wide search shows `recorded_at` is never filtered on, never ordered
on, and never read by any derivation: the fold's only temporal filter is
`event_timestamp <= as_of`.

So the platform already stores knowledge-time and has no way to use it, and
M078's frozen limitation names the consequence exactly -- it is effective-time
evidence, and must not be used for calibration or forward evaluation "without a
recorded_at / evidence-availability firewall". This module is that firewall.

TWO QUESTIONS, NOT ONE
----------------------
    M076 / M078 ask:  what does the ledger NOW say happened by E?
    M079 asks:        what evidence was AVAILABLE by K about what happened by E?

Both are legitimate and they are NOT interchangeable. Evaluating a decision
against evidence recorded after it was made is a look-ahead leak.

SEPARATION OF DUTIES
--------------------
This module applies ONLY the knowledge filter (`recorded_at <= K`) and hands
the survivors to M076's own `derive_position_state`, which applies the
effective filter and folds. M079 adds exactly one dimension and delegates the
other: M076's fold remains the sole authority on open versus closed, is not
modified, and is not re-implemented.

INCOMPLETE KNOWLEDGE IS NOT CORRUPTION
--------------------------------------
Knowledge filtering can legitimately produce a sequence the fold rejects -- a
CLOSED whose OPENED was recorded later. That is not corrupt data; it is the
honest shape of partial knowledge, and nothing is invented to paper over it.
Because the fold raises the same exception for both cases, the failure path
re-folds the key UNFILTERED to tell them apart (design review T07).

This module is pure: no I/O, no clock, no randomness, no float.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from empirical_platform.decision_candidate.operator_position_ledger import (
    DerivedPosition,
    LedgerRejectionError,
    OperatorAssertedPositionEvent,
    derive_position_state,
)

__all__ = [
    "EVIDENCE_AVAILABILITY_BANNER",
    "EvidenceSnapshotOutcome",
    "EvidenceUnassessableReason",
    "KnownPositionStatus",
    "OperatorEvidenceSnapshot",
    "PositionEvidenceEntry",
    "build_operator_evidence_snapshot",
    "events_known_by",
]

EVIDENCE_AVAILABILITY_BANNER = (
    "what the operator's ledger had RECORDED by the knowledge cutoff about what it "
    "says happened by the effective cutoff. This is an EVIDENCE-AVAILABILITY snapshot: "
    "KNOWN means known TO THE LEDGER by that cutoff, NOT known to be true. An assertion "
    "recorded later is deliberately invisible here, which is the point -- evaluating a "
    "decision against evidence recorded after it was made is a look-ahead leak. A "
    "position reported open may later prove to have been reduced by an assertion "
    "recorded afterwards. NOT broker-verified; NOT execution; NOT fills; NOT actual "
    "holdings; NOT a market valuation; NOT realized or unrealized P&L; NOT a "
    "profitability claim; NOT a causal claim; NOT advice. Asserted prices and notionals "
    "are M076's own operator assertions, never revalued."
)


class KnownPositionStatus(StrEnum):
    """What the knowledge-filtered evidence supports for one position key."""

    #: The filtered evidence folds coherently and the position is open at the
    #: effective cutoff. KNOWN to the ledger by K -- not known to be true.
    KNOWN_OPEN = "KNOWN_OPEN"
    #: The filtered evidence folds coherently and the position is closed.
    KNOWN_CLOSED = "KNOWN_CLOSED"
    #: The evidence visible at K does not fold -- typically a CLOSED or REDUCED
    #: whose OPENED was recorded later. A property of the SNAPSHOT, not of the
    #: operator, and no state is invented for it.
    INCOMPLETE_KNOWLEDGE_SEQUENCE = "INCOMPLETE_KNOWLEDGE_SEQUENCE"
    #: The key does not fold even over the UNFILTERED event set, so the
    #: underlying data is genuinely incoherent rather than merely truncated.
    LEDGER_INCOHERENT_FOR_POSITION = "LEDGER_INCOHERENT_FOR_POSITION"


class EvidenceSnapshotOutcome(StrEnum):
    """Closed vocabulary for the snapshot as a whole."""

    EVIDENCE_SNAPSHOT_AVAILABLE = "EVIDENCE_SNAPSHOT_AVAILABLE"
    #: Nothing had been recorded by the knowledge cutoff. Distinct from "nothing
    #: happened" -- the ledger was simply silent at that moment.
    NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF = "NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class EvidenceUnassessableReason(StrEnum):
    """Why the snapshot was withheld. Absence is never rendered as a pass."""

    LEDGER_UNAVAILABLE = "LEDGER_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class PositionEvidenceEntry:
    """One position key as the knowledge-filtered evidence supports it.

    `position` is M076's own derived position, carried through unchanged, and is
    `None` whenever the evidence does not support a state -- never a placeholder.
    """

    position_governance_id: str
    instrument_symbol: str
    status: KnownPositionStatus
    position: DerivedPosition | None
    #: M076's own rejection reason when the evidence does not fold. Preserved
    #: verbatim so the refusal is traceable to the frozen authority.
    rejection_reason: str | None
    #: Events for this key visible at (E, K).
    visible_event_count: int


@dataclass(frozen=True, slots=True)
class OperatorEvidenceSnapshot:
    """The whole point-in-time snapshot."""

    outcome: EvidenceSnapshotOutcome
    unassessable_reason: EvidenceUnassessableReason | None
    effective_as_of: datetime
    knowledge_as_of: datetime
    total_event_count: int
    visible_event_count: int
    #: Recorded by K, but stamped after the effective cutoff.
    excluded_by_effective_cutoff: int
    #: Recorded after the knowledge cutoff, whatever their effective time. This
    #: is the firewall's own effect, and merging it into one count would make
    #: that effect invisible.
    excluded_by_knowledge_cutoff: int
    known_open_count: int
    known_closed_count: int
    incomplete_knowledge_count: int
    incoherent_position_count: int
    entries: tuple[PositionEvidenceEntry, ...] = ()
    limitations: tuple[str, ...] = field(default_factory=tuple)


def events_known_by(
    events: tuple[OperatorAssertedPositionEvent, ...],
    knowledge_as_of: datetime,
) -> tuple[OperatorAssertedPositionEvent, ...]:
    """The assertions that had been RECORDED by `knowledge_as_of`, inclusive.

    This is the whole of M079's own filtering. The effective filter belongs to
    M076 and is not duplicated here.
    """
    return tuple(event for event in events if event.recorded_at <= knowledge_as_of)


def _entry_order(entry: PositionEvidenceEntry) -> tuple[str, str]:
    return (entry.instrument_symbol, entry.position_governance_id)


def _group_by_position(
    events: tuple[OperatorAssertedPositionEvent, ...],
) -> dict[str, tuple[OperatorAssertedPositionEvent, ...]]:
    grouped: dict[str, list[OperatorAssertedPositionEvent]] = {}
    for event in events:
        grouped.setdefault(event.position_governance_id, []).append(event)
    return {key: tuple(value) for key, value in grouped.items()}


def _fold_one_key(
    events: tuple[OperatorAssertedPositionEvent, ...], effective_as_of: datetime
) -> DerivedPosition:
    """Fold ONE key through M076's own authority, returning its position.

    Folding a single key at a time is what lets one incomplete key be reported
    without withholding the whole snapshot -- and it reuses the frozen fold
    rather than re-implementing it.

    Callers pass events already filtered to `event_timestamp <= effective_as_of`
    and grouped by one key, so exactly one position always results. That
    invariant is asserted rather than silently tolerated: implementation review
    R01 found that returning `None` here let the caller `continue`, which would
    drop a position from the snapshot with no entry, no count and no limitation
    recording the omission. A snapshot that silently loses a position is worse
    than one that fails loudly.
    """
    state = derive_position_state(events=events, as_of=effective_as_of)
    for position in (*state.open_positions, *state.closed_positions):
        return position
    raise AssertionError(
        "invariant violated: a non-empty, effective-filtered single-key event group "
        "must fold to exactly one position"
    )


def build_operator_evidence_snapshot(
    *,
    events: tuple[OperatorAssertedPositionEvent, ...],
    effective_as_of: datetime,
    knowledge_as_of: datetime,
    ledger_available: bool = True,
) -> OperatorEvidenceSnapshot:
    """Build the point-in-time evidence snapshot at `(effective_as_of, knowledge_as_of)`.

    Both cutoffs are required, inclusive, and must be timezone-aware. Neither
    has a default: a default on either dimension would silently choose an
    epistemic stance.
    """
    for label, moment in (
        ("effective_as_of", effective_as_of),
        ("knowledge_as_of", knowledge_as_of),
    ):
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware; a naive datetime has no instant")

    limitations: list[str] = []

    if not ledger_available:
        limitations.append(
            "the operator position ledger could not be read; the snapshot is withheld "
            "rather than presented as if nothing had been recorded"
        )
        return OperatorEvidenceSnapshot(
            outcome=EvidenceSnapshotOutcome.NOT_ASSESSABLE,
            unassessable_reason=EvidenceUnassessableReason.LEDGER_UNAVAILABLE,
            effective_as_of=effective_as_of,
            knowledge_as_of=knowledge_as_of,
            total_event_count=0,
            visible_event_count=0,
            excluded_by_effective_cutoff=0,
            excluded_by_knowledge_cutoff=0,
            known_open_count=0,
            known_closed_count=0,
            incomplete_knowledge_count=0,
            incoherent_position_count=0,
            limitations=tuple(limitations),
        )

    known = events_known_by(events, knowledge_as_of)
    excluded_by_knowledge = len(events) - len(known)
    visible = tuple(e for e in known if e.event_timestamp <= effective_as_of)
    excluded_by_effective = len(known) - len(visible)

    limitations.append(
        "KNOWN means known to the ledger by the knowledge cutoff, not known to be true; "
        "an assertion recorded later is deliberately invisible here"
    )
    if excluded_by_knowledge:
        limitations.append(
            f"{excluded_by_knowledge} assertion(s) were recorded after the knowledge "
            "cutoff and are excluded; this is the firewall's own effect, not an absence "
            "of activity"
        )
    if excluded_by_effective:
        limitations.append(
            f"{excluded_by_effective} assertion(s) were recorded by the knowledge cutoff "
            "but are stamped after the effective cutoff, and are excluded"
        )
    if knowledge_as_of < effective_as_of:
        limitations.append(
            f"the knowledge cutoff ({knowledge_as_of.isoformat()}) precedes the effective "
            f"cutoff ({effective_as_of.isoformat()}); this asks what was known then about "
            "what had happened by the later moment, which is meaningful but easy to "
            "misread"
        )

    if not known:
        return OperatorEvidenceSnapshot(
            outcome=EvidenceSnapshotOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF,
            unassessable_reason=None,
            effective_as_of=effective_as_of,
            knowledge_as_of=knowledge_as_of,
            total_event_count=len(events),
            visible_event_count=0,
            excluded_by_effective_cutoff=excluded_by_effective,
            excluded_by_knowledge_cutoff=excluded_by_knowledge,
            known_open_count=0,
            known_closed_count=0,
            incomplete_knowledge_count=0,
            incoherent_position_count=0,
            limitations=tuple(limitations),
        )

    unfiltered_by_key = _group_by_position(events)
    entries: list[PositionEvidenceEntry] = []

    for key, key_events in _group_by_position(visible).items():
        symbol = key_events[0].instrument_symbol
        try:
            position = _fold_one_key(key_events, effective_as_of)
        except LedgerRejectionError as filtered_failure:
            # Design review T07. The fold raises the SAME exception for a
            # knowledge-truncated prefix and for genuinely corrupt data, so the
            # only honest way to tell them apart is to ask whether the failure
            # survives when the knowledge filter is removed. This decides ONLY
            # how to label the refusal -- no state from the unfiltered fold is
            # ever reported, so no future knowledge leaks into the answer.
            try:
                _fold_one_key(unfiltered_by_key[key], effective_as_of)
            except LedgerRejectionError as unfiltered_failure:
                status = KnownPositionStatus.LEDGER_INCOHERENT_FOR_POSITION
                reason = unfiltered_failure.reason.value
            else:
                status = KnownPositionStatus.INCOMPLETE_KNOWLEDGE_SEQUENCE
                reason = filtered_failure.reason.value
            entries.append(
                PositionEvidenceEntry(
                    position_governance_id=key,
                    instrument_symbol=symbol,
                    status=status,
                    position=None,
                    rejection_reason=reason,
                    visible_event_count=len(key_events),
                )
            )
            continue

        entries.append(
            PositionEvidenceEntry(
                position_governance_id=key,
                instrument_symbol=symbol,
                status=(
                    KnownPositionStatus.KNOWN_OPEN
                    if position.is_open
                    else KnownPositionStatus.KNOWN_CLOSED
                ),
                position=position,
                rejection_reason=None,
                visible_event_count=len(key_events),
            )
        )

    ordered = tuple(sorted(entries, key=_entry_order))
    if any(e.status is KnownPositionStatus.INCOMPLETE_KNOWLEDGE_SEQUENCE for e in ordered):
        limitations.append(
            "one or more positions have evidence that does not fold at this knowledge "
            "cutoff, typically a close or reduction whose opening was recorded later; no "
            "state is reported for them and none is inferred"
        )
    if any(e.status is KnownPositionStatus.LEDGER_INCOHERENT_FOR_POSITION for e in ordered):
        limitations.append(
            "one or more positions do not fold even over the unfiltered ledger, so their "
            "underlying data is genuinely incoherent rather than merely incomplete"
        )

    return OperatorEvidenceSnapshot(
        outcome=EvidenceSnapshotOutcome.EVIDENCE_SNAPSHOT_AVAILABLE,
        unassessable_reason=None,
        effective_as_of=effective_as_of,
        knowledge_as_of=knowledge_as_of,
        total_event_count=len(events),
        visible_event_count=len(visible),
        excluded_by_effective_cutoff=excluded_by_effective,
        excluded_by_knowledge_cutoff=excluded_by_knowledge,
        known_open_count=sum(1 for e in ordered if e.status is KnownPositionStatus.KNOWN_OPEN),
        known_closed_count=sum(1 for e in ordered if e.status is KnownPositionStatus.KNOWN_CLOSED),
        incomplete_knowledge_count=sum(
            1 for e in ordered if e.status is KnownPositionStatus.INCOMPLETE_KNOWLEDGE_SEQUENCE
        ),
        incoherent_position_count=sum(
            1 for e in ordered if e.status is KnownPositionStatus.LEDGER_INCOHERENT_FOR_POSITION
        ),
        entries=ordered,
        limitations=tuple(limitations),
    )
