"""MILESTONE-082 receipt attestation persistence.

APPEND-ONLY, in two layers, each narrower than the phrase suggests:

  * this class exposes `attest` and read methods only -- there is no UPDATE and
    no DELETE code path anywhere in it;
  * a BEFORE UPDATE OR DELETE trigger refuses direct SQL too. That is ROW-LEVEL
    UPDATE/DELETE IMMUTABILITY UNDER THE INSTALLED TRIGGER, and nothing more.
    TRUNCATE is a statement-level operation a row trigger does not intercept,
    and DROP TRIGGER, DROP TABLE and superuser mutation all remain possible.
    Calling this "database-enforced immutability" without that qualification
    over-reads it, and the earlier wording here did exactly that.

PRIOR-COMMITTED-EVENT ENFORCEMENT (owner review finding 4). A BEFORE INSERT
trigger refuses a receipt whose referenced event was written by the CURRENT
transaction. Before it existed, a direct SQL caller could insert an event and a
matching receipt in ONE transaction -- the foreign key was satisfied because the
event was visible to that transaction -- so a persisted row proved the causal
claim only for rows this class had produced. It now holds for every row.

What is STILL not enforced: `system_received_at`, `attested_by` and
`attester_version` are unauthenticated labels. A direct SQL caller with write
access can forge all three for an already-committed event.

THE TWO-PHASE MODEL IS THE POINT. `attest` runs in its OWN transaction, AFTER
the event's transaction has committed, and it READS THE EVENT BACK before
creating the receipt. That read-back, plus program order, is what the receipt
proves:

    the event was already durably committed WHEN THIS RECEIPT WAS CREATED.

That claim is CAUSAL and holds regardless of any clock.

RETRACTED BY OWNER REVIEW (finding 2). This module previously said the ordering
made `system_received_at <= W` IMPLY the event was durably committed by W. It
does not. `system_received_at` is a LABEL from `_clock`, and a backward or
misconfigured host clock can produce a label earlier than the read-back it
follows -- see `test_a_backward_clock_breaks_the_wall_clock_implication`. The
label is system-assigned; it is not a proven bound.

Assigning the instant inside the ingesting transaction was separately PROVED to
leak: a paused transaction's pre-commit timestamp made an invisible row appear
"available" at a cutoff chosen during the pause. The second transaction is what
removes that, and it remains mandatory.

THE CLOCK IS INJECTED so the backward-clock attack the Owner mandated can be
executed rather than argued. Production wiring passes nothing and gets
`datetime.now(UTC)`.

EVERY RELATION IS SCHEMA-QUALIFIED (owner review finding 8). An unqualified name
resolves through the caller's `search_path`, and `pg_temp` precedes `public` in
the default one. A non-superuser proved the consequence against the prior-commit
trigger: a committed decoy row in a temp relation of the same name let a receipt
attest an event that was still in progress in `public`. These statements were
equally exposed, so they are qualified too.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from empirical_platform.decision_candidate.operator_event_receipt import OperatorEventReceipt
from empirical_platform.shared.errors.foundation import FoundationError
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

__all__ = ["PostgresOperatorEventReceiptRepository"]

ATTESTER_VERSION = "M082.1"

_EVENT_UNIQUE_CONSTRAINT = "uq_operator_event_receipt_event"


def _host_clock() -> datetime:
    """The production clock. Untrusted by design -- see the module docstring."""
    return datetime.now(UTC)


class UnknownOperatorEventError(RuntimeError):
    """Raised when attestation is asked for an event that is not committed.

    Deliberately NOT a soft verdict. An attestation for an event the platform
    cannot read back would be a receipt for something that may not exist, which
    is precisely the fabrication this milestone refuses.
    """


class PostgresOperatorEventReceiptRepository:
    """PostgreSQL-backed append-only receipt store."""

    __slots__ = ("_clock", "_service")

    def __init__(
        self,
        service: PostgresPersistenceService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service
        self._clock = clock if clock is not None else _host_clock

    def attest(
        self,
        *,
        receipt_governance_id: str,
        event_governance_id: str,
        attested_by: str,
    ) -> OperatorEventReceipt:
        """Attest that `event_governance_id` was read back as already committed.

        Idempotent BY EVENT: if a receipt already exists this returns it
        unchanged rather than creating a second authority. That is enforced by
        the UNIQUE constraint, not by a check-then-act race.
        """
        existing = self.get_for_event(event_governance_id)
        if existing is not None:
            return existing

        with self._service.unit_of_work() as work:
            # PHASE 2 READ-BACK. This runs in a transaction of its own, so it
            # can only observe the event if the event's transaction has already
            # COMMITTED. Everything the receipt claims rests on this read.
            rows = work.execute(
                "SELECT governance_id FROM public.operator_position_event "
                "WHERE governance_id = :gid",
                {"gid": event_governance_id},
            )
            if not list(rows):
                raise UnknownOperatorEventError(
                    f"no committed operator position event with governance_id "
                    f"{event_governance_id!r}; refusing to attest"
                )

            # The label is taken HERE, after the read-back. The ORDERING of the
            # two operations is the causal claim. The VALUE is only a label:
            # `_clock` is not trusted to be correct, monotonic, or even
            # forward-moving, and the artifact no longer claims it is.
            system_received_at = self._clock()
            if system_received_at.tzinfo is None or system_received_at.utcoffset() is None:
                raise ValueError("clock returned a naive datetime; an instant needs an offset")

            receipt = OperatorEventReceipt(
                receipt_governance_id=receipt_governance_id,
                event_governance_id=event_governance_id,
                system_received_at=system_received_at,
                attested_by=attested_by,
                attester_version=ATTESTER_VERSION,
            )
            try:
                work.execute(
                    "INSERT INTO public.operator_event_receipt "
                    "(receipt_governance_id, event_governance_id, system_received_at, "
                    "attested_by, attester_version) VALUES "
                    "(:receipt_governance_id, :event_governance_id, :system_received_at, "
                    ":attested_by, :attester_version)",
                    {
                        "receipt_governance_id": receipt.receipt_governance_id,
                        "event_governance_id": receipt.event_governance_id,
                        "system_received_at": receipt.system_received_at,
                        "attested_by": receipt.attested_by,
                        "attester_version": receipt.attester_version,
                    },
                )
            except FoundationError as exc:
                # Two concurrent attesters for one event: the database decides.
                # The loser reports the winner's receipt, not a fault.
                #
                # IMPLEMENTATION REVIEW R01, found by executing four concurrent
                # attesters. The first version called `get_for_event` HERE,
                # while still inside this unit of work, which raised "Nested
                # persistence units of work are not supported" -- so the losers
                # crashed instead of reporting the winner, which is exactly the
                # case this branch exists to handle gracefully. The conflict is
                # now only DETECTED inside the transaction; the winner is read
                # after it has closed.
                if unique_violation_constraint_name(exc) != _EVENT_UNIQUE_CONSTRAINT:
                    raise
                conflicted = True
            else:
                conflicted = False

        if conflicted:
            winner = self.get_for_event(event_governance_id)
            if winner is None:  # pragma: no cover - the row must exist to conflict
                raise RuntimeError(
                    f"receipt for {event_governance_id!r} conflicted but cannot be read back"
                )
            return winner
        return receipt

    def get_for_event(self, event_governance_id: str) -> OperatorEventReceipt | None:
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    "SELECT receipt_governance_id, event_governance_id, system_received_at, "
                    "attested_by, attester_version FROM public.operator_event_receipt "
                    "WHERE event_governance_id = :gid",
                    {"gid": event_governance_id},
                )
            )
        if not rows:
            return None
        return _row_to_receipt(rows[0])

    def list_labelled_by(self, receipt_label_cutoff: datetime) -> tuple[OperatorEventReceipt, ...]:
        """Only receipts whose label is at or before the cutoff.

        THE CUTOFF IS APPLIED IN SQL (owner review finding 9). `list_all` +
        domain filtering was structurally sound only INSIDE the pure builder,
        after every current row had already been materialised into a domain
        object. That is where it broke: a receipt labelled 2099 carrying a blank
        `attested_by` raised `ValueError` while a 2027 report was being built,
        so a row the artifact must not be able to see decided whether the
        artifact existed at all. Rows beyond the cutoff are now never fetched.
        """
        if receipt_label_cutoff.tzinfo is None or receipt_label_cutoff.utcoffset() is None:
            raise ValueError(
                "receipt_label_cutoff must be timezone-aware; a naive datetime has no instant"
            )
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT receipt_governance_id, event_governance_id, system_received_at, "
                "attested_by, attester_version FROM public.operator_event_receipt "
                "WHERE system_received_at <= :cutoff "
                "ORDER BY system_received_at, event_governance_id",
                {"cutoff": receipt_label_cutoff},
            )
            return tuple(_row_to_receipt(row) for row in rows)

    def list_all(self) -> tuple[OperatorEventReceipt, ...]:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT receipt_governance_id, event_governance_id, system_received_at, "
                "attested_by, attester_version FROM public.operator_event_receipt "
                "ORDER BY system_received_at, event_governance_id"
            )
            return tuple(_row_to_receipt(row) for row in rows)


def _row_to_receipt(row: Mapping[str, Any]) -> OperatorEventReceipt:
    return OperatorEventReceipt(
        receipt_governance_id=str(row["receipt_governance_id"]),
        event_governance_id=str(row["event_governance_id"]),
        system_received_at=row["system_received_at"],
        attested_by=str(row["attested_by"]),
        attester_version=str(row["attester_version"]),
    )
