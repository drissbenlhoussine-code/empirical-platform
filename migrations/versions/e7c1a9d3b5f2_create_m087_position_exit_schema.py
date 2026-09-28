"""MILESTONE-087 human-approved position exit schema.

ADDITIVE ONLY. No table, trigger, function, column or row belonging to MILESTONE-085 or any
earlier milestone is created, altered or dropped. `paper_execution_attempt` (the M085
entry) is READ by insert guards and never written: an exit is keyed back to the entry
intent and the entry attempt it closes, and the M085 rows stay byte-for-byte unchanged.

THE CLAIM, AND ONLY THIS. These tables record, durably and in a form the database refuses
to corrupt:

  - exactly what the Owner was shown on an exit review page (`position_exit_preview`),
    including the position evidence it was judged on, with the FULL-CLOSE rule as CHECKs:
    quantity > 0, quantity = broker position, quantity = entry filled - already exited;
  - one explicit, expiring, SINGLE-USE human exit authorization per preview, bound to the
    preview's request fingerprint, its binding fingerprint, its account and its derived
    `m087-` client_order_id (`position_exit_authorization`);
  - AT MOST ONE ACTIVE exit attempt per position (a partial UNIQUE index on the entry
    intent over non-terminal-or-filled states), UNIQUE client_order_id, UNIQUE
    authorization, a closed transition table, and a once-only `closed_position_verified_at`
    that is the ONLY change a terminal FILLED row may take (`position_exit_attempt`);
  - every broker answer and every reconciliation round, append-only and sequence-ordered
    (`position_exit_acknowledgement`, `position_exit_reconciliation_round`);
  - the audit trail (`position_exit_event`), append-only.

WHAT IT DOES NOT CLAIM. Nothing here asserts that a simulated fill is a market execution,
that the environment can be anything but SIMULATION (a CHECK refuses any other value), or
that this product may touch a paper or live account for an exit.

IMMUTABILITY, THE SAME NARROW SHAPE AS M082-M085: BEFORE UPDATE OR DELETE ROW triggers.
Row-level immutability under the installed triggers only; TRUNCATE, DROP, DISABLE TRIGGER
and superuser mutation remain possible and this must not be described as absolute.

Revision ID: e7c1a9d3b5f2
Revises: a7d3c9e14f26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e7c1a9d3b5f2"
down_revision: str | None = "a7d3c9e14f26"
branch_labels: None = None
depends_on: None = None

_HEX_DIGEST = "~ '^[0-9a-f]{64}$'"

_STATES = (
    "'DISPATCH_CLAIMED', 'SUBMISSION_IN_PROGRESS', 'SUBMITTED', 'ACCEPTED', 'PARTIALLY_FILLED', "
    "'FILLED', 'CANCEL_REQUESTED', 'CANCELED', 'REJECTED', 'EXPIRED', 'SUBMISSION_UNKNOWN'"
)
_TERMINAL = "'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED'"
#: States that count as an ACTIVE exit identity for the position: everything but a
#: terminal outcome that left the position open (CANCELED, REJECTED, EXPIRED). FILLED is
#: active: the position is gone or being verified, and no second exit may address it.
_INACTIVE = "'CANCELED', 'REJECTED', 'EXPIRED'"
_OUTCOMES = "'NOT_FOUND', 'FOUND', 'UNUSABLE', 'FAILED'"

_PREVIEW = "position_exit_preview"
_AUTHORIZATION = "position_exit_authorization"
_ATTEMPT = "position_exit_attempt"
_ACK = "position_exit_acknowledgement"
_ROUND = "position_exit_reconciliation_round"
_EVENT = "position_exit_event"


def _not_blank(column: str) -> str:
    return f"length(btrim({column})) > 0"


_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION public.m087_append_only()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

#: A preview may only describe an M085 entry attempt that exists, belongs to the intent
#: named, and is final (FILLED, or CANCELED with shares already filled). A partially filled
#: entry whose remainder can still fill is refused here as well as in the domain.
_PREVIEW_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.position_exit_preview_guard_insert()
RETURNS trigger AS $$
DECLARE
    entry_row public.paper_execution_attempt;
BEGIN
    SELECT * INTO entry_row
    FROM public.paper_execution_attempt
    WHERE attempt_id = NEW.entry_attempt_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'exit preview % names entry attempt % which does not exist',
            NEW.preview_id, NEW.entry_attempt_id;
    END IF;

    IF entry_row.intent_governance_id IS DISTINCT FROM NEW.entry_intent_governance_id THEN
        RAISE EXCEPTION
            'exit preview % names entry attempt % which belongs to intent %, not %',
            NEW.preview_id, NEW.entry_attempt_id, entry_row.intent_governance_id,
            NEW.entry_intent_governance_id;
    END IF;

    IF entry_row.state NOT IN ('FILLED', 'CANCELED') THEN
        RAISE EXCEPTION
            'exit preview % names entry attempt % in state %; only a final entry can be closed',
            NEW.preview_id, NEW.entry_attempt_id, entry_row.state;
    END IF;

    IF entry_row.filled_quantity IS NULL OR entry_row.filled_quantity <= 0 THEN
        RAISE EXCEPTION
            'exit preview % names entry attempt % which filled nothing',
            NEW.preview_id, NEW.entry_attempt_id;
    END IF;

    IF NEW.entry_state IS DISTINCT FROM entry_row.state
        OR NEW.entry_filled_quantity IS DISTINCT FROM entry_row.filled_quantity
    THEN
        RAISE EXCEPTION
            'exit preview % records entry evidence that differs from the stored entry attempt %',
            NEW.preview_id, NEW.entry_attempt_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_AUTHORIZATION_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.position_exit_authorization_guard_insert()
RETURNS trigger AS $$
DECLARE
    preview_row public.position_exit_preview;
BEGIN
    SELECT * INTO preview_row FROM public.position_exit_preview
    WHERE preview_id = NEW.preview_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'exit authorization % names preview % which does not exist',
            NEW.authorization_id, NEW.preview_id;
    END IF;

    IF NEW.consumed_at IS NOT NULL OR NEW.consumed_by_attempt_id IS NOT NULL THEN
        RAISE EXCEPTION
            'exit authorization % must be inserted unconsumed', NEW.authorization_id;
    END IF;

    IF preview_row.entry_intent_governance_id IS DISTINCT FROM NEW.entry_intent_governance_id
        OR preview_row.preview_version IS DISTINCT FROM NEW.preview_version
        OR preview_row.request_fingerprint IS DISTINCT FROM NEW.request_fingerprint
        OR preview_row.binding_fingerprint IS DISTINCT FROM NEW.preview_binding_fingerprint
        OR preview_row.account_reference IS DISTINCT FROM NEW.account_reference
        OR preview_row.client_order_id IS DISTINCT FROM NEW.client_order_id
        OR preview_row.symbol IS DISTINCT FROM NEW.symbol
        OR preview_row.quantity IS DISTINCT FROM NEW.quantity
    THEN
        RAISE EXCEPTION
            'exit authorization % does not describe the preview it names; it permits nothing',
            NEW.authorization_id;
    END IF;

    -- A permission may not outlive the mandatory liquidation deadline it was granted under
    -- (when that deadline is still ahead at the time of authorizing).
    IF NEW.authorized_at < preview_row.liquidation_deadline
        AND NEW.expires_at > preview_row.liquidation_deadline
    THEN
        RAISE EXCEPTION
            'exit authorization % outlives the mandatory liquidation deadline %',
            NEW.authorization_id, preview_row.liquidation_deadline;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_AUTHORIZATION_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.position_exit_authorization_guard_update()
RETURNS trigger AS $$
BEGIN
    IF OLD.consumed_at IS NOT NULL THEN
        RAISE EXCEPTION
            'exit authorization % has already been used and cannot be consumed again',
            OLD.authorization_id;
    END IF;
    IF NEW.consumed_at IS NULL OR NEW.consumed_by_attempt_id IS NULL THEN
        RAISE EXCEPTION
            'exit authorization % may only be updated in order to consume it',
            OLD.authorization_id;
    END IF;
    IF NEW.authorization_id IS DISTINCT FROM OLD.authorization_id
        OR NEW.entry_intent_governance_id IS DISTINCT FROM OLD.entry_intent_governance_id
        OR NEW.preview_id IS DISTINCT FROM OLD.preview_id
        OR NEW.preview_version IS DISTINCT FROM OLD.preview_version
        OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
        OR NEW.preview_binding_fingerprint IS DISTINCT FROM OLD.preview_binding_fingerprint
        OR NEW.account_reference IS DISTINCT FROM OLD.account_reference
        OR NEW.client_order_id IS DISTINCT FROM OLD.client_order_id
        OR NEW.symbol IS DISTINCT FROM OLD.symbol
        OR NEW.quantity IS DISTINCT FROM OLD.quantity
        OR NEW.authorized_by IS DISTINCT FROM OLD.authorized_by
        OR NEW.authorized_at IS DISTINCT FROM OLD.authorized_at
        OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
        OR NEW.basis_host_requested_at IS DISTINCT FROM OLD.basis_host_requested_at
        OR NEW.basis_host_at IS DISTINCT FROM OLD.basis_host_at
        OR NEW.basis_broker_earliest_at IS DISTINCT FROM OLD.basis_broker_earliest_at
        OR NEW.basis_broker_latest_at IS DISTINCT FROM OLD.basis_broker_latest_at
    THEN
        RAISE EXCEPTION
            'exit authorization % is immutable apart from its consumption', OLD.authorization_id;
    END IF;
    IF NEW.consumed_at >= OLD.expires_at THEN
        RAISE EXCEPTION
            'exit authorization % expired at % and cannot be consumed at %',
            OLD.authorization_id, OLD.expires_at, NEW.consumed_at;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_ATTEMPT_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.position_exit_attempt_guard_insert()
RETURNS trigger AS $$
DECLARE
    authorization_row public.position_exit_authorization;
BEGIN
    SELECT * INTO authorization_row FROM public.position_exit_authorization
    WHERE authorization_id = NEW.authorization_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'exit attempt % references authorization % which does not exist',
            NEW.attempt_id, NEW.authorization_id;
    END IF;
    IF authorization_row.consumed_at IS NULL THEN
        RAISE EXCEPTION
            'exit attempt % requires authorization % to be consumed in the same transaction',
            NEW.attempt_id, NEW.authorization_id;
    END IF;
    IF authorization_row.consumed_by_attempt_id IS DISTINCT FROM NEW.attempt_id THEN
        RAISE EXCEPTION
            'exit authorization % was consumed by attempt %, not by attempt %',
            NEW.authorization_id, authorization_row.consumed_by_attempt_id, NEW.attempt_id;
    END IF;
    IF authorization_row.entry_intent_governance_id IS DISTINCT FROM NEW.entry_intent_governance_id
        OR authorization_row.request_fingerprint IS DISTINCT FROM NEW.request_fingerprint
        OR authorization_row.client_order_id IS DISTINCT FROM NEW.client_order_id
        OR authorization_row.symbol IS DISTINCT FROM NEW.symbol
        OR authorization_row.quantity IS DISTINCT FROM NEW.quantity
    THEN
        RAISE EXCEPTION
            'exit attempt % does not carry the authorized identity and terms', NEW.attempt_id;
    END IF;
    IF NEW.state <> 'DISPATCH_CLAIMED' THEN
        RAISE EXCEPTION
            'exit attempt % must be inserted as DISPATCH_CLAIMED, not %', NEW.attempt_id, NEW.state;
    END IF;
    IF NEW.closed_position_verified_at IS NOT NULL THEN
        RAISE EXCEPTION
            'exit attempt % cannot be inserted with a verified closed position', NEW.attempt_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_ATTEMPT_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.position_exit_attempt_guard_update()
RETURNS trigger AS $$
DECLARE
    allowed text[];
BEGIN
    IF NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
        OR NEW.entry_intent_governance_id IS DISTINCT FROM OLD.entry_intent_governance_id
        OR NEW.authorization_id IS DISTINCT FROM OLD.authorization_id
        OR NEW.client_order_id IS DISTINCT FROM OLD.client_order_id
        OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
        OR NEW.symbol IS DISTINCT FROM OLD.symbol
        OR NEW.quantity IS DISTINCT FROM OLD.quantity
        OR NEW.claimed_at IS DISTINCT FROM OLD.claimed_at
    THEN
        RAISE EXCEPTION
            'exit attempt % identity is immutable after the dispatch claim', OLD.attempt_id;
    END IF;

    -- The verification of a closed position is set ONCE, never cleared, never changed.
    IF OLD.closed_position_verified_at IS NOT NULL
        AND NEW.closed_position_verified_at IS DISTINCT FROM OLD.closed_position_verified_at
    THEN
        RAISE EXCEPTION
            'exit attempt % already has a verified closed position; it is immutable',
            OLD.attempt_id;
    END IF;

    IF OLD.state IN (__TERMINAL__) THEN
        -- A completed record cannot be rewritten. The ONE permitted change on a FILLED row
        -- is recording the verification that the broker position is zero.
        IF OLD.state = 'FILLED'
            AND NEW.state = 'FILLED'
            AND OLD.closed_position_verified_at IS NULL
            AND NEW.closed_position_verified_at IS NOT NULL
            AND NEW.filled_quantity IS NOT DISTINCT FROM OLD.filled_quantity
            AND NEW.filled_avg_price IS NOT DISTINCT FROM OLD.filled_avg_price
            AND NEW.broker_order_id IS NOT DISTINCT FROM OLD.broker_order_id
            AND NEW.broker_status IS NOT DISTINCT FROM OLD.broker_status
            AND NEW.submitted_at IS NOT DISTINCT FROM OLD.submitted_at
            AND NEW.acknowledged_at IS NOT DISTINCT FROM OLD.acknowledged_at
            AND NEW.terminal_at IS NOT DISTINCT FROM OLD.terminal_at
            AND NEW.failure_code IS NOT DISTINCT FROM OLD.failure_code
            AND NEW.failure_detail IS NOT DISTINCT FROM OLD.failure_detail
        THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION
            'exit attempt % is terminal in state % and cannot be rewritten',
            OLD.attempt_id, OLD.state;
    END IF;

    IF NEW.closed_position_verified_at IS NOT NULL THEN
        RAISE EXCEPTION
            'exit attempt % cannot record a verified closed position before it is FILLED',
            OLD.attempt_id;
    END IF;

    IF NEW.submitted_at IS DISTINCT FROM OLD.submitted_at AND OLD.submitted_at IS NOT NULL THEN
        RAISE EXCEPTION 'exit attempt % submitted_at is written once', OLD.attempt_id;
    END IF;
    IF NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at
        AND OLD.acknowledged_at IS NOT NULL
    THEN
        RAISE EXCEPTION 'exit attempt % acknowledged_at is written once', OLD.attempt_id;
    END IF;

    IF NEW.state = OLD.state THEN
        RETURN NEW;  -- a same-state refresh of what the broker last said
    END IF;

    allowed := CASE OLD.state
        WHEN 'DISPATCH_CLAIMED' THEN
            ARRAY['SUBMISSION_IN_PROGRESS', 'REJECTED', 'EXPIRED']
        WHEN 'SUBMISSION_IN_PROGRESS' THEN
            ARRAY['SUBMITTED', 'SUBMISSION_UNKNOWN', 'REJECTED']
        WHEN 'SUBMITTED' THEN
            ARRAY['ACCEPTED', 'PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED', 'CANCELED',
                  'REJECTED', 'EXPIRED', 'SUBMISSION_UNKNOWN']
        WHEN 'ACCEPTED' THEN
            ARRAY['PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED', 'CANCELED', 'REJECTED',
                  'EXPIRED', 'SUBMISSION_UNKNOWN']
        WHEN 'PARTIALLY_FILLED' THEN
            ARRAY['FILLED', 'CANCEL_REQUESTED', 'CANCELED', 'EXPIRED', 'SUBMISSION_UNKNOWN']
        WHEN 'CANCEL_REQUESTED' THEN
            ARRAY['CANCELED', 'PARTIALLY_FILLED', 'FILLED', 'REJECTED', 'EXPIRED',
                  'SUBMISSION_UNKNOWN']
        WHEN 'SUBMISSION_UNKNOWN' THEN
            ARRAY['SUBMITTED', 'ACCEPTED', 'PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED',
                  'CANCELED', 'REJECTED', 'EXPIRED']
        ELSE ARRAY[]::text[]
    END;

    IF NOT (NEW.state = ANY (allowed)) THEN
        RAISE EXCEPTION
            '% -> % is not an allowed position exit transition for attempt %',
            OLD.state, NEW.state, OLD.attempt_id;
    END IF;

    IF NEW.state IN (__TERMINAL__) AND NEW.terminal_at IS NULL THEN
        RAISE EXCEPTION
            'exit attempt % entering terminal state % requires terminal_at',
            OLD.attempt_id, NEW.state;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
""".replace("__TERMINAL__", _TERMINAL)

_ROUND_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.position_exit_round_guard_insert()
RETURNS trigger AS $$
DECLARE
    attempt_row public.position_exit_attempt;
BEGIN
    SELECT * INTO attempt_row FROM public.position_exit_attempt
    WHERE attempt_id = NEW.attempt_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'exit reconciliation round % names attempt % which does not exist',
            NEW.round_id, NEW.attempt_id;
    END IF;
    IF attempt_row.entry_intent_governance_id IS DISTINCT FROM NEW.entry_intent_governance_id
        OR attempt_row.authorization_id IS DISTINCT FROM NEW.authorization_id
        OR attempt_row.client_order_id IS DISTINCT FROM NEW.client_order_id
    THEN
        RAISE EXCEPTION
            'exit reconciliation round % does not describe attempt %', NEW.round_id, NEW.attempt_id;
    END IF;
    IF NEW.outcome IS NOT NULL OR NEW.completed_at IS NOT NULL
        OR NEW.acknowledgement_sequence IS NOT NULL
        OR NEW.broker_earliest_at IS NOT NULL OR NEW.broker_latest_at IS NOT NULL
    THEN
        RAISE EXCEPTION 'exit reconciliation round % must begin incomplete', NEW.round_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_ROUND_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.position_exit_round_guard_update()
RETURNS trigger AS $$
BEGIN
    IF NEW.round_id IS DISTINCT FROM OLD.round_id
        OR NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
        OR NEW.entry_intent_governance_id IS DISTINCT FROM OLD.entry_intent_governance_id
        OR NEW.authorization_id IS DISTINCT FROM OLD.authorization_id
        OR NEW.client_order_id IS DISTINCT FROM OLD.client_order_id
        OR NEW.account_reference IS DISTINCT FROM OLD.account_reference
        OR NEW.sequence IS DISTINCT FROM OLD.sequence
        OR NEW.started_at IS DISTINCT FROM OLD.started_at
    THEN
        RAISE EXCEPTION 'exit reconciliation round % identity is immutable', OLD.round_id;
    END IF;
    IF OLD.outcome IS NOT NULL THEN
        RAISE EXCEPTION
            'exit reconciliation round % is complete (%) and is immutable',
            OLD.round_id, OLD.outcome;
    END IF;
    IF NEW.outcome IS NULL OR NEW.completed_at IS NULL THEN
        RAISE EXCEPTION
            'exit reconciliation round % may only be updated to a completed outcome', OLD.round_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""


def _create_preview_table() -> None:
    op.create_table(
        _PREVIEW,
        sa.Column("preview_id", sa.String(length=64), primary_key=True),
        sa.Column("entry_intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("entry_attempt_id", sa.String(length=64), nullable=False),
        sa.Column("preview_version", sa.Integer(), nullable=False),
        sa.Column("account_reference", sa.String(length=96), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("limit_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("time_in_force", sa.String(length=8), nullable=False),
        sa.Column("extended_hours", sa.Boolean(), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("position_digest", sa.String(length=64), nullable=False),
        sa.Column("entry_state", sa.String(length=32), nullable=False),
        sa.Column("entry_filled_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("entry_avg_fill_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("exits_filled_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("broker_position_quantity", sa.BigInteger(), nullable=False),
        sa.Column("competing_entry_attempt_ids", sa.Text(), nullable=False),
        sa.Column("position_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quote_bid", sa.Numeric(20, 8), nullable=True),
        sa.Column("quote_ask", sa.Numeric(20, 8), nullable=True),
        sa.Column("quote_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quote_source", sa.String(length=32), nullable=False),
        sa.Column("liquidation_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("binding_fingerprint", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "entry_intent_governance_id", "preview_version", name="uq_position_exit_preview_version"
        ),
        sa.CheckConstraint(_not_blank("preview_id"), name="ck_position_exit_preview_id_present"),
        sa.CheckConstraint(
            "preview_version >= 1", name="ck_position_exit_preview_version_positive"
        ),
        # THE EXIT INVARIANTS AT THE DATABASE BOUNDARY. A preview describing anything but a
        # full close of an existing long, in SIMULATION, as a DAY order in regular hours,
        # cannot be stored, so it cannot be authorized.
        sa.CheckConstraint("side = 'SELL_TO_CLOSE'", name="ck_position_exit_preview_side"),
        sa.CheckConstraint("quantity > 0", name="ck_position_exit_preview_quantity_positive"),
        sa.CheckConstraint(
            "quantity = broker_position_quantity",
            name="ck_position_exit_preview_quantity_equals_broker_position",
        ),
        sa.CheckConstraint(
            "quantity = entry_filled_quantity - exits_filled_quantity",
            name="ck_position_exit_preview_full_close",
        ),
        sa.CheckConstraint(
            "environment = 'SIMULATION'", name="ck_position_exit_preview_environment"
        ),
        sa.CheckConstraint("time_in_force = 'DAY'", name="ck_position_exit_preview_time_in_force"),
        sa.CheckConstraint(
            "extended_hours = false", name="ck_position_exit_preview_no_extended_hours"
        ),
        sa.CheckConstraint(
            "order_type IN ('MARKET', 'LIMIT')", name="ck_position_exit_preview_order_type"
        ),
        sa.CheckConstraint(
            "(order_type = 'LIMIT' AND limit_price IS NOT NULL AND limit_price > 0)"
            " OR (order_type <> 'LIMIT' AND limit_price IS NULL)",
            name="ck_position_exit_preview_limit_price_shape",
        ),
        sa.CheckConstraint(
            "client_order_id LIKE 'm087-%'", name="ck_position_exit_preview_client_order_id_prefix"
        ),
        sa.CheckConstraint(
            f"request_fingerprint {_HEX_DIGEST}",
            name="ck_position_exit_preview_request_fingerprint",
        ),
        sa.CheckConstraint(
            f"position_digest {_HEX_DIGEST}", name="ck_position_exit_preview_position_digest"
        ),
        sa.CheckConstraint(
            f"binding_fingerprint {_HEX_DIGEST}",
            name="ck_position_exit_preview_binding_fingerprint",
        ),
        sa.CheckConstraint(
            "exits_filled_quantity >= 0", name="ck_position_exit_preview_exits_non_negative"
        ),
    )
    op.create_index(f"ix_{_PREVIEW}_entry", _PREVIEW, ["entry_intent_governance_id"])


def _create_authorization_table() -> None:
    op.create_table(
        _AUTHORIZATION,
        sa.Column("authorization_id", sa.String(length=64), primary_key=True),
        sa.Column("entry_intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("preview_id", sa.String(length=64), nullable=False),
        sa.Column("preview_version", sa.Integer(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("preview_binding_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("account_reference", sa.String(length=96), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("authorized_by", sa.String(length=64), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_host_requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_host_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_broker_earliest_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_broker_latest_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_attempt_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["preview_id"],
            [f"{_PREVIEW}.preview_id"],
            name="fk_position_exit_authorization_preview",
        ),
        # ONE authorization per review page shown.
        sa.UniqueConstraint("preview_id", name="uq_position_exit_authorization_one_per_preview"),
        sa.CheckConstraint(
            _not_blank("authorization_id"), name="ck_position_exit_authorization_id_present"
        ),
        sa.CheckConstraint(
            _not_blank("authorized_by"), name="ck_position_exit_authorization_actor_present"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_position_exit_authorization_quantity_positive"),
        sa.CheckConstraint(
            "expires_at > authorized_at", name="ck_position_exit_authorization_expiry_follows"
        ),
        sa.CheckConstraint(
            f"request_fingerprint {_HEX_DIGEST}",
            name="ck_position_exit_authorization_request_fingerprint",
        ),
        sa.CheckConstraint(
            "client_order_id LIKE 'm087-%'",
            name="ck_position_exit_authorization_client_order_id_prefix",
        ),
        sa.CheckConstraint(
            "(consumed_at IS NULL AND consumed_by_attempt_id IS NULL)"
            " OR (consumed_at IS NOT NULL AND consumed_by_attempt_id IS NOT NULL)",
            name="ck_position_exit_authorization_consumption_is_paired",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= authorized_at",
            name="ck_position_exit_authorization_consumed_after_authorized",
        ),
        sa.CheckConstraint(
            "basis_host_at >= basis_host_requested_at "
            "AND basis_broker_latest_at >= basis_broker_earliest_at "
            "AND authorized_at <= basis_host_at",
            name="ck_position_exit_authorization_basis_interval",
        ),
    )
    op.create_index(f"ix_{_AUTHORIZATION}_entry", _AUTHORIZATION, ["entry_intent_governance_id"])


def _create_attempt_table() -> None:
    op.create_table(
        _ATTEMPT,
        sa.Column("attempt_id", sa.String(length=64), primary_key=True),
        sa.Column("entry_intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("authorization_id", sa.String(length=64), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
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
        sa.Column("closed_position_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            [f"{_AUTHORIZATION}.authorization_id"],
            name="fk_position_exit_attempt_authorization",
        ),
        sa.UniqueConstraint("client_order_id", name="uq_position_exit_attempt_client_order_id"),
        sa.UniqueConstraint(
            "authorization_id", name="uq_position_exit_attempt_one_per_authorization"
        ),
        sa.CheckConstraint(_not_blank("attempt_id"), name="ck_position_exit_attempt_id_present"),
        sa.CheckConstraint(f"state IN ({_STATES})", name="ck_position_exit_attempt_state"),
        sa.CheckConstraint("quantity > 0", name="ck_position_exit_attempt_quantity_positive"),
        sa.CheckConstraint(
            f"request_fingerprint {_HEX_DIGEST}",
            name="ck_position_exit_attempt_request_fingerprint",
        ),
        sa.CheckConstraint(
            "client_order_id LIKE 'm087-%'", name="ck_position_exit_attempt_client_order_id_prefix"
        ),
        sa.CheckConstraint(
            f"(state IN ({_TERMINAL}) AND terminal_at IS NOT NULL)"
            f" OR (state NOT IN ({_TERMINAL}) AND terminal_at IS NULL)",
            name="ck_position_exit_attempt_terminal_at_matches_state",
        ),
        # NEVER OVER-SOLD: the filled quantity lies within the authorized quantity.
        sa.CheckConstraint(
            "filled_quantity IS NULL OR (filled_quantity >= 0 AND filled_quantity <= quantity)",
            name="ck_position_exit_attempt_filled_within_quantity",
        ),
        sa.CheckConstraint(
            "closed_position_verified_at IS NULL"
            " OR (state = 'FILLED' AND filled_quantity = quantity)",
            name="ck_position_exit_attempt_closed_requires_full_fill",
        ),
    )
    # AT MOST ONE ACTIVE EXIT IDENTITY PER POSITION. A cancelled, refused or expired exit
    # leaves the position open and a new exit may follow it; an open or filled one forbids
    # any other.
    op.create_index(
        "uq_position_exit_attempt_one_active_per_entry",
        _ATTEMPT,
        ["entry_intent_governance_id"],
        unique=True,
        postgresql_where=sa.text(f"state NOT IN ({_INACTIVE})"),
    )
    op.create_index(f"ix_{_ATTEMPT}_entry", _ATTEMPT, ["entry_intent_governance_id", "claimed_at"])
    op.create_index(f"ix_{_ATTEMPT}_claimed_desc", _ATTEMPT, [sa.text("claimed_at DESC")])


def _create_acknowledgement_table() -> None:
    op.create_table(
        _ACK,
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
            [f"{_ATTEMPT}.attempt_id"],
            name="fk_position_exit_acknowledgement_attempt",
        ),
        sa.UniqueConstraint(
            "attempt_id", "sequence", name="uq_position_exit_acknowledgement_attempt_sequence"
        ),
        sa.CheckConstraint(
            "sequence >= 1", name="ck_position_exit_acknowledgement_sequence_positive"
        ),
        sa.CheckConstraint(
            "kind IN ('SUBMIT', 'RECONCILE', 'CANCEL')",
            name="ck_position_exit_acknowledgement_kind",
        ),
        sa.CheckConstraint(
            f"payload_digest {_HEX_DIGEST}", name="ck_position_exit_acknowledgement_payload_digest"
        ),
        sa.CheckConstraint(
            "length(sanitized_payload) <= 8192",
            name="ck_position_exit_acknowledgement_payload_bounded",
        ),
    )


def _create_round_table() -> None:
    op.create_table(
        _ROUND,
        sa.Column("round_id", sa.String(length=64), primary_key=True),
        sa.Column("attempt_id", sa.String(length=64), nullable=False),
        sa.Column("entry_intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("authorization_id", sa.String(length=64), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("account_reference", sa.String(length=96), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledgement_sequence", sa.Integer(), nullable=True),
        sa.Column("broker_earliest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("broker_latest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["attempt_id"], [f"{_ATTEMPT}.attempt_id"], name="fk_position_exit_round_attempt"
        ),
        sa.UniqueConstraint(
            "attempt_id", "sequence", name="uq_position_exit_round_attempt_sequence"
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_position_exit_round_sequence_positive"),
        sa.CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_OUTCOMES})", name="ck_position_exit_round_outcome"
        ),
        sa.CheckConstraint(
            "(outcome IS NULL) = (completed_at IS NULL)",
            name="ck_position_exit_round_completion_pairs",
        ),
        sa.CheckConstraint(
            "(broker_earliest_at IS NULL) = (broker_latest_at IS NULL)",
            name="ck_position_exit_round_broker_interval_pairs",
        ),
        sa.CheckConstraint(
            "broker_latest_at IS NULL OR broker_latest_at >= broker_earliest_at",
            name="ck_position_exit_round_broker_interval_ordered",
        ),
    )


def _create_event_table() -> None:
    op.create_table(
        _EVENT,
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("entry_intent_governance_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"], [f"{_ATTEMPT}.attempt_id"], name="fk_position_exit_event_attempt"
        ),
        sa.CheckConstraint(_not_blank("event_id"), name="ck_position_exit_event_id_present"),
        sa.CheckConstraint(_not_blank("event_type"), name="ck_position_exit_event_type_present"),
    )
    op.create_index(
        f"ix_{_EVENT}_entry_occurred", _EVENT, ["entry_intent_governance_id", "occurred_at"]
    )


def _trigger(name: str, timing: str, table: str, function: str) -> str:
    return (
        f"CREATE TRIGGER {name} {timing} ON public.{table} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{function}()"
    )


def upgrade() -> None:
    op.execute(_APPEND_ONLY_FUNCTION)
    _create_preview_table()
    _create_authorization_table()
    _create_attempt_table()
    _create_acknowledgement_table()
    _create_round_table()
    _create_event_table()

    op.execute(_PREVIEW_INSERT_FUNCTION)
    op.execute(
        _trigger(
            f"{_PREVIEW}_guard_insert_trigger",
            "BEFORE INSERT",
            _PREVIEW,
            "position_exit_preview_guard_insert",
        )
    )
    op.execute(
        _trigger(
            f"{_PREVIEW}_append_only_trigger",
            "BEFORE UPDATE OR DELETE",
            _PREVIEW,
            "m087_append_only",
        )
    )
    op.execute(_AUTHORIZATION_INSERT_FUNCTION)
    op.execute(
        _trigger(
            f"{_AUTHORIZATION}_guard_insert_trigger",
            "BEFORE INSERT",
            _AUTHORIZATION,
            "position_exit_authorization_guard_insert",
        )
    )
    op.execute(_AUTHORIZATION_UPDATE_FUNCTION)
    op.execute(
        _trigger(
            f"{_AUTHORIZATION}_guard_update_trigger",
            "BEFORE UPDATE",
            _AUTHORIZATION,
            "position_exit_authorization_guard_update",
        )
    )
    op.execute(
        _trigger(
            f"{_AUTHORIZATION}_refuse_delete_trigger",
            "BEFORE DELETE",
            _AUTHORIZATION,
            "m087_append_only",
        )
    )
    op.execute(_ATTEMPT_INSERT_FUNCTION)
    op.execute(
        _trigger(
            f"{_ATTEMPT}_guard_insert_trigger",
            "BEFORE INSERT",
            _ATTEMPT,
            "position_exit_attempt_guard_insert",
        )
    )
    op.execute(_ATTEMPT_UPDATE_FUNCTION)
    op.execute(
        _trigger(
            f"{_ATTEMPT}_guard_update_trigger",
            "BEFORE UPDATE",
            _ATTEMPT,
            "position_exit_attempt_guard_update",
        )
    )
    op.execute(
        _trigger(f"{_ATTEMPT}_refuse_delete_trigger", "BEFORE DELETE", _ATTEMPT, "m087_append_only")
    )
    op.execute(
        _trigger(f"{_ACK}_append_only_trigger", "BEFORE UPDATE OR DELETE", _ACK, "m087_append_only")
    )
    op.execute(_ROUND_INSERT_FUNCTION)
    op.execute(
        _trigger(
            f"{_ROUND}_guard_insert_trigger",
            "AFTER INSERT",
            _ROUND,
            "position_exit_round_guard_insert",
        )
    )
    op.execute(_ROUND_UPDATE_FUNCTION)
    op.execute(
        _trigger(
            f"{_ROUND}_guard_update_trigger",
            "BEFORE UPDATE",
            _ROUND,
            "position_exit_round_guard_update",
        )
    )
    op.execute(
        _trigger(f"{_ROUND}_append_only_trigger", "BEFORE DELETE", _ROUND, "m087_append_only")
    )
    op.execute(
        _trigger(
            f"{_EVENT}_append_only_trigger", "BEFORE UPDATE OR DELETE", _EVENT, "m087_append_only"
        )
    )


def downgrade() -> None:
    # Removes ONLY MILESTONE-087 objects; every M085 and earlier object survives unchanged.
    for table, triggers in (
        (_EVENT, (f"{_EVENT}_append_only_trigger",)),
        (
            _ROUND,
            (
                f"{_ROUND}_append_only_trigger",
                f"{_ROUND}_guard_update_trigger",
                f"{_ROUND}_guard_insert_trigger",
            ),
        ),
        (_ACK, (f"{_ACK}_append_only_trigger",)),
        (
            _ATTEMPT,
            (
                f"{_ATTEMPT}_refuse_delete_trigger",
                f"{_ATTEMPT}_guard_update_trigger",
                f"{_ATTEMPT}_guard_insert_trigger",
            ),
        ),
        (
            _AUTHORIZATION,
            (
                f"{_AUTHORIZATION}_refuse_delete_trigger",
                f"{_AUTHORIZATION}_guard_update_trigger",
                f"{_AUTHORIZATION}_guard_insert_trigger",
            ),
        ),
        (_PREVIEW, (f"{_PREVIEW}_append_only_trigger", f"{_PREVIEW}_guard_insert_trigger")),
    ):
        for trigger in triggers:
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON public.{table}")
    op.drop_table(_EVENT)
    op.drop_table(_ROUND)
    op.drop_table(_ACK)
    op.drop_table(_ATTEMPT)
    op.drop_table(_AUTHORIZATION)
    op.drop_table(_PREVIEW)
    for function in (
        "position_exit_round_guard_update",
        "position_exit_round_guard_insert",
        "position_exit_attempt_guard_update",
        "position_exit_attempt_guard_insert",
        "position_exit_authorization_guard_update",
        "position_exit_authorization_guard_insert",
        "position_exit_preview_guard_insert",
        "m087_append_only",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS public.{function}()")
