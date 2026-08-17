"""MILESTONE-082 operator event receipt attestation schema.

ADDITIVE ONLY. No existing table is altered and NO ROW IS BACKFILLED.

The table is created EMPTY on purpose. M076 already holds events created before
M082, and manufacturing a receipt for them -- from `recorded_at`, from
`event_timestamp`, or from the migration's own run time -- would fabricate
knowledge history. Absence of a receipt is an honest state and stays absent.

`ON DELETE RESTRICT`, never CASCADE: M076 is append-only, but if a row were ever
removed the receipt evidence must not silently vanish with it.

TWO TRIGGERS, AND EACH ENFORCES EXACTLY ONE NARROW THING.

1. ROW-LEVEL UPDATE/DELETE IMMUTABILITY, under the installed trigger. That is
   the whole of it: TRUNCATE is a statement-level operation a row trigger does
   not intercept, and DROP TRIGGER, DROP TABLE and superuser mutation are all
   still possible. This is NOT absolute database immutability and must not be
   described as such.

2. PRIOR-COMMITTED-EVENT ENFORCEMENT (Owner review finding 4). Without it the
   foreign key alone could be satisfied by an event INSERTed earlier in the SAME
   transaction, so a direct SQL caller could fabricate a receipt for an event
   that had never committed -- and the report could not tell it apart from one
   produced by `attest()`. Reproduced before being fixed.

   The trigger asks whether the referenced event's `xmin` transaction is still
   IN PROGRESS. If the row is visible to us and its writer is still in progress,
   that writer can only be our own transaction or a subtransaction of it, since
   MVCC never shows another transaction's uncommitted rows. That test handles
   savepoints, nested savepoints and rollback-to-savepoint, which a simple
   `xmin = pg_current_xact_id()::xid` comparison does NOT -- a subtransaction
   gets its own, higher, xid. It also does not produce a false rejection when a
   CONCURRENT transaction with a HIGHER xid committed before we read, which a
   plain xid ordering comparison would.

   `pg_xact_status` RETURNING NULL -- its documented answer for a transaction
   too old to have status information -- is treated as not-in-progress and
   accepted: a live transaction always has its CLOG present, so "too old to
   know" can only mean "committed long ago".

   That is the ONLY unknown that is accepted. A CHECKER FAILURE is different and
   is NOT accepted: the status call is deliberately unguarded, so a future xid8,
   a failed conversion or a missing privilege PROPAGATES and the INSERT fails
   closed. Owner review finding 6 -- an earlier version caught EXCEPTION WHEN
   OTHERS here and turned every such failure into permission to insert.

WHAT THIS STILL DOES NOT ENFORCE, stated so no reader over-reads it: the
receipt's `system_received_at`, `attested_by` and `attester_version` are
UNAUTHENTICATED LABELS. A direct SQL caller with write access can insert a
receipt for an already-committed event carrying any label, any attester name and
any version, and the report cannot distinguish it from one `attest()` produced.

Revision ID: d9a2f5c81b73
Revises: b7e1c4a95d38
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d9a2f5c81b73"
down_revision: str | None = "b7e1c4a95d38"
branch_labels: None = None
depends_on: None = None

# FROZEN LITERAL, owner finding 16: the complete Python 3.13 str.strip()
# whitespace set, all 29 codepoints. A migration is history and must NOT import
# mutable application code, so this is written out rather than derived. A test
# asserts it still agrees with BLANK_CHARACTERS on every one of the 29.
#
# RAW strings: these escapes are for PostgreSQL's E'' parser, not Python's. A
# non-raw literal would have Python decode them first and hand PostgreSQL the
# actual control characters instead of the escape text.
_BLANK_SQL = (
    r"\x09\x0A\x0B\x0C\x0D\x1C"
    r"\x1D\x1E\x1F\x20\u0085\u00A0"
    r"\u1680\u2000\u2001\u2002\u2003\u2004"
    r"\u2005\u2006\u2007\u2008\u2009\u200A"
    r"\u2028\u2029\u202F\u205F\u3000"
)


def _not_blank(column: str) -> str:
    """The blank CHECK for one column, using the frozen 29-character set."""
    return f"btrim({column}, E'{_BLANK_SQL}') <> ''"


_TIMESTAMPTZ = sa.DateTime(timezone=True)

_IMMUTABILITY_FUNCTION = """
CREATE OR REPLACE FUNCTION public.operator_event_receipt_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'operator_event_receipt is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_IMMUTABILITY_TRIGGER = """
CREATE TRIGGER operator_event_receipt_immutable_trigger
BEFORE UPDATE OR DELETE ON public.operator_event_receipt
FOR EACH ROW EXECUTE FUNCTION public.operator_event_receipt_immutable()
"""

# Owner review finding 4. The FK alone accepts an event inserted earlier in the
# SAME transaction, because it is visible to that transaction. This refuses it.
_PRIOR_COMMIT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.operator_event_receipt_requires_prior_commit()
RETURNS trigger AS $$
DECLARE
    event_xmin xid;
    probe numeric;
    writer_status text;
BEGIN
    -- SCHEMA-QUALIFIED (owner review finding 8). This read was previously
    -- unqualified, so a caller could CREATE TEMP TABLE operator_position_event,
    -- COMMIT a decoy row into it, and the trigger would resolve pg_temp ahead of
    -- public. Executed by a role with rolsuper/rolcreatedb/rolcreaterole all
    -- false: the receipt inserted, and after commit the event and the receipt
    -- shared one xmin -- the same transaction the trigger exists to refuse.
    SELECT e.xmin INTO event_xmin
      FROM public.operator_position_event e
     WHERE e.governance_id = NEW.event_governance_id;

    IF NOT FOUND THEN
        -- No such event: the foreign key is the authority on that, not this.
        RETURN NEW;
    END IF;

    -- Promote the 32-bit xmin into the current xid8 epoch. A transaction that
    -- is still in progress is necessarily in the current epoch, so this is
    -- exact for the only case being tested.
    probe := (pg_catalog.pg_current_xact_id()::text::numeric
              - pg_catalog.pg_current_xact_id()::xid::text::numeric)
             + event_xmin::text::numeric;

    -- NO EXCEPTION HANDLER (owner review finding 6). An earlier version wrapped
    -- this call in EXCEPTION WHEN OTHERS and treated any failure as an unknown
    -- status, which was then ACCEPTED -- the enforcement FAILED OPEN. Executed
    -- demonstration: a role lacking EXECUTE on pg_xact_status raises
    -- "permission denied for function pg_xact_status", and the old handler
    -- converted that into an accept. Any error now PROPAGATES.
    writer_status := pg_catalog.pg_xact_status(probe::text::xid8);

    -- EXPLICIT ALLOWLIST (owner review, fail-closed hardening). The previous
    -- form refused only 'in progress' and 'aborted', so any future or unexpected
    -- non-NULL status value would have been ACCEPTED. Only two outcomes are
    -- permitted, and everything else is refused:
    --
    --   'committed' -> the event came from a prior transaction. Accept.
    --   NULL        -> pg_xact_status's documented answer for a transaction too
    --                  old to have status information. A live transaction always
    --                  has its CLOG, so this cannot be an in-progress writer.
    --                  Accept, under exactly that limitation and no wider one.
    --   anything else, including 'in progress' and 'aborted' -> REFUSE.
    IF writer_status IS NULL OR writer_status = 'committed' THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION
        'operator_event_receipt requires a PRIOR COMMITTED event: % was written '
        'by a transaction whose status is %, so no receipt can attest it',
        NEW.event_governance_id, writer_status;
END $$ LANGUAGE plpgsql
-- A pinned, minimal search_path: the function must not resolve anything through
-- a caller-controlled path. Every relation and function above is qualified as
-- well, so this is defence in depth rather than the only barrier.
SET search_path = pg_catalog, public
"""

_PRIOR_COMMIT_TRIGGER = """
CREATE TRIGGER operator_event_receipt_requires_prior_commit_trigger
BEFORE INSERT ON public.operator_event_receipt
FOR EACH ROW EXECUTE FUNCTION public.operator_event_receipt_requires_prior_commit()
"""


def upgrade() -> None:
    op.create_table(
        "operator_event_receipt",
        sa.Column("receipt_governance_id", sa.String(length=64), primary_key=True),
        # Exactly one receipt per event. The UNIQUE constraint is what makes
        # retry idempotent structurally rather than by convention, and what
        # resolves two concurrent attesters for the same event.
        sa.Column("event_governance_id", sa.String(length=64), nullable=False),
        # The attestation LABEL, assigned by the application host clock after
        # the event was read back as committed.
        #
        # RETRACTED (Owner review finding 2): this comment previously called it
        # an "UPPER BOUND WITNESS on the event's commit time". It is not. The
        # host clock can be wrong, adjusted or moved BACKWARD, and an executed
        # backward-clock attack produces a label preceding the event's real
        # commit. This column is a system-assigned label and bounds nothing.
        sa.Column("system_received_at", _TIMESTAMPTZ, nullable=False),
        # Recorded strings describing the pathway. Neither is an authority in
        # itself; both exist so a reader can tell what produced the receipt.
        sa.Column("attested_by", sa.String(length=64), nullable=False),
        sa.Column("attester_version", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("event_governance_id", name="uq_operator_event_receipt_event"),
        # Owner review finding 9, CORRECTED BY FINDING 12. The first version used
        # btrim(col) <> '', whose default strips ONLY ordinary spaces: tab,
        # newline, CR, formfeed, vertical tab and NBSP all passed while Python
        # called them blank, so a tab-only attested_by persisted and then crashed
        # the report. The character set below is the SAME ENUMERATED SET as
        # `BLANK_CHARACTERS` in decision_candidate/operator_event_receipt.py, and
        # a test asserts the two agree character by character.
        #
        # \x0B, NOT \v: PostgreSQL's E'' syntax has no \v escape, so E'\v'
        # yields the LETTER v (ascii 118), not vertical tab (11). Written that
        # way, btrim('valve', set) returned 'alve' -- the constraint would have
        # stripped a real letter out of legitimate identifiers. Caught only by
        # running the per-character test over all four columns.
        #
        # OWNER FINDING 16. The set is now the COMPLETE Python 3.13 str.strip()
        # whitespace set, all 29 codepoints, written as a FROZEN LITERAL. An
        # earlier version used only seven characters, which made the two sides
        # agree by WEAKENING Python rather than by mirroring it.
        #
        # The literal is frozen here on purpose: a migration is history and must
        # not import mutable application code. A test asserts this installed
        # constraint and BLANK_CHARACTERS still agree on all 29.
        sa.CheckConstraint(
            _not_blank("receipt_governance_id"),
            name="ck_operator_event_receipt_receipt_id_present",
        ),
        sa.CheckConstraint(
            _not_blank("event_governance_id"),
            name="ck_operator_event_receipt_event_id_present",
        ),
        sa.CheckConstraint(
            _not_blank("attested_by"),
            name="ck_operator_event_receipt_attested_by_present",
        ),
        sa.CheckConstraint(
            _not_blank("attester_version"),
            name="ck_operator_event_receipt_attester_version_present",
        ),
        sa.ForeignKeyConstraint(
            ["event_governance_id"],
            ["operator_position_event.governance_id"],
            name="fk_operator_event_receipt_event",
            ondelete="RESTRICT",
        ),
    )
    # The single query path: everything attested by a cutoff.
    op.create_index(
        "ix_operator_event_receipt_received_at",
        "operator_event_receipt",
        ["system_received_at"],
    )
    op.execute(_IMMUTABILITY_FUNCTION)
    op.execute(_IMMUTABILITY_TRIGGER)
    op.execute(_PRIOR_COMMIT_FUNCTION)
    op.execute(_PRIOR_COMMIT_TRIGGER)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS operator_event_receipt_requires_prior_commit_trigger "
        "ON public.operator_event_receipt"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS operator_event_receipt_immutable_trigger "
        "ON public.operator_event_receipt"
    )
    op.drop_index("ix_operator_event_receipt_received_at", table_name="operator_event_receipt")
    op.drop_table("operator_event_receipt")
    op.execute("DROP FUNCTION IF EXISTS public.operator_event_receipt_immutable()")
    op.execute("DROP FUNCTION IF EXISTS public.operator_event_receipt_requires_prior_commit()")
