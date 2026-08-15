"""MILESTONE-079 -- Operator evidence availability snapshot (point-in-time).

M076 persists TWO timestamps on every operator assertion:

    event_timestamp  when the operator says the event happened  (EFFECTIVE time)
    recorded_at      when the assertion says it was written down (RECORDED time)

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
    M079 asks:        what does the ledger RECORD as having been recorded by K,
                      about what it says happened by E?

Both are legitimate and they are NOT interchangeable. Evaluating a decision
against evidence recorded after it was made is a look-ahead leak.

WHAT THIS MODULE MAY AND MAY NOT CLAIM
--------------------------------------
`recorded_at` is an operator-supplied field, not a system-assigned immutable
receipt time. So this module does NOT claim to report what evidence was
*actually* available at K. It reports what the ledger *records* as having been
recorded by K. The distinction is stated in the banner and in a limitation
carried on every snapshot. (The module and banner retain "availability" in
their names because that is the milestone's identity; the claim itself is the
weaker and accurate one.)

SEPARATION OF DUTIES
--------------------
This module applies ONLY the knowledge filter (`recorded_at <= K`) and hands
the survivors to M076's own `derive_position_state`, which applies the
effective filter and folds. M079 adds exactly one dimension and delegates the
other: M076's fold remains the sole authority on open versus closed, is not
modified, and is not re-implemented.

NO POST-CUTOFF EVIDENCE MAY INFLUENCE ANY OUTPUT
------------------------------------------------
Owner review of the first M079 candidate found a temporal leak in this module's
own design. The original code, when a knowledge-filtered sequence failed to
fold, re-folded the same key against the UNFILTERED event set in order to label
the failure INCOMPLETE_KNOWLEDGE_SEQUENCE (resolvable later) versus
LEDGER_INCOHERENT_FOR_POSITION (genuinely corrupt). No quantity was copied from
that second fold -- but the CLASSIFICATION was decided by evidence recorded
after K, which is exactly the leak this milestone exists to prevent. At K the
system cannot know which of the two it is, and saying so is the honest answer.
That discriminator is RETRACTED. Two counts derived from the full event set,
`total_event_count` and `excluded_by_knowledge_cutoff`, leaked for the same
reason and are removed with it.

The guarantee is now structural rather than disciplinary: `build_operator_
evidence_snapshot` filters once and delegates to `_snapshot_from_known_evidence`,
which is never given the unfiltered events and therefore CANNOT consult them.
Every field of the returned snapshot is a function of the surviving evidence
and the two cutoffs alone.

A consequence worth stating plainly: this snapshot cannot report how many
assertions the firewall hid, because counting them would require reading the
very evidence the cutoff excludes.

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
    "what the operator's ledger RECORDS as having been recorded by the knowledge "
    "cutoff, about what it says happened by the effective cutoff. KNOWN means known "
    "TO THE LEDGER by that cutoff, NOT known to be true. recorded_at is an "
    "operator-supplied field, not an independently attested receipt time, so this is "
    "what the ledger records about its own history -- not proof of what was actually "
    "available. An assertion recorded later is deliberately invisible here, which is "
    "the point -- evaluating a decision against evidence recorded after it was made is "
    "a look-ahead leak. Nothing recorded after the knowledge cutoff influences any "
    "figure, status or count below, including the count of what was hidden, which is "
    "why no such count is reported. A position reported open may later prove to have "
    "been reduced by an assertion recorded afterwards. NOT broker-verified; NOT "
    "execution; NOT fills; NOT actual holdings; NOT a market valuation; NOT realized "
    "or unrealized P&L; NOT a profitability claim; NOT a causal claim; NOT advice. "
    "Asserted prices and notionals are M076's own operator assertions, never revalued."
)


class KnownPositionStatus(StrEnum):
    """What the knowledge-filtered evidence supports for one position key."""

    #: The filtered evidence folds coherently and the position is open at the
    #: effective cutoff. KNOWN to the ledger by K -- not known to be true.
    KNOWN_OPEN = "KNOWN_OPEN"
    #: The filtered evidence folds coherently and the position is closed.
    KNOWN_CLOSED = "KNOWN_CLOSED"
    #: The evidence recorded by K does not form a coherent fold, and from that
    #: evidence ALONE it cannot be known whether this is temporary incompleteness
    #: -- a close or reduction whose opening was recorded later -- or underlying
    #: ledger incoherence. Deciding between the two would require reading
    #: evidence recorded after K, so M079 declines to decide. A property of the
    #: SNAPSHOT, not a verdict on the operator, and no state is invented for it.
    UNRESOLVED_KNOWLEDGE_SEQUENCE = "UNRESOLVED_KNOWLEDGE_SEQUENCE"


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
    #: M076's own rejection reason for the KNOWLEDGE-FILTERED fold. Preserved
    #: verbatim so the refusal is traceable to the frozen authority, and taken
    #: only from the filtered attempt so no post-cutoff evidence can shape it.
    rejection_reason: str | None
    #: Events for this key visible at (E, K).
    visible_event_count: int


@dataclass(frozen=True, slots=True)
class OperatorEvidenceSnapshot:
    """The whole point-in-time snapshot.

    Every field is a function of the evidence recorded by the knowledge cutoff
    and of the two cutoffs themselves. No field can vary with evidence recorded
    after the cutoff -- there is deliberately no total-ledger count and no
    hidden-assertion count, because both would leak exactly that.
    """

    outcome: EvidenceSnapshotOutcome
    unassessable_reason: EvidenceUnassessableReason | None
    effective_as_of: datetime
    knowledge_as_of: datetime
    #: Assertions recorded by the knowledge cutoff, whatever their effective time.
    known_event_count: int
    #: Of those, the ones also stamped at or before the effective cutoff.
    visible_event_count: int
    #: Recorded by K, but stamped after the effective cutoff.
    excluded_by_effective_cutoff: int
    known_open_count: int
    known_closed_count: int
    unresolved_position_count: int
    entries: tuple[PositionEvidenceEntry, ...] = ()
    limitations: tuple[str, ...] = field(default_factory=tuple)


def events_known_by(
    events: tuple[OperatorAssertedPositionEvent, ...],
    knowledge_as_of: datetime,
) -> tuple[OperatorAssertedPositionEvent, ...]:
    """The assertions the ledger records as RECORDED by `knowledge_as_of`, inclusive.

    This is the whole of M079's own filtering, and the only place the unfiltered
    event set is ever read. The effective filter belongs to M076 and is not
    duplicated here.
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

    Folding a single key at a time is what lets one unresolved key be reported
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


def _snapshot_from_known_evidence(
    *,
    known: tuple[OperatorAssertedPositionEvent, ...],
    effective_as_of: datetime,
    knowledge_as_of: datetime,
) -> OperatorEvidenceSnapshot:
    """Build the snapshot from evidence recorded by the cutoff, and nothing else.

    This function is deliberately never given the unfiltered event set. It is
    the structural form of M079's central guarantee: post-cutoff evidence cannot
    influence any output because it is not reachable from here. Owner review of
    the first candidate found that guarantee stated but not structurally
    enforced, and a discriminator inside the failure path was consulting the
    unfiltered events to classify a refusal.
    """
    visible = tuple(e for e in known if e.event_timestamp <= effective_as_of)
    excluded_by_effective = len(known) - len(visible)

    limitations: list[str] = [
        "KNOWN means known to the ledger by the knowledge cutoff, not known to be true; "
        "an assertion recorded later is deliberately invisible here",
        "recorded_at is an operator-supplied field, not an independently attested "
        "receipt time, so this snapshot reports what the ledger records as having been "
        "recorded by the cutoff rather than proof of what was actually available",
        "assertions recorded after the knowledge cutoff are excluded and influence "
        "nothing above; that exclusion is the firewall's own effect, not an absence "
        "of activity. By construction this snapshot cannot report how many such "
        "assertions there were, because counting them would require reading the very "
        "evidence the cutoff excludes",
    ]
    if excluded_by_effective:
        limitations.append(
            f"{excluded_by_effective} assertion(s) were recorded by the knowledge cutoff "
            "but are stamped after the effective cutoff, and are excluded"
        )
    if knowledge_as_of < effective_as_of:
        limitations.append(
            f"the knowledge cutoff ({knowledge_as_of.isoformat()}) precedes the effective "
            f"cutoff ({effective_as_of.isoformat()}); this asks what was recorded then about "
            "what had happened by the later moment, which is meaningful but easy to "
            "misread"
        )

    if not known:
        return OperatorEvidenceSnapshot(
            outcome=EvidenceSnapshotOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF,
            unassessable_reason=None,
            effective_as_of=effective_as_of,
            knowledge_as_of=knowledge_as_of,
            known_event_count=0,
            visible_event_count=0,
            excluded_by_effective_cutoff=0,
            known_open_count=0,
            known_closed_count=0,
            unresolved_position_count=0,
            limitations=tuple(limitations),
        )

    entries: list[PositionEvidenceEntry] = []
    for key, key_events in _group_by_position(visible).items():
        symbol = key_events[0].instrument_symbol
        try:
            position = _fold_one_key(key_events, effective_as_of)
        except LedgerRejectionError as failure:
            # The evidence recorded by K does not fold. Whether it would fold
            # once more evidence is recorded is UNKNOWABLE AT K, and answering
            # it would mean reading assertions recorded after K. So the refusal
            # is reported as unresolved, with M076's own reason for the filtered
            # attempt, and nothing is inferred.
            entries.append(
                PositionEvidenceEntry(
                    position_governance_id=key,
                    instrument_symbol=symbol,
                    status=KnownPositionStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE,
                    position=None,
                    rejection_reason=failure.reason.value,
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
    if any(e.status is KnownPositionStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE for e in ordered):
        limitations.append(
            "one or more positions have evidence that does not fold at this knowledge "
            "cutoff; from the evidence recorded by this cutoff alone it cannot be known "
            "whether that is temporary incompleteness -- typically a close or reduction "
            "whose opening was recorded later -- or underlying ledger incoherence. No "
            "state is reported for them, none is inferred, and the question is left open "
            "rather than settled with evidence recorded afterwards"
        )

    return OperatorEvidenceSnapshot(
        outcome=EvidenceSnapshotOutcome.EVIDENCE_SNAPSHOT_AVAILABLE,
        unassessable_reason=None,
        effective_as_of=effective_as_of,
        knowledge_as_of=knowledge_as_of,
        known_event_count=len(known),
        visible_event_count=len(visible),
        excluded_by_effective_cutoff=excluded_by_effective,
        known_open_count=sum(1 for e in ordered if e.status is KnownPositionStatus.KNOWN_OPEN),
        known_closed_count=sum(1 for e in ordered if e.status is KnownPositionStatus.KNOWN_CLOSED),
        unresolved_position_count=sum(
            1 for e in ordered if e.status is KnownPositionStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE
        ),
        entries=ordered,
        limitations=tuple(limitations),
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

    `events` is read exactly once, by `events_known_by`. Everything after that
    point sees only the survivors, so two ledgers agreeing on `recorded_at <= K`
    produce byte-identical snapshots however much they differ afterwards.
    """
    for label, moment in (
        ("effective_as_of", effective_as_of),
        ("knowledge_as_of", knowledge_as_of),
    ):
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware; a naive datetime has no instant")

    if not ledger_available:
        return OperatorEvidenceSnapshot(
            outcome=EvidenceSnapshotOutcome.NOT_ASSESSABLE,
            unassessable_reason=EvidenceUnassessableReason.LEDGER_UNAVAILABLE,
            effective_as_of=effective_as_of,
            knowledge_as_of=knowledge_as_of,
            known_event_count=0,
            visible_event_count=0,
            excluded_by_effective_cutoff=0,
            known_open_count=0,
            known_closed_count=0,
            unresolved_position_count=0,
            limitations=(
                "the operator position ledger could not be read; the snapshot is withheld "
                "rather than presented as if nothing had been recorded",
            ),
        )

    return _snapshot_from_known_evidence(
        known=events_known_by(events, knowledge_as_of),
        effective_as_of=effective_as_of,
        knowledge_as_of=knowledge_as_of,
    )
