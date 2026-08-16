"""MILESTONE-082 -- Operator Event Receipt Attestation.

WHAT THIS EXISTS TO FIX. M079's own frozen docstring admits that `recorded_at`
"is an operator-supplied field, not a system-assigned immutable" one. Measured
against real PostgreSQL, an ordinary permitted caller can persist an M076 event
with `recorded_at` of last year, next year, 1999, 2999, or before its own
`event_timestamp` -- all five persist, and the table carries no
database-generated column at all. So M079/M080/M081 are sound GIVEN
`recorded_at`, but `recorded_at` is not an independent knowledge authority.

WHAT A RECEIPT ASSERTS, AND ONLY THIS:

    the platform's persistence boundary READ THIS EVENT BACK AS ALREADY
    DURABLY COMMITTED, at `system_received_at`, measured by the application
    host clock of the attesting process.

WHY THE TWO-PHASE MODEL IS THE WHOLE POINT. A receipt timestamp assigned INSIDE
the ingesting transaction leaks knowledge, and this was proved by execution, not
argued: a transaction assigned its timestamp, paused, and a cutoff K was chosen
during the pause while the row was invisible to every reader. After commit, a
historical query `assigned_at <= K` returned the row -- the same class of defect
M079 exists to prevent.

Taking the instant in a SECOND transaction, after the event has committed and
been read back, inverts it:

    commit_time(event)  <  system_received_at(receipt)

    therefore   system_received_at <= W   IMPLIES   durably committed by W

The converse does NOT hold, and that asymmetry is the design. An event committed
just before W but attested just after W is EXCLUDED. M082 may UNDERSTATE what
was known; it can never OVERSTATE it. A false negative is a safe direction for a
knowledge claim; a false positive is the leak.

WHAT IS DELIBERATELY NOT CLAIMED. Not the commit time (PostgreSQL's
`track_commit_timestamp` is off and `pg_xact_commit_timestamp` errors here, so
commit-time authority is unavailable and is not faked). Not wall-clock truth --
the host clock can be wrong, adjusted, or moved backward, so this says
SYSTEM-ASSIGNED, never "true time". No ordering authority: a database sequence
was rejected because two connections proved assignment order is NOT commit
order, and a rollback proved its gaps do not mean missing receipts.

LEGACY EVENTS ARE NEVER BACKFILLED. A receipt is never manufactured from
`recorded_at`, `event_timestamp` or a migration time. An event without a receipt
reports NO_SYSTEM_RECEIPT_EVIDENCE and remains a perfectly valid M076 operator
assertion that simply carries no M082 authority.

M079, M080 and M081 are untouched and do NOT consume this authority. That would
change the meaning of every figure they emit and requires its own milestone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
)

__all__ = [
    "ATTESTED_EVIDENCE_BANNER",
    "AttestedEvidenceReport",
    "AttestedEvidenceStatus",
    "AttestedEventEntry",
    "OperatorEventReceipt",
    "attested_known_by",
    "build_attested_evidence_report",
]


class AttestedEvidenceStatus(StrEnum):
    """What the receipt evidence supports for one event at a cutoff."""

    ATTESTED = "ATTESTED"
    ATTESTED_AFTER_CUTOFF = "ATTESTED_AFTER_CUTOFF"
    NO_SYSTEM_RECEIPT_EVIDENCE = "NO_SYSTEM_RECEIPT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class OperatorEventReceipt:
    """One system attestation that an M076 event was already durably committed.

    `system_received_at` is an UPPER BOUND WITNESS on the event's commit time,
    never the commit time itself.
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
        # A naive datetime has no instant, so it cannot witness anything.
        if self.system_received_at.tzinfo is None or self.system_received_at.utcoffset() is None:
            raise ValueError(
                "system_received_at must be timezone-aware; a naive datetime has no instant"
            )


ATTESTED_EVIDENCE_BANNER = (
    "SYSTEM-RECEIPT-ATTESTED OPERATOR EVIDENCE: which operator-asserted events "
    "the platform's persistence boundary had READ BACK AS ALREADY DURABLY "
    "COMMITTED by the attestation cutoff. "
    "A receipt asserts ONLY that: the event was observed committed at a "
    "SYSTEM-ASSIGNED instant taken from the application host clock AFTER the "
    "event was read back. "
    "It does NOT assert the event's COMMIT TIME, which is not available here "
    "and is not claimed. "
    "It does NOT assert true wall-clock time: the host clock can be wrong, "
    "adjusted or moved backward, so this is SYSTEM-ASSIGNED, never actual time. "
    "It does NOT assert that the operator's assertion is true, that recorded_at "
    "is honest, that any trade occurred, or that any price was paid. "
    "The guarantee runs in ONE DIRECTION ONLY: attested at or before the cutoff "
    "IMPLIES durably committed by the cutoff. The converse does NOT hold, so an "
    "event committed before the cutoff but attested after it is EXCLUDED here. "
    "This report may therefore UNDERSTATE what the platform knew, and can never "
    "OVERSTATE it. "
    "Events with NO receipt are NOT attested by M082 and carry no M082 "
    "authority; they remain valid M076 operator assertions, and their absence "
    "of a receipt is NEVER filled in from recorded_at, event_timestamp or any "
    "other guess. "
    "NO ordering authority is emitted: a database sequence would be assignment "
    "order, not commit order. "
    "This report does NOT change, wrap or strengthen M079, M080 or M081, which "
    "continue to use the operator-supplied recorded_at exactly as frozen. "
    "Nothing attested after the cutoff influences any figure below."
)


@dataclass(frozen=True, slots=True)
class AttestedEventEntry:
    """One M076 event and what the receipt evidence supports for it."""

    event_governance_id: str
    position_governance_id: str
    instrument_symbol: str
    status: AttestedEvidenceStatus
    system_received_at: datetime | None
    attested_by: str | None


@dataclass(frozen=True, slots=True)
class AttestedEvidenceReport:
    """The attested-evidence snapshot at one cutoff."""

    attested_as_of: datetime
    attested_count: int
    attested_after_cutoff_count: int
    unattested_count: int
    entries: tuple[AttestedEventEntry, ...]
    limitations: tuple[str, ...]


def attested_known_by(
    events: tuple[OperatorAssertedPositionEvent, ...],
    receipts: tuple[OperatorEventReceipt, ...],
    attested_as_of: datetime,
) -> tuple[OperatorAssertedPositionEvent, ...]:
    """The events a receipt proves were durably committed by `attested_as_of`.

    This is M082's analogue of M079's `events_known_by`, and it is deliberately
    a SEPARATE function with a SEPARATE authority. M079 filters the
    operator-supplied `recorded_at`; this filters the system-assigned
    `system_received_at`. Neither is modified by the other.

    `recorded_at` is never read here.
    """
    if attested_as_of.tzinfo is None or attested_as_of.utcoffset() is None:
        raise ValueError("attested_as_of must be timezone-aware; a naive datetime has no instant")

    attested = {
        receipt.event_governance_id
        for receipt in receipts
        if receipt.system_received_at <= attested_as_of
    }
    return tuple(event for event in events if event.governance_id in attested)


_LIMITATIONS = (
    "limitation: a receipt is an UPPER BOUND WITNESS on the event's commit "
    "time, not the commit time. It says the event had ALREADY committed when "
    "the instant was taken; it does not say when it committed",
    "limitation: the guarantee is ONE-DIRECTIONAL. Attested at or before the "
    "cutoff implies durably committed by the cutoff; the converse does not "
    "hold, so this report may UNDERSTATE what was known and can never OVERSTATE "
    "it",
    "limitation: the instant comes from the APPLICATION HOST CLOCK of the "
    "attesting process. That clock can be wrong, can be adjusted, and can move "
    "backward. M082 claims SYSTEM-ASSIGNED time, never true or actual time, and "
    "makes no cryptographic or monotonicity claim",
    "limitation: PostgreSQL commit timestamps are NOT used. "
    "track_commit_timestamp is an optional, off-by-default, restart-required "
    "server setting the platform does not control, so commit-time authority is "
    "unavailable here and is not claimed",
    "limitation: NO ordering authority is emitted. A database sequence is "
    "assignment order, not commit order -- two connections proved a transaction "
    "taking the earlier sequence can commit later -- and its gaps do not mean "
    "missing receipts. Ordering here is by (system_received_at, "
    "event_governance_id) for determinism only",
    "limitation: events with NO receipt are reported as "
    "NO_SYSTEM_RECEIPT_EVIDENCE. That absence is NEVER filled in from "
    "recorded_at, event_timestamp, a migration time or any other guess. Such an "
    "event remains a valid M076 operator assertion carrying no M082 authority",
    "limitation: the M076 recording path is unchanged and still reachable, so "
    "M082 does NOT claim that all events carry receipt authority. Only events "
    "possessing a receipt are eligible for M082-authoritative analysis",
    "limitation: a crash between the event's commit and its attestation leaves "
    "the event permanently unattested. That honest absence is preferred to a "
    "fabricated instant, and a later reconciliation may only assign a LATER "
    "true instant, never a guessed historical one",
    "limitation: M079, M080 and M081 are untouched and do NOT consume this "
    "authority. They continue to filter the operator-supplied recorded_at "
    "exactly as frozen. Adopting receipt authority downstream would change the "
    "meaning of every figure they emit and requires its own milestone",
    "limitation: this report emits NO monetary value, NO ratio, NO aggregate "
    "and NO performance figure of any kind",
)


def build_attested_evidence_report(
    *,
    events: tuple[OperatorAssertedPositionEvent, ...],
    receipts: tuple[OperatorEventReceipt, ...],
    attested_as_of: datetime,
) -> AttestedEvidenceReport:
    """Build the attested-evidence snapshot at `attested_as_of`."""
    if attested_as_of.tzinfo is None or attested_as_of.utcoffset() is None:
        raise ValueError("attested_as_of must be timezone-aware; a naive datetime has no instant")

    by_event = {receipt.event_governance_id: receipt for receipt in receipts}

    entries: list[AttestedEventEntry] = []
    for event in events:
        receipt = by_event.get(event.governance_id)
        # A receipt later than the cutoff must not leak its instant into the
        # snapshot: at this cutoff the platform did not yet hold it. Only the
        # ATTESTED branch carries the instant forward.
        status: AttestedEvidenceStatus
        received_at: datetime | None = None
        attested_by: str | None = None
        if receipt is None:
            status = AttestedEvidenceStatus.NO_SYSTEM_RECEIPT_EVIDENCE
        elif receipt.system_received_at <= attested_as_of:
            status = AttestedEvidenceStatus.ATTESTED
            received_at = receipt.system_received_at
            attested_by = receipt.attested_by
        else:
            status = AttestedEvidenceStatus.ATTESTED_AFTER_CUTOFF

        entries.append(
            AttestedEventEntry(
                event_governance_id=event.governance_id,
                position_governance_id=event.position_governance_id,
                instrument_symbol=event.instrument_symbol,
                status=status,
                system_received_at=received_at,
                attested_by=attested_by,
            )
        )

    ordered = tuple(
        sorted(
            entries,
            key=lambda e: (
                e.system_received_at is None,
                e.system_received_at or attested_as_of,
                e.event_governance_id,
            ),
        )
    )

    def count(status: AttestedEvidenceStatus) -> int:
        return sum(1 for entry in ordered if entry.status is status)

    return AttestedEvidenceReport(
        attested_as_of=attested_as_of,
        attested_count=count(AttestedEvidenceStatus.ATTESTED),
        attested_after_cutoff_count=count(AttestedEvidenceStatus.ATTESTED_AFTER_CUTOFF),
        unattested_count=count(AttestedEvidenceStatus.NO_SYSTEM_RECEIPT_EVIDENCE),
        entries=ordered,
        limitations=_LIMITATIONS,
    )
