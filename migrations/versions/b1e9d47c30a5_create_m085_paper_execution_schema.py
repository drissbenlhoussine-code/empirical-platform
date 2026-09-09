"""MILESTONE-085 Alpaca paper execution with exact human approval schema.

ADDITIVE ONLY. No table, trigger, function, column or row belonging to any
earlier milestone is created, altered or dropped. `approved_order_intent`
(MILESTONE-084) is REFERENCED by foreign key and never written: MILESTONE-085
adds no transition away from `submission_state = NOT_SUBMITTED` and stores its
own execution state in its own tables, keyed by the intent's governance
identity. The M084 row a human approved is byte-for-byte unchanged afterwards.

THE CLAIM, AND ONLY THIS. These tables record, durably and in a form the
database itself refuses to corrupt:

  - what a paper account said about itself at one instant;
  - exactly what a human was shown before authorizing a dispatch;
  - one explicit, expiring, SINGLE-USE human authorization, bound to one exact
    request fingerprint, one exact paper account reference and one exact
    `client_order_id`;
  - AT MOST ONE dispatch attempt per approved intent, ever;
  - every answer the broker gave, append-only and in order;
  - the execution stop, versioned and append-only.

WHAT IT DOES NOT CLAIM. Nothing here asserts that a paper acknowledgement is a
real-market execution, that a paper fill predicts a live fill, that an order was
profitable, fillable or well-executed, or that this product may touch a live
account. The full list lives in
`external-review/MILESTONE-085/current-authority.json`.

EXACTLY-ONCE IS A UNIQUE CONSTRAINT, NOT A CONVENTION. `paper_execution_attempt`
carries UNIQUE on `intent_governance_id` AND UNIQUE on `client_order_id`. Two
concurrent workers therefore cannot both create an attempt for one intent, and
no two attempts can ever address the same broker order identity. Neither
depends on the application asking politely, and neither depends on the BROKER's
duplicate protection -- Alpaca refuses a duplicate `client_order_id` only while
the first order is still active, so it is not a durable exactly-once authority
and nothing here treats it as one.

SINGLE USE IS THE ONLY PERMITTED MUTATION IN THIS SCHEMA. Every table below is
append-only under its installed triggers, with exactly two exceptions, both
narrow and both enforced:

  - `paper_execution_authorization` may move `consumed_at` and
    `consumed_by_attempt_id` from NULL to a value, ONCE, never back, and may
    change nothing else. That is what makes a spent permission genuinely
    unusable rather than merely discouraged.
  - `paper_execution_attempt` may move `state` along the CLOSED transition
    table, and may set the broker/outcome columns. Its identity columns --
    intent, authorization, `client_order_id`, request fingerprint, claim instant
    -- are refused on UPDATE, so an attempt cannot be re-pointed at a different
    order after the fact.

THE TRANSITION TABLE IS MIRRORED HERE, NOT SUMMARIZED. `paper_execution_attempt
_guard_update()` encodes the same edges as
`empirical_platform.decision_candidate.paper_execution.ALLOWED_PAPER_TRANSITIONS`,
and an integration test compares the two so that they cannot drift. Two edges
are deliberate and easy to misread as bugs: CANCEL_REQUESTED -> FILLED, because
asking to cancel races the venue and can lose; and SUBMISSION_UNKNOWN -> every
real outcome but NOT back to SUBMISSION_IN_PROGRESS, so an ambiguous dispatch
can be resolved but never quietly retried into a second order.

IMMUTABILITY, THE SAME NARROW SHAPE AS M082/M083/M084. The append-only triggers
are BEFORE UPDATE OR DELETE ROW triggers. That is ROW-LEVEL IMMUTABILITY UNDER
THE INSTALLED TRIGGERS ONLY: TRUNCATE is statement-level and not intercepted,
and DROP TRIGGER, DROP TABLE, ALTER TABLE ... DISABLE TRIGGER,
`session_replication_role = replica` and superuser mutation all remain possible.
This must not be described as absolute database immutability.

MEASURED CROSS-MILESTONE LIMITATION. The foreign keys below make a TRUNCATE of
M084's `approved_order_intent` structurally inexecutable while this schema is
installed, exactly as M084's own foreign key did to M083's fixture. This is
recorded rather than repaired, and it disappears on downgrade.

BLANK IDENTITY. Identity columns use the identical frozen 29-character Python
3.13 `str.strip()` blank set that M082's, M083's and M084's migrations froze
locally, reproduced here rather than imported, because a migration is history
and must not depend on mutable application code.

Revision ID: b1e9d47c30a5
Revises: a3f7c21d9b04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b1e9d47c30a5"
down_revision: str | None = "a3f7c21d9b04"
branch_labels: None = None
depends_on: None = None

# FROZEN LITERAL, reproduced from M082/M083/M084 rather than imported -- see the
# module docstring. All 29 codepoints of Python 3.13's `str.strip()` blank set,
# escaped for PostgreSQL's E'' parser (not Python's). RAW, DOUBLED BACKSLASHES:
# these are literal two-character escape sequences for PostgreSQL's own parser.
_BLANK_SQL = (
    "\\x09\\x0A\\x0B\\x0C\\x0D\\x1C"
    "\\x1D\\x1E\\x1F\\x20\\u0085\\u00A0"
    "\\u1680\\u2000\\u2001\\u2002\\u2003\\u2004"
    "\\u2005\\u2006\\u2007\\u2008\\u2009\\u200A"
    "\\u2028\\u2029\\u202F\\u205F\\u3000"
)


def _not_blank(column: str) -> str:
    return f"btrim({column}, E'{_BLANK_SQL}') <> ''"


# A 64-character lowercase hex digest. Stated as a pattern rather than a length
# so that a truncated, upper-cased or partially-written digest is refused too.
_HEX_DIGEST = "~ '^[0-9a-f]{64}$'"

#: The one host an order may be dispatched to. A CHECK, so a row describing a
#: dispatch to anywhere else cannot be stored at all -- including by a direct
#: SQL writer who never went through the adapter's URL pinning.
_PAPER_HOST = "paper-api.alpaca.markets"

_STATES = (
    "'NOT_DISPATCHED', 'AUTHORIZATION_PENDING', 'AUTHORIZED', 'DISPATCH_CLAIMED', "
    "'SUBMISSION_IN_PROGRESS', 'PAPER_SUBMITTED', 'PAPER_ACCEPTED', 'PARTIALLY_FILLED', "
    "'FILLED', 'CANCEL_REQUESTED', 'CANCELED', 'REJECTED', 'EXPIRED', 'SUBMISSION_UNKNOWN'"
)

#: States an ATTEMPT row may hold. NOT_DISPATCHED, AUTHORIZATION_PENDING and
#: AUTHORIZED describe an intent that has no attempt yet, so an attempt row
#: carrying one of them would be a contradiction.
_ATTEMPT_STATES = (
    "'DISPATCH_CLAIMED', 'SUBMISSION_IN_PROGRESS', 'PAPER_SUBMITTED', 'PAPER_ACCEPTED', "
    "'PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED', 'CANCELED', 'REJECTED', 'EXPIRED', "
    "'SUBMISSION_UNKNOWN'"
)

_TERMINAL_STATES = "'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED'"

# ---------------------------------------------------------------------------
# Shared append-only trigger function
# ---------------------------------------------------------------------------

_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION public.m085_append_only()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

# ---------------------------------------------------------------------------
# Single-use authorization consumption
# ---------------------------------------------------------------------------

_AUTHORIZATION_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_execution_authorization_guard_update()
RETURNS trigger AS $$
BEGIN
    -- Consumption is the ONLY permitted change, and only in one direction.
    IF OLD.consumed_at IS NOT NULL THEN
        RAISE EXCEPTION
            'authorization % has already been used and cannot be consumed again',
            OLD.authorization_id;
    END IF;
    IF NEW.consumed_at IS NULL THEN
        RAISE EXCEPTION
            'authorization % may only be updated in order to consume it',
            OLD.authorization_id;
    END IF;
    IF NEW.consumed_by_attempt_id IS NULL THEN
        RAISE EXCEPTION
            'consuming authorization % requires the attempt that consumed it',
            OLD.authorization_id;
    END IF;

    -- Nothing else may move. An authorization whose fingerprint, account or
    -- expiry could be edited would not be a binding permission.
    IF NEW.authorization_id IS DISTINCT FROM OLD.authorization_id
        OR NEW.intent_governance_id IS DISTINCT FROM OLD.intent_governance_id
        OR NEW.preview_id IS DISTINCT FROM OLD.preview_id
        OR NEW.preview_version IS DISTINCT FROM OLD.preview_version
        OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
        OR NEW.account_reference IS DISTINCT FROM OLD.account_reference
        OR NEW.client_order_id IS DISTINCT FROM OLD.client_order_id
        OR NEW.authorized_by IS DISTINCT FROM OLD.authorized_by
        OR NEW.authorized_at IS DISTINCT FROM OLD.authorized_at
        OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
    THEN
        RAISE EXCEPTION
            'authorization % is immutable apart from its consumption',
            OLD.authorization_id;
    END IF;

    -- An expired authorization cannot be consumed. Enforced here as well as in
    -- the application because expiry is the whole point of a short-lived
    -- permission, and a caller that reads the row and then acts is one clock
    -- skew away from acting on a lapsed one.
    IF NEW.consumed_at >= OLD.expires_at THEN
        RAISE EXCEPTION
            'authorization % expired at % and cannot be consumed at %',
            OLD.authorization_id, OLD.expires_at, NEW.consumed_at;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_AUTHORIZATION_UPDATE_TRIGGER = """
CREATE TRIGGER paper_execution_authorization_guard_update_trigger
BEFORE UPDATE ON public.paper_execution_authorization
FOR EACH ROW EXECUTE FUNCTION public.paper_execution_authorization_guard_update()
"""

_AUTHORIZATION_DELETE_TRIGGER = """
CREATE TRIGGER paper_execution_authorization_refuse_delete_trigger
BEFORE DELETE ON public.paper_execution_authorization
FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()
"""

# ---------------------------------------------------------------------------
# The attempt: insert guard and the closed transition table
# ---------------------------------------------------------------------------

_ATTEMPT_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_execution_attempt_guard_insert()
RETURNS trigger AS $$
DECLARE
    authorization_row public.paper_execution_authorization;
BEGIN
    -- An attempt exists only because a human authorization was spent on it.
    SELECT * INTO authorization_row
    FROM public.paper_execution_authorization
    WHERE authorization_id = NEW.authorization_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'attempt % references authorization % which does not exist',
            NEW.attempt_id, NEW.authorization_id;
    END IF;

    IF authorization_row.consumed_at IS NULL THEN
        RAISE EXCEPTION
            'attempt % requires authorization % to be consumed in the same transaction',
            NEW.attempt_id, NEW.authorization_id;
    END IF;

    IF authorization_row.consumed_by_attempt_id IS DISTINCT FROM NEW.attempt_id THEN
        RAISE EXCEPTION
            'authorization % was consumed by attempt %, not by attempt %',
            NEW.authorization_id,
            authorization_row.consumed_by_attempt_id,
            NEW.attempt_id;
    END IF;

    -- The three bindings that make this dispatch the authorized one.
    IF authorization_row.intent_governance_id IS DISTINCT FROM NEW.intent_governance_id THEN
        RAISE EXCEPTION
            'authorization % authorizes intent %, not intent %',
            NEW.authorization_id,
            authorization_row.intent_governance_id,
            NEW.intent_governance_id;
    END IF;

    IF authorization_row.request_fingerprint IS DISTINCT FROM NEW.request_fingerprint THEN
        RAISE EXCEPTION
            'attempt % does not carry the authorized request fingerprint',
            NEW.attempt_id;
    END IF;

    IF authorization_row.client_order_id IS DISTINCT FROM NEW.client_order_id THEN
        RAISE EXCEPTION
            'attempt % does not carry the authorized client order id',
            NEW.attempt_id;
    END IF;

    -- A dispatch always begins by being claimed. An attempt inserted directly
    -- as PAPER_SUBMITTED would be a submission with no claim behind it.
    IF NEW.state <> 'DISPATCH_CLAIMED' THEN
        RAISE EXCEPTION
            'attempt % must be inserted as DISPATCH_CLAIMED, not %',
            NEW.attempt_id, NEW.state;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_ATTEMPT_INSERT_TRIGGER = """
CREATE TRIGGER paper_execution_attempt_guard_insert_trigger
BEFORE INSERT ON public.paper_execution_attempt
FOR EACH ROW EXECUTE FUNCTION public.paper_execution_attempt_guard_insert()
"""

_ATTEMPT_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_execution_attempt_guard_update()
RETURNS trigger AS $$
DECLARE
    allowed text[];
BEGIN
    -- Identity is fixed at claim time. If any of these could move, an attempt
    -- could be re-pointed at a different order or a different authorization
    -- after the fact, and the audit trail would describe something that never
    -- happened.
    IF NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
        OR NEW.intent_governance_id IS DISTINCT FROM OLD.intent_governance_id
        OR NEW.authorization_id IS DISTINCT FROM OLD.authorization_id
        OR NEW.client_order_id IS DISTINCT FROM OLD.client_order_id
        OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
        OR NEW.claimed_at IS DISTINCT FROM OLD.claimed_at
    THEN
        RAISE EXCEPTION
            'attempt % identity is immutable after the dispatch claim',
            OLD.attempt_id;
    END IF;

    IF NEW.state = OLD.state THEN
        -- A same-state update refreshes what the broker last said. Permitted,
        -- because reconciliation legitimately re-reads an order that has not
        -- moved. It still cannot resurrect a terminal attempt, since the state
        -- is unchanged by definition.
        RETURN NEW;
    END IF;

    IF OLD.state IN (__TERMINAL__) THEN
        RAISE EXCEPTION
            'attempt % is terminal in state % and cannot move to %',
            OLD.attempt_id, OLD.state, NEW.state;
    END IF;

    -- The closed transition table, mirrored from
    -- decision_candidate.paper_execution.ALLOWED_PAPER_TRANSITIONS. An
    -- integration test compares the two, so they cannot drift apart.
    allowed := CASE OLD.state
        WHEN 'DISPATCH_CLAIMED' THEN
            ARRAY['SUBMISSION_IN_PROGRESS', 'REJECTED', 'EXPIRED']
        WHEN 'SUBMISSION_IN_PROGRESS' THEN
            ARRAY['PAPER_SUBMITTED', 'SUBMISSION_UNKNOWN', 'REJECTED']
        WHEN 'PAPER_SUBMITTED' THEN
            ARRAY['PAPER_ACCEPTED', 'PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED',
                  'CANCELED', 'REJECTED', 'EXPIRED', 'SUBMISSION_UNKNOWN']
        WHEN 'PAPER_ACCEPTED' THEN
            ARRAY['PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED', 'CANCELED',
                  'REJECTED', 'EXPIRED', 'SUBMISSION_UNKNOWN']
        WHEN 'PARTIALLY_FILLED' THEN
            ARRAY['FILLED', 'CANCEL_REQUESTED', 'CANCELED', 'EXPIRED',
                  'SUBMISSION_UNKNOWN']
        WHEN 'CANCEL_REQUESTED' THEN
            ARRAY['CANCELED', 'PARTIALLY_FILLED', 'FILLED', 'REJECTED', 'EXPIRED',
                  'SUBMISSION_UNKNOWN']
        WHEN 'SUBMISSION_UNKNOWN' THEN
            ARRAY['PAPER_SUBMITTED', 'PAPER_ACCEPTED', 'PARTIALLY_FILLED', 'FILLED',
                  'CANCEL_REQUESTED', 'CANCELED', 'REJECTED', 'EXPIRED']
        ELSE ARRAY[]::text[]
    END;

    IF NOT (NEW.state = ANY (allowed)) THEN
        RAISE EXCEPTION
            '% -> % is not an allowed paper execution transition for attempt %',
            OLD.state, NEW.state, OLD.attempt_id;
    END IF;

    IF NEW.state IN (__TERMINAL__) AND NEW.terminal_at IS NULL THEN
        RAISE EXCEPTION
            'attempt % entering terminal state % requires terminal_at',
            OLD.attempt_id, NEW.state;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
""".replace("__TERMINAL__", _TERMINAL_STATES)

_ATTEMPT_UPDATE_TRIGGER = """
CREATE TRIGGER paper_execution_attempt_guard_update_trigger
BEFORE UPDATE ON public.paper_execution_attempt
FOR EACH ROW EXECUTE FUNCTION public.paper_execution_attempt_guard_update()
"""

_ATTEMPT_DELETE_TRIGGER = """
CREATE TRIGGER paper_execution_attempt_refuse_delete_trigger
BEFORE DELETE ON public.paper_execution_attempt
FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()
"""

_PREVIEW_IMMUTABLE_TRIGGER = """
CREATE TRIGGER paper_submission_preview_append_only_trigger
BEFORE UPDATE OR DELETE ON public.paper_submission_preview
FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()
"""

_ACCOUNT_IMMUTABLE_TRIGGER = """
CREATE TRIGGER paper_account_snapshot_append_only_trigger
BEFORE UPDATE OR DELETE ON public.paper_account_snapshot
FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()
"""

_ACKNOWLEDGEMENT_IMMUTABLE_TRIGGER = """
CREATE TRIGGER paper_broker_acknowledgement_append_only_trigger
BEFORE UPDATE OR DELETE ON public.paper_broker_acknowledgement
FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()
"""

_EVENT_IMMUTABLE_TRIGGER = """
CREATE TRIGGER paper_execution_event_append_only_trigger
BEFORE UPDATE OR DELETE ON public.paper_execution_event
FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()
"""

_KILL_SWITCH_IMMUTABLE_TRIGGER = """
CREATE TRIGGER paper_execution_kill_switch_append_only_trigger
BEFORE UPDATE OR DELETE ON public.paper_execution_kill_switch
FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()
"""


def _create_kill_switch_table() -> None:
    op.create_table(
        "paper_execution_kill_switch",
        sa.Column("kill_switch_id", sa.String(length=64), primary_key=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("engaged", sa.Boolean(), nullable=False),
        sa.Column("changed_by", sa.String(length=64), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        # Moving the switch writes a NEW version rather than editing one, so the
        # history of who stopped execution and when survives.
        sa.UniqueConstraint("scope", "version", name="uq_paper_kill_switch_scope_version"),
        sa.CheckConstraint(_not_blank("kill_switch_id"), name="ck_paper_kill_switch_id_present"),
        sa.CheckConstraint(_not_blank("changed_by"), name="ck_paper_kill_switch_actor_present"),
        sa.CheckConstraint("scope = 'GLOBAL'", name="ck_paper_kill_switch_scope"),
        sa.CheckConstraint("version >= 1", name="ck_paper_kill_switch_version_positive"),
    )


def _create_account_snapshot_table() -> None:
    op.create_table(
        "paper_account_snapshot",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("environment", sa.String(length=8), nullable=False),
        sa.Column("endpoint_host", sa.String(length=64), nullable=False),
        # A DIGEST of the broker account id, never the id. The product needs to
        # prove two records concern the same account; it does not need to store a
        # real account number to do that.
        sa.Column("account_reference", sa.String(length=64), nullable=False),
        sa.Column("account_status", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("buying_power", sa.Numeric(24, 8), nullable=False),
        sa.Column("cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("equity", sa.Numeric(24, 8), nullable=False),
        sa.Column("multiplier", sa.String(length=8), nullable=False),
        sa.Column("shorting_enabled", sa.Boolean(), nullable=False),
        sa.Column("trading_blocked", sa.Boolean(), nullable=False),
        sa.Column("transfers_blocked", sa.Boolean(), nullable=False),
        sa.Column("account_blocked", sa.Boolean(), nullable=False),
        sa.Column("trade_suspended_by_user", sa.Boolean(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_not_blank("snapshot_id"), name="ck_paper_account_id_present"),
        sa.CheckConstraint(
            _not_blank("account_reference"), name="ck_paper_account_reference_present"
        ),
        # PAPER is the only environment this schema can express. A row claiming
        # a live environment cannot be stored.
        sa.CheckConstraint("environment = 'PAPER'", name="ck_paper_account_environment"),
        sa.CheckConstraint(
            f"endpoint_host = '{_PAPER_HOST}'", name="ck_paper_account_endpoint_host"
        ),
        sa.CheckConstraint("currency = 'USD'", name="ck_paper_account_currency"),
    )


def _create_preview_table() -> None:
    op.create_table(
        "paper_submission_preview",
        sa.Column("preview_id", sa.String(length=64), primary_key=True),
        sa.Column("intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("preview_version", sa.Integer(), nullable=False),
        sa.Column("account_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("account_reference", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("limit_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("time_in_force", sa.String(length=8), nullable=False),
        sa.Column("extended_hours", sa.Boolean(), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("approved_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("market_is_open", sa.Boolean(), nullable=False),
        sa.Column("market_next_open", sa.DateTime(timezone=True), nullable=True),
        sa.Column("market_next_close", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quote_bid", sa.Numeric(20, 8), nullable=True),
        sa.Column("quote_ask", sa.Numeric(20, 8), nullable=True),
        sa.Column("quote_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quote_source", sa.String(length=32), nullable=False),
        sa.Column("asset_tradable", sa.Boolean(), nullable=False),
        sa.Column("asset_status", sa.String(length=16), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("asset_exchange", sa.String(length=16), nullable=False),
        sa.Column("asset_fractionable", sa.Boolean(), nullable=False),
        sa.Column("refusals", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["intent_governance_id"],
            ["approved_order_intent.intent_governance_id"],
            name="fk_paper_preview_intent",
        ),
        sa.ForeignKeyConstraint(
            ["account_snapshot_id"],
            ["paper_account_snapshot.snapshot_id"],
            name="fk_paper_preview_account_snapshot",
        ),
        sa.UniqueConstraint(
            "intent_governance_id", "preview_version", name="uq_paper_preview_intent_version"
        ),
        sa.CheckConstraint(_not_blank("preview_id"), name="ck_paper_preview_id_present"),
        sa.CheckConstraint("preview_version >= 1", name="ck_paper_preview_version_positive"),
        # The four product invariants, at the database boundary. A preview
        # describing a sell, a fractional quantity, an overnight order or an
        # extended-hours order cannot be stored, so it cannot be authorized.
        sa.CheckConstraint("side = 'BUY'", name="ck_paper_preview_long_only"),
        sa.CheckConstraint("quantity > 0", name="ck_paper_preview_quantity_positive"),
        sa.CheckConstraint("time_in_force = 'DAY'", name="ck_paper_preview_time_in_force"),
        sa.CheckConstraint("extended_hours = false", name="ck_paper_preview_no_extended_hours"),
        sa.CheckConstraint("order_type IN ('MARKET', 'LIMIT')", name="ck_paper_preview_order_type"),
        sa.CheckConstraint(
            "(order_type = 'LIMIT' AND limit_price IS NOT NULL AND limit_price > 0)"
            " OR (order_type <> 'LIMIT' AND limit_price IS NULL)",
            name="ck_paper_preview_limit_price_shape",
        ),
        sa.CheckConstraint(
            f"request_fingerprint {_HEX_DIGEST}", name="ck_paper_preview_request_fingerprint"
        ),
        sa.CheckConstraint(
            f"approved_fingerprint {_HEX_DIGEST}", name="ck_paper_preview_approved_fingerprint"
        ),
        sa.CheckConstraint(
            "client_order_id LIKE 'm085-%'", name="ck_paper_preview_client_order_id_prefix"
        ),
        sa.CheckConstraint(
            "length(client_order_id) BETWEEN 6 AND 64",
            name="ck_paper_preview_client_order_id_length",
        ),
    )
    op.create_index(
        "ix_paper_preview_intent",
        "paper_submission_preview",
        ["intent_governance_id"],
    )


def _create_authorization_table() -> None:
    op.create_table(
        "paper_execution_authorization",
        sa.Column("authorization_id", sa.String(length=64), primary_key=True),
        sa.Column("intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("preview_id", sa.String(length=64), nullable=False),
        sa.Column("preview_version", sa.Integer(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("account_reference", sa.String(length=64), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("authorized_by", sa.String(length=64), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        # Deliberately NOT a foreign key to the attempt: the attempt's insert
        # guard reads this row, so a mutual foreign key would make the pair
        # uninsertable in either order.
        sa.Column("consumed_by_attempt_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["intent_governance_id"],
            ["approved_order_intent.intent_governance_id"],
            name="fk_paper_authorization_intent",
        ),
        sa.ForeignKeyConstraint(
            ["preview_id"],
            ["paper_submission_preview.preview_id"],
            name="fk_paper_authorization_preview",
        ),
        # ONE authorization per preview. A second permission for the same shown
        # preview would be a second chance to spend one human decision.
        sa.UniqueConstraint("preview_id", name="uq_paper_authorization_one_per_preview"),
        sa.CheckConstraint(
            _not_blank("authorization_id"), name="ck_paper_authorization_id_present"
        ),
        sa.CheckConstraint(
            _not_blank("authorized_by"), name="ck_paper_authorization_actor_present"
        ),
        sa.CheckConstraint(
            "expires_at > authorized_at", name="ck_paper_authorization_expiry_follows"
        ),
        sa.CheckConstraint(
            f"request_fingerprint {_HEX_DIGEST}",
            name="ck_paper_authorization_request_fingerprint",
        ),
        sa.CheckConstraint(
            "client_order_id LIKE 'm085-%'", name="ck_paper_authorization_client_order_id_prefix"
        ),
        # Consumption is all-or-nothing: a row cannot record that it was used
        # without recording what used it.
        sa.CheckConstraint(
            "(consumed_at IS NULL AND consumed_by_attempt_id IS NULL)"
            " OR (consumed_at IS NOT NULL AND consumed_by_attempt_id IS NOT NULL)",
            name="ck_paper_authorization_consumption_is_paired",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= authorized_at",
            name="ck_paper_authorization_consumed_after_authorized",
        ),
    )
    # AT MOST ONE CONSUMED AUTHORIZATION PER INTENT. Unconsumed authorizations
    # may accumulate -- one may lapse unused and a human may authorize again --
    # but only one can ever be spent, so one intent can only ever have been
    # dispatched once.
    op.create_index(
        "uq_paper_authorization_one_consumed_per_intent",
        "paper_execution_authorization",
        ["intent_governance_id"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NOT NULL"),
    )
    op.create_index(
        "ix_paper_authorization_intent",
        "paper_execution_authorization",
        ["intent_governance_id"],
    )


def _create_attempt_table() -> None:
    op.create_table(
        "paper_execution_attempt",
        sa.Column("attempt_id", sa.String(length=64), primary_key=True),
        sa.Column("intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("authorization_id", sa.String(length=64), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column("broker_status", sa.String(length=32), nullable=True),
        sa.Column("filled_quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("filled_avg_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("failure_code", sa.String(length=32), nullable=True),
        sa.Column("failure_detail", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["intent_governance_id"],
            ["approved_order_intent.intent_governance_id"],
            name="fk_paper_attempt_intent",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["paper_execution_authorization.authorization_id"],
            name="fk_paper_attempt_authorization",
        ),
        # THE TWO EXACTLY-ONCE CONSTRAINTS. Neither is an application
        # convention. One intent cannot have two attempts, and no two attempts
        # can address one broker order identity.
        sa.UniqueConstraint("intent_governance_id", name="uq_paper_attempt_one_per_intent"),
        sa.UniqueConstraint("client_order_id", name="uq_paper_attempt_client_order_id"),
        sa.UniqueConstraint("authorization_id", name="uq_paper_attempt_one_per_authorization"),
        sa.CheckConstraint(_not_blank("attempt_id"), name="ck_paper_attempt_id_present"),
        sa.CheckConstraint(f"state IN ({_ATTEMPT_STATES})", name="ck_paper_attempt_state"),
        sa.CheckConstraint(
            f"request_fingerprint {_HEX_DIGEST}", name="ck_paper_attempt_request_fingerprint"
        ),
        sa.CheckConstraint(
            "client_order_id LIKE 'm085-%'", name="ck_paper_attempt_client_order_id_prefix"
        ),
        sa.CheckConstraint(
            f"(state IN ({_TERMINAL_STATES}) AND terminal_at IS NOT NULL)"
            f" OR (state NOT IN ({_TERMINAL_STATES}) AND terminal_at IS NULL)",
            name="ck_paper_attempt_terminal_at_matches_state",
        ),
        sa.CheckConstraint(
            "filled_quantity IS NULL OR filled_quantity >= 0",
            name="ck_paper_attempt_filled_quantity_non_negative",
        ),
    )
    op.create_index(
        "ix_paper_attempt_state_claimed",
        "paper_execution_attempt",
        ["state", "claimed_at"],
    )


def _create_acknowledgement_table() -> None:
    op.create_table(
        "paper_broker_acknowledgement",
        sa.Column("acknowledgement_id", sa.String(length=64), primary_key=True),
        sa.Column("attempt_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column("broker_status", sa.String(length=32), nullable=True),
        sa.Column("client_order_id_echo", sa.String(length=64), nullable=True),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column("sanitized_payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["paper_execution_attempt.attempt_id"],
            name="fk_paper_acknowledgement_attempt",
        ),
        sa.UniqueConstraint(
            "attempt_id", "sequence", name="uq_paper_acknowledgement_attempt_sequence"
        ),
        sa.CheckConstraint(
            _not_blank("acknowledgement_id"), name="ck_paper_acknowledgement_id_present"
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_paper_acknowledgement_sequence_positive"),
        sa.CheckConstraint(
            "kind IN ('SUBMIT', 'RECONCILE', 'CANCEL')", name="ck_paper_acknowledgement_kind"
        ),
        sa.CheckConstraint(
            f"payload_digest {_HEX_DIGEST}", name="ck_paper_acknowledgement_payload_digest"
        ),
        # A bounded body. An unbounded broker response would let a hostile or
        # broken endpoint grow this table without limit.
        sa.CheckConstraint(
            "length(sanitized_payload) <= 8192",
            name="ck_paper_acknowledgement_payload_bounded",
        ),
    )
    op.create_index(
        "ix_paper_acknowledgement_attempt",
        "paper_broker_acknowledgement",
        ["attempt_id", "sequence"],
    )


def _create_event_table() -> None:
    op.create_table(
        "paper_execution_event",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(
            ["intent_governance_id"],
            ["approved_order_intent.intent_governance_id"],
            name="fk_paper_event_intent",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["paper_execution_attempt.attempt_id"],
            name="fk_paper_event_attempt",
        ),
        sa.CheckConstraint(_not_blank("event_id"), name="ck_paper_event_id_present"),
        sa.CheckConstraint(_not_blank("event_type"), name="ck_paper_event_type_present"),
    )
    op.create_index(
        "ix_paper_event_intent_occurred",
        "paper_execution_event",
        ["intent_governance_id", "occurred_at"],
    )


def upgrade() -> None:
    # Order matters: the shared refusal function first, then tables in
    # dependency order, then the guards that read those tables.
    op.execute(_APPEND_ONLY_FUNCTION)

    _create_kill_switch_table()
    _create_account_snapshot_table()
    _create_preview_table()
    _create_authorization_table()
    _create_attempt_table()
    _create_acknowledgement_table()
    _create_event_table()

    op.execute(_AUTHORIZATION_UPDATE_FUNCTION)
    op.execute(_AUTHORIZATION_UPDATE_TRIGGER)
    op.execute(_AUTHORIZATION_DELETE_TRIGGER)
    op.execute(_ATTEMPT_INSERT_FUNCTION)
    op.execute(_ATTEMPT_INSERT_TRIGGER)
    op.execute(_ATTEMPT_UPDATE_FUNCTION)
    op.execute(_ATTEMPT_UPDATE_TRIGGER)
    op.execute(_ATTEMPT_DELETE_TRIGGER)
    op.execute(_PREVIEW_IMMUTABLE_TRIGGER)
    op.execute(_ACCOUNT_IMMUTABLE_TRIGGER)
    op.execute(_ACKNOWLEDGEMENT_IMMUTABLE_TRIGGER)
    op.execute(_EVENT_IMMUTABLE_TRIGGER)
    op.execute(_KILL_SWITCH_IMMUTABLE_TRIGGER)


def downgrade() -> None:
    # Removes ONLY MILESTONE-085 objects. M084's `approved_order_intent` is
    # referenced by foreign key above and never altered; it and every earlier
    # milestone's tables, rows, constraints and triggers survive this downgrade
    # unchanged, and the M084 schema behaves exactly as it did before.
    op.execute(
        "DROP TRIGGER IF EXISTS paper_execution_kill_switch_append_only_trigger "
        "ON public.paper_execution_kill_switch"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_execution_event_append_only_trigger "
        "ON public.paper_execution_event"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_broker_acknowledgement_append_only_trigger "
        "ON public.paper_broker_acknowledgement"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_account_snapshot_append_only_trigger "
        "ON public.paper_account_snapshot"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_submission_preview_append_only_trigger "
        "ON public.paper_submission_preview"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_execution_attempt_refuse_delete_trigger "
        "ON public.paper_execution_attempt"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_execution_attempt_guard_update_trigger "
        "ON public.paper_execution_attempt"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_execution_attempt_guard_insert_trigger "
        "ON public.paper_execution_attempt"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_execution_authorization_refuse_delete_trigger "
        "ON public.paper_execution_authorization"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_execution_authorization_guard_update_trigger "
        "ON public.paper_execution_authorization"
    )

    op.drop_table("paper_execution_event")
    op.drop_table("paper_broker_acknowledgement")
    op.drop_table("paper_execution_attempt")
    op.drop_table("paper_execution_authorization")
    op.drop_table("paper_submission_preview")
    op.drop_table("paper_account_snapshot")
    op.drop_table("paper_execution_kill_switch")

    op.execute("DROP FUNCTION IF EXISTS public.paper_execution_attempt_guard_update()")
    op.execute("DROP FUNCTION IF EXISTS public.paper_execution_attempt_guard_insert()")
    op.execute("DROP FUNCTION IF EXISTS public.paper_execution_authorization_guard_update()")
    op.execute("DROP FUNCTION IF EXISTS public.m085_append_only()")
