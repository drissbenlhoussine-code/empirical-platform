"""MILESTONE-083 persisted receipt-set evaluation evidence watermark schema.

ADDITIVE ONLY. No M082 table, trigger, function, column or row is touched.
`operator_event_receipt` is read, never written, by anything in this file.

THE CLAIM, AND ONLY THIS. One persisted watermark row binds a stable watermark
governance identity to the EXACT set of `receipt_governance_id` values that
were visible to the schema-qualified capture query executed by the INSERT
statement that created it, under that statement's own transaction snapshot.
The set is stored once, in deterministic canonical (`COLLATE "C"`) order, and
never changes afterward. "Visible" means visible to THAT STATEMENT under ITS
transaction snapshot -- not globally visible to every reader, not commit-time,
not wall-clock, not an ordering or sequence authority. See
`external-review/MILESTONE-083/current-authority.json` for the closed,
machine-readable statement of what this does and does not prove.

WHY A TRIGGER, NOT THE CALLER. A caller-supplied membership list -- however it
is populated -- can omit an id, add a nonexistent id, or simply be wrong, and
nothing at the database boundary would notice. The BEFORE INSERT trigger below
throws away whatever `receipt_governance_ids` value the caller (application
code or a direct SQL statement) sent and REPLACES it, unconditionally, with
one query it runs itself against `public.operator_event_receipt`. A direct SQL
INSERT that never mentions the column at all works identically to one that
supplies a hostile array: both are overwritten the same way, because the
trigger does not read `NEW.receipt_governance_ids` before overwriting it.

CANONICAL ORDER. `array_agg(... ORDER BY receipt_governance_id COLLATE "C")`
pins byte-order lexical ordering explicitly, independent of the database's
default collation (this cluster happens to run `C.UTF-8`, but the watermark's
canonical order must not depend on that happening to be true). `receipt_
governance_id` is `operator_event_receipt`'s own primary key, so the source
column already carries no duplicates; canonicalization is stated as an
explicit property of the query regardless.

EMPTY SET. `array_agg` over zero rows is NULL, not an empty array, so the
capture query wraps it in `COALESCE(..., ARRAY[]::text[])`. The column is
`NOT NULL`: an empty receipt table produces an explicit `{}`, never a NULL
that a reader might mistake for "not yet captured".

STATEMENT-SNAPSHOT VISIBILITY, NOT PRIOR-COMMIT VISIBILITY. Unlike M082's
prior-commit trigger, this schema does NOT require the referenced receipts to
have committed in an earlier transaction. The capture query runs inside the
same transaction as the INSERT that fires it, under ordinary PostgreSQL
statement semantics: a statement always sees the effects of every earlier
statement in ITS OWN transaction, committed or not, in addition to whatever
committed before the transaction's snapshot was taken (under the default READ
COMMITTED isolation level, snapshot is retaken per statement). Concretely: a
receipt INSERTed earlier in the SAME transaction as the watermark capture IS
visible to the capture query and IS included in the set, even though it has
not committed yet. A receipt committed by ANOTHER transaction after the
capture statement's snapshot was taken is excluded. This is measured directly
in `tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py`
and must not be described as "prior-committed" -- that is M082's guarantee,
not this one.

IMMUTABILITY, THE SAME NARROW SHAPE AS M082. A BEFORE UPDATE OR DELETE row
trigger refuses both operations unconditionally. That is ROW-LEVEL
UPDATE/DELETE IMMUTABILITY UNDER THE INSTALLED TRIGGER ONLY: TRUNCATE is a
statement-level operation a row trigger does not intercept, and DROP TRIGGER,
DROP TABLE, disabling the trigger, and superuser mutation all remain possible.
This must not be described as absolute database immutability.

IDENTITY UNIQUENESS IS THE ONLY IDEMPOTENCY MECHANISM. `watermark_governance_id`
is the primary key. Two concurrent captures of the same id race on that
constraint; the database picks exactly one winner and the loser's INSERT fails
with a unique violation, which the repository (not this migration) turns into
"read back the winner". No row is ever partially written: a failed or
rolled-back INSERT leaves nothing, because the entire row -- including the
trigger-computed array -- is produced and validated inside one statement
inside one transaction.

BLANK IDENTITY. `watermark_governance_id` uses the identical frozen 29-
character Python 3.13 `str.strip()` blank set M082's migration froze locally,
reproduced here rather than imported, because a migration is history and must
not depend on mutable application code. A test asserts this literal still
agrees with `BLANK_CHARACTERS` in
`decision_candidate/evaluation_evidence_watermark.py`.

WHAT THIS DOES NOT ENFORCE, STATED SO NO READER OVER-READS IT. This schema
does not defend against DDL authority (DROP TABLE/TRIGGER/FUNCTION), a
superuser, `ALTER TABLE ... DISABLE TRIGGER`, TRUNCATE, or a replication path
that bypasses these triggers. It stores no timestamp, no label, no sequence,
and no "as of" field of any kind, and asserts no evaluation, ResearchSession,
DecisionCandidate or brief consumed this set -- that binding is explicitly out
of scope for MILESTONE-083 and belongs to a future evaluation-context
milestone, not started.

Revision ID: 9e4e647347ad
Revises: d9a2f5c81b73
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "9e4e647347ad"
down_revision: str | None = "d9a2f5c81b73"
branch_labels: None = None
depends_on: None = None

# FROZEN LITERAL, reproduced from M082's migration rather than imported -- see
# the module docstring. All 29 codepoints of Python 3.13's `str.strip()` blank
# set, escaped for PostgreSQL's E'' parser (not Python's). RAW, DOUBLED
# BACKSLASHES: these are literal two-character `\x`/`\u` escape sequences for
# PostgreSQL's own parser, not Python string escapes.
_BLANK_SQL = (
    "\\x09\\x0A\\x0B\\x0C\\x0D\\x1C"
    "\\x1D\\x1E\\x1F\\x20\\u0085\\u00A0"
    "\\u1680\\u2000\\u2001\\u2002\\u2003\\u2004"
    "\\u2005\\u2006\\u2007\\u2008\\u2009\\u200A"
    "\\u2028\\u2029\\u202F\\u205F\\u3000"
)

_NOT_BLANK_WATERMARK_ID = f"btrim(watermark_governance_id, E'{_BLANK_SQL}') <> ''"

_IMMUTABILITY_FUNCTION = """
CREATE OR REPLACE FUNCTION public.evaluation_evidence_watermark_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'evaluation_evidence_watermark is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_IMMUTABILITY_TRIGGER = """
CREATE TRIGGER evaluation_evidence_watermark_immutable_trigger
BEFORE UPDATE OR DELETE ON public.evaluation_evidence_watermark
FOR EACH ROW EXECUTE FUNCTION public.evaluation_evidence_watermark_immutable()
"""

# THE CAPTURE TRIGGER. Runs BEFORE INSERT and unconditionally REPLACES
# NEW.receipt_governance_ids -- it never reads the caller-supplied value, so a
# direct SQL caller cannot influence the stored set by any combination of
# omission, addition, duplication or reordering. Schema-qualified relation and
# a pinned, minimal search_path (owner-review lesson reproduced from M082):
# an unqualified read would resolve a same-named pg_temp relation ahead of
# public for a caller who created one.
_CAPTURE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.evaluation_evidence_watermark_capture_receipt_set()
RETURNS trigger AS $$
BEGIN
    NEW.receipt_governance_ids := (
        SELECT COALESCE(
            array_agg(r.receipt_governance_id ORDER BY r.receipt_governance_id COLLATE "C"),
            ARRAY[]::text[]
        )
        FROM public.operator_event_receipt r
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_CAPTURE_TRIGGER = """
CREATE TRIGGER evaluation_evidence_watermark_capture_receipt_set_trigger
BEFORE INSERT ON public.evaluation_evidence_watermark
FOR EACH ROW EXECUTE FUNCTION public.evaluation_evidence_watermark_capture_receipt_set()
"""


def upgrade() -> None:
    op.create_table(
        "evaluation_evidence_watermark",
        sa.Column("watermark_governance_id", sa.String(length=64), primary_key=True),
        # NOT NULL with no server default: without the capture trigger, an
        # INSERT that omits this column fails NOT NULL rather than silently
        # persisting an unset watermark. The trigger always supplies a value
        # (possibly the empty array) before the constraint is checked, because
        # BEFORE ROW triggers run before NOT NULL/CHECK validation.
        sa.Column(
            "receipt_governance_ids",
            sa.ARRAY(sa.String(length=64)),
            nullable=False,
        ),
        sa.CheckConstraint(
            _NOT_BLANK_WATERMARK_ID,
            name="ck_evaluation_evidence_watermark_id_present",
        ),
        sa.PrimaryKeyConstraint(
            "watermark_governance_id",
            name="pk_evaluation_evidence_watermark",
        ),
    )
    op.execute(_IMMUTABILITY_FUNCTION)
    op.execute(_IMMUTABILITY_TRIGGER)
    op.execute(_CAPTURE_FUNCTION)
    op.execute(_CAPTURE_TRIGGER)


def downgrade() -> None:
    # Removes ONLY M083 objects. M082's table, triggers, functions and rows
    # are never referenced here and survive unchanged -- proven directly by
    # `tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py`
    # running an upgrade/downgrade/upgrade cycle against a live database and
    # asserting M082 row counts and behaviour are unaffected.
    op.execute(
        "DROP TRIGGER IF EXISTS evaluation_evidence_watermark_capture_receipt_set_trigger "
        "ON public.evaluation_evidence_watermark"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS evaluation_evidence_watermark_immutable_trigger "
        "ON public.evaluation_evidence_watermark"
    )
    op.drop_table("evaluation_evidence_watermark")
    op.execute("DROP FUNCTION IF EXISTS public.evaluation_evidence_watermark_capture_receipt_set()")
    op.execute("DROP FUNCTION IF EXISTS public.evaluation_evidence_watermark_immutable()")
