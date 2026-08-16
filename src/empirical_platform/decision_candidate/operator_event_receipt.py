"""MILESTONE-082 -- Operator Event Receipt Attestation.

WHAT THIS EXISTS TO FIX. M079's own frozen docstring admits that `recorded_at`
"is an operator-supplied field, not a system-assigned immutable" one. Measured
against real PostgreSQL, an ordinary permitted caller can persist an M076 event
with `recorded_at` of last year, next year, 1999, 2999, or before its own
`event_timestamp` -- all five persist, and the table carries no
database-generated column at all. So M079/M080/M081 are sound GIVEN
`recorded_at`, but `recorded_at` is not an independent knowledge authority.

WHAT A RECEIPT ASSERTS, AND ONLY THIS -- A CAUSAL FACT:

    the attestation process READ THIS EVENT BACK from committed persistence,
    and only THEN created this receipt.

That ordering is guaranteed by program order plus PostgreSQL transaction
visibility: `attest` runs in a transaction of its own, so it can observe the
event only if the event's transaction has already committed. It holds no matter
what any clock says.

`system_received_at` is a SYSTEM-ASSIGNED LABEL recorded alongside that causal
fact. It is NOT a proven bound on the event's commit time -- see the retraction
below.

============================================================================
RETRACTED BY OWNER REVIEW (M082 owner review, finding 2)
============================================================================

An earlier version of this module claimed:

    commit_time(event) < system_received_at(receipt)
    therefore system_received_at <= W  IMPLIES  durably committed by W

and that M082 "can never OVERSTATE" what was known by W. That claim is
**RETRACTED**. It was never proved, and it is false whenever the application
host clock is wrong or moves backward -- a possibility this module's own
limitations already admitted, so the two statements could not both be true.

Executed counter-example: an event commits, is read back successfully, and the
attesting clock then returns an instant EARLIER than the read-back. The receipt
carries that earlier label. A historical query at a W between the two reports
the event as attested by W, although at real wall-clock W the event had not
committed. Causal ordering is not numerical wall-clock ordering when the clock
can jump.

What survives is the causal claim, which does not depend on the clock at all.

WHAT IS THEREFORE NOT CLAIMED. Not the commit time (PostgreSQL's
`track_commit_timestamp` is off and `pg_xact_commit_timestamp` errors here, so
commit-time authority is unavailable and is not faked). Not an upper bound on
the commit time. Not wall-clock truth. Not that comparing the label to an
arbitrary historical instant W proves durable availability at W.

CONSEQUENCE, STATED PLAINLY: **M082 does NOT replace M079's `recorded_at`
firewall.** It supplies a smaller true primitive -- causal receipt attestation
-- instead of a larger false one. Binding an evaluation to receipt identities or
an explicitly persisted receipt set, rather than reconstructing wall-clock
availability afterwards, is a separate future milestone and is not started.

WHY THE TWO-PHASE MODEL IS STILL THE POINT. A receipt written INSIDE the
ingesting transaction has no causal claim at all, and this was proved by
execution: a transaction assigned its timestamp, paused, and a cutoff K was
chosen during the pause while the row was invisible to every reader. After
commit, a historical query `assigned_at <= K` returned the row. The second
transaction plus read-back is what makes the causal claim true.

THE SNAPSHOT IS RECEIPT-CUTOFF ONLY (M082 owner review, finding 1). The
historical artifact is built FROM RECEIPTS whose label is at or before the
cutoff, never from the current ledger inventory. A receipt labelled after the
cutoff, and an event that has no such receipt, are structurally unreachable: no
entry, no count and no ordering position can be derived from them. An earlier
version built the artifact from `ledger.list_all()` and emitted
ATTESTED_AFTER_CUTOFF, NO_SYSTEM_RECEIPT_EVIDENCE and
`attested_after_cutoff_count`; that made the output depend on rows created after
the cutoff, and it is **RETRACTED**. The snapshot deliberately does NOT know how
much evidence it excluded, and no replacement count is offered.

LEGACY EVENTS ARE NEVER BACKFILLED. A receipt is never manufactured from
`recorded_at`, `event_timestamp` or a migration time. An event without a receipt
simply does not appear, and remains a perfectly valid M076 operator assertion
that carries no M082 authority.

M079, M080 and M081 are untouched and do NOT consume this authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
)

__all__ = [
    "ATTESTED_EVIDENCE_BANNER",
    "AttestedEvidenceReport",
    "AttestedEventEntry",
    "MissingAttestedEventError",
    "OperatorEventReceipt",
    "build_attested_evidence_report",
    "events_with_receipt_labelled_by",
]


class MissingAttestedEventError(RuntimeError):
    """A receipt references an event the caller did not supply.

    The foreign key makes this unreachable in the PostgreSQL adapter. It is
    raised rather than silently skipped because a missing referent is an
    infrastructure inconsistency, not an absence of evidence, and quietly
    dropping the entry would understate the snapshot for the wrong reason.
    """


@dataclass(frozen=True, slots=True)
class OperatorEventReceipt:
    """One system receipt attesting an M076 event was read back as committed.

    `system_received_at` is a SYSTEM-ASSIGNED LABEL taken from the application
    host clock after the read-back. It is NOT a proven upper bound on the
    event's commit time; see the module docstring's retraction.
    """

    receipt_governance_id: str
    event_governance_id: str
    system_received_at: datetime
    attested_by: str
    attester_version: str

    def __post_init__(self) -> None:
        for label, value in (
            ("receipt_governance_id", self.receipt_governance_id),
            ("event_governance_id", self.event_governance_id),
            ("attested_by", self.attested_by),
            ("attester_version", self.attester_version),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        # A naive datetime has no instant, so it cannot label anything.
        if self.system_received_at.tzinfo is None or self.system_received_at.utcoffset() is None:
            raise ValueError(
                "system_received_at must be timezone-aware; a naive datetime has no instant"
            )


ATTESTED_EVIDENCE_BANNER = (
    "SYSTEM-RECEIPT-ATTESTED OPERATOR EVIDENCE: the operator-asserted events "
    "that carry an M082 receipt whose SYSTEM-ASSIGNED LABEL is at or before the "
    "cutoff below. "
    "What a receipt PROVES is CAUSAL and clock-independent: the attestation "
    "process read the event back from COMMITTED persistence, and only then "
    "created the receipt. "
    "What it does NOT prove is any wall-clock fact. system_received_at is a "
    "LABEL taken from the application host clock, which can be wrong, adjusted "
    "or moved BACKWARD, so a label at or before the cutoff DOES NOT prove the "
    "event was durably committed by that cutoff in real time. "
    "RETRACTED: an earlier version of this report claimed the label was an "
    "upper bound on commit time and that the report could never OVERSTATE what "
    "was known. Both claims are withdrawn -- they are false under a backward "
    "clock, which is executed and recorded. "
    "This report therefore does NOT replace M079's recorded_at firewall, and "
    "M079, M080 and M081 continue to use the operator-supplied recorded_at "
    "exactly as frozen. "
    "It does NOT assert the event's COMMIT TIME, which is not available here "
    "and is not claimed. "
    "It does NOT assert that the operator's assertion is true, that recorded_at "
    "is honest, that any trade occurred, or that any price was paid. "
    "This is a RECEIPT-CUTOFF SNAPSHOT: it is built ONLY from receipts labelled "
    "at or before the cutoff. Receipts labelled after the cutoff, and events "
    "with no such receipt, are structurally absent -- they contribute no entry, "
    "no count and no ordering. "
    "Consequently this report CANNOT tell you how much evidence it excluded, "
    "and it deliberately offers no count of what it cannot see. "
    "An event that does not appear is NOT attested by M082 and carries no M082 "
    "authority; it remains a valid M076 operator assertion, and its absence is "
    "NEVER filled in from recorded_at, event_timestamp or any other guess. "
    "NO ordering authority is emitted: a database sequence would be assignment "
    "order, not commit order."
)


@dataclass(frozen=True, slots=True)
class AttestedEventEntry:
    """One M076 event whose receipt label is at or before the cutoff.

    Every field here is derivable from the receipt and from the append-only,
    immutable M076 event row the receipt proves was already committed. No field
    can carry information created after the cutoff.
    """

    event_governance_id: str
    position_governance_id: str
    instrument_symbol: str
    system_received_at: datetime
    attested_by: str


@dataclass(frozen=True, slots=True)
class AttestedEvidenceReport:
    """The receipt-cutoff snapshot.

    There is DELIBERATELY no `attested_after_cutoff_count` and no
    `unattested_count`. Both were future-aware: they counted rows that exist
    only in the present-day store. See the module docstring's retraction.
    """

    receipt_label_cutoff: datetime
    attested_count: int
    entries: tuple[AttestedEventEntry, ...]
    limitations: tuple[str, ...]


def events_with_receipt_labelled_by(
    events: tuple[OperatorAssertedPositionEvent, ...],
    receipts: tuple[OperatorEventReceipt, ...],
    receipt_label_cutoff: datetime,
) -> tuple[OperatorAssertedPositionEvent, ...]:
    """The events carrying a receipt labelled at or before the cutoff.

    RENAMED from `attested_known_by` by Owner review finding 2. The old name
    asserted KNOWLEDGE at a time, which the label cannot support. This function
    filters a system-assigned label; it does not establish what was knowable.

    `recorded_at` is never read here -- this authority is separate from M079's,
    and neither is modified by the other.
    """
    if receipt_label_cutoff.tzinfo is None or receipt_label_cutoff.utcoffset() is None:
        raise ValueError(
            "receipt_label_cutoff must be timezone-aware; a naive datetime has no instant"
        )

    labelled = {
        receipt.event_governance_id
        for receipt in receipts
        if receipt.system_received_at <= receipt_label_cutoff
    }
    return tuple(event for event in events if event.governance_id in labelled)


_LIMITATIONS = (
    "limitation: what a receipt PROVES is CAUSAL only -- the attestation "
    "process read the event back from committed persistence before creating "
    "the receipt. That holds regardless of any clock",
    "limitation: RETRACTED CLAIM. Earlier versions of this artifact said "
    "system_received_at was an UPPER BOUND on the event's commit time, and that "
    "the report could never OVERSTATE what was known. Both are withdrawn. The "
    "application host clock can be wrong, adjusted or moved BACKWARD, and an "
    "executed backward-clock attack produces a receipt labelled before the "
    "event's real commit chronology",
    "limitation: comparing the label to an arbitrary historical instant W does "
    "NOT prove the event was durably committed by W in real time. The cutoff "
    "here is a LABEL comparison, not a knowledge-time proof",
    "limitation: CONSEQUENTLY M082 does NOT replace M079's recorded_at "
    "firewall. M079, M080 and M081 continue to filter the operator-supplied "
    "recorded_at exactly as frozen, and adopting receipt authority downstream "
    "is a separate future milestone",
    "limitation: PostgreSQL commit timestamps are NOT used. "
    "track_commit_timestamp is an optional, off-by-default, restart-required "
    "server setting the platform does not control, so commit-time authority is "
    "unavailable here and is not claimed",
    "limitation: no monotonicity is enforced and no cryptographic claim is "
    "made. This is not a trusted timestamping service, and a sufficiently "
    "privileged actor can influence the clock that produces the label",
    "limitation: NO ordering authority is emitted. A database sequence is "
    "assignment order, not commit order -- two connections proved a transaction "
    "taking the earlier sequence can commit later -- and its gaps do not mean "
    "missing receipts. Ordering here is by (system_received_at, "
    "event_governance_id) for determinism only",
    "limitation: this is a RECEIPT-CUTOFF SNAPSHOT built ONLY from receipts "
    "labelled at or before the cutoff. Receipts labelled after it, and events "
    "with no such receipt, are structurally unreachable and contribute nothing",
    "limitation: this snapshot CANNOT report how much evidence it excluded. A "
    "count of what it cannot see would itself be future-aware, so none is "
    "offered",
    "limitation: an event absent from this snapshot is NOT attested by M082. "
    "That absence is NEVER filled in from recorded_at, event_timestamp, a "
    "migration time or any other guess. Such an event remains a valid M076 "
    "operator assertion carrying no M082 authority",
    "limitation: the M076 recording path is unchanged and still reachable, so "
    "M082 does NOT claim that all events carry receipt authority. Only events "
    "possessing a receipt are eligible for M082-authoritative analysis",
    "limitation: a crash between the event's commit and its attestation leaves "
    "the event permanently unattested. That honest absence is preferred to a "
    "fabricated instant, and a later reconciliation may only assign a LATER "
    "label, never a guessed historical one",
    "limitation: this report emits NO monetary value, NO ratio, NO aggregate "
    "and NO performance figure of any kind",
)


def build_attested_evidence_report(
    *,
    events: tuple[OperatorAssertedPositionEvent, ...],
    receipts: tuple[OperatorEventReceipt, ...],
    receipt_label_cutoff: datetime,
) -> AttestedEvidenceReport:
    """Build the receipt-cutoff snapshot.

    RECEIPTS ARE THE SPINE, not the ledger. Only receipts labelled at or before
    the cutoff are considered, and `events` is consulted solely to resolve the
    already-proved-committed detail of an event one of those receipts names. A
    later receipt, or an event with no qualifying receipt, cannot influence any
    entry, count or ordering position -- that is structural, not a filter
    applied afterwards.
    """
    if receipt_label_cutoff.tzinfo is None or receipt_label_cutoff.utcoffset() is None:
        raise ValueError(
            "receipt_label_cutoff must be timezone-aware; a naive datetime has no instant"
        )

    eligible = tuple(
        receipt for receipt in receipts if receipt.system_received_at <= receipt_label_cutoff
    )
    by_event_id = {event.governance_id: event for event in events}

    entries: list[AttestedEventEntry] = []
    for receipt in eligible:
        event = by_event_id.get(receipt.event_governance_id)
        if event is None:
            raise MissingAttestedEventError(
                f"receipt {receipt.receipt_governance_id!r} attests event "
                f"{receipt.event_governance_id!r}, which was not supplied"
            )
        entries.append(
            AttestedEventEntry(
                event_governance_id=event.governance_id,
                position_governance_id=event.position_governance_id,
                instrument_symbol=event.instrument_symbol,
                system_received_at=receipt.system_received_at,
                attested_by=receipt.attested_by,
            )
        )

    ordered = tuple(sorted(entries, key=lambda e: (e.system_received_at, e.event_governance_id)))

    return AttestedEvidenceReport(
        receipt_label_cutoff=receipt_label_cutoff,
        attested_count=len(ordered),
        entries=ordered,
        limitations=_LIMITATIONS,
    )
