"""MILESTONE-085 corrective pass: send-time policy binding and immutable terminal attempts.

WHY THIS EXISTS. The independent review of `754ceda` reproduced, among others:

  D1  the notional cap, quote freshness limit and watchlist reached the dispatch path
      as command-line arguments, unbound to the authorization, so a submit could
      state looser limits than the human authorized;
  P2  a terminal attempt's broker and fill columns could be rewritten by an UPDATE
      that kept the same state;
  P3  nothing in the database compared an authorization with the preview it names.

WHAT IS ADDED.

  paper_submission_preview        records the SEND-TIME POLICY it was judged under --
                                  the configuration version, notional cap, freshness
                                  limit, spread limit, watchlist, prohibited list and
                                  entry window -- plus the intent expiry and the
                                  preview's binding fingerprint. An insert guard
                                  requires the order to be the stored intent's and the
                                  policy to be the stored configuration version's.
  paper_execution_authorization   records copies of what the human was shown. An
                                  insert guard requires every copy to equal the stored
                                  preview, the preview to be authorizable, the row to
                                  be unconsumed, the permission not to outlive the
                                  intent, and the basis not to postdate the preview's
                                  freshness limit. The update guard freezes the new
                                  columns like every other one.
  paper_execution_attempt         the update guard now refuses EVERY update to a
                                  terminal attempt, same-state included, and refuses
                                  rewriting a broker order id, submission instant or
                                  acknowledgement instant once recorded.

NOT BACKFILLED. The new columns are NOT NULL and cannot be derived for a preview or
authorization written before this revision -- that would be manufacturing consent. The
upgrade therefore REFUSES to run while either table holds a row, rather than inventing
values. MILESTONE-083 and MILESTONE-084 tables gain no column, constraint or trigger;
`approved_order_intent` and `operator_trading_configuration` are READ by the guards.

THE PRIOR GUARD TEXTS ARE READ FROM HISTORY. The downgrade restores the attempt update
guard `b1e9d47c30a5` installed and the authorization guard `d4f18a6c2e97` installed,
byte for byte, by loading those revisions' own constants rather than retyping them.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic import op

revision: str = "9c4b2e7d5a18"
down_revision: str | None = "e61b3f9a4c27"
branch_labels: str | None = None
depends_on: str | None = None

_PREVIEW = "paper_submission_preview"
_AUTHORIZATION = "paper_execution_authorization"
_TERMINAL_STATES = "'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED'"


def _history(stem: str) -> ModuleType:
    """Load an earlier revision's module for its frozen SQL constants."""
    path = Path(__file__).with_name(f"{stem}.py")
    spec = importlib.util.spec_from_file_location(f"_m085_history_{stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"migration history {stem} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PREVIEW_POLICY_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_submission_preview_guard_policy()
RETURNS trigger AS $$
DECLARE
    intent_row public.approved_order_intent;
    configuration_row public.operator_trading_configuration;
BEGIN
    SELECT * INTO intent_row
    FROM public.approved_order_intent
    WHERE intent_governance_id = NEW.intent_governance_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            '% references approved order intent % which does not exist',
            TG_TABLE_NAME, NEW.intent_governance_id;
    END IF;

    -- The order a human will be shown is the approved intent's, exactly.
    IF intent_row.configuration_governance_id IS DISTINCT FROM NEW.configuration_governance_id
        OR intent_row.configuration_version IS DISTINCT FROM NEW.configuration_version
        OR intent_row.approved_fingerprint IS DISTINCT FROM NEW.approved_fingerprint
        OR intent_row.expires_at IS DISTINCT FROM NEW.intent_expires_at
        OR intent_row.symbol IS DISTINCT FROM NEW.symbol
        OR intent_row.side IS DISTINCT FROM NEW.side
        OR intent_row.quantity IS DISTINCT FROM NEW.quantity
        OR intent_row.order_type IS DISTINCT FROM NEW.order_type
        OR intent_row.limit_price IS DISTINCT FROM NEW.limit_price
    THEN
        RAISE EXCEPTION
            'preview % does not describe the exact approved intent %',
            NEW.preview_id, NEW.intent_governance_id;
    END IF;

    SELECT * INTO configuration_row
    FROM public.operator_trading_configuration
    WHERE configuration_governance_id = NEW.configuration_governance_id
      AND configuration_version = NEW.configuration_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'preview % names configuration % version % which does not exist',
            NEW.preview_id, NEW.configuration_governance_id, NEW.configuration_version;
    END IF;

    -- The limits are the configuration version's, never a caller's.
    IF configuration_row.maximum_capital_per_trade IS DISTINCT FROM NEW.maximum_notional
        OR configuration_row.maximum_market_data_age_seconds
            IS DISTINCT FROM NEW.quote_maximum_age_seconds
        OR configuration_row.maximum_spread_percent IS DISTINCT FROM NEW.maximum_spread_percent
        OR configuration_row.earliest_entry_time IS DISTINCT FROM NEW.earliest_entry_time
        OR configuration_row.latest_entry_time IS DISTINCT FROM NEW.latest_entry_time
        OR configuration_row.operator_timezone IS DISTINCT FROM NEW.operator_timezone
        OR NOT (NEW.policy_watchlist @> configuration_row.watchlist
                AND NEW.policy_watchlist <@ configuration_row.watchlist)
        OR NOT (NEW.policy_prohibited_instruments @> configuration_row.prohibited_instruments
                AND NEW.policy_prohibited_instruments <@ configuration_row.prohibited_instruments)
    THEN
        RAISE EXCEPTION
            'preview % does not carry the send-time policy of configuration % version %',
            NEW.preview_id, NEW.configuration_governance_id, NEW.configuration_version;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_AUTHORIZATION_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_execution_authorization_guard_insert()
RETURNS trigger AS $$
DECLARE
    preview_row public.paper_submission_preview;
BEGIN
    -- Consumption is an UPDATE this table permits exactly once. A row inserted
    -- already consumed would skip that guard and its expiry check entirely.
    IF NEW.consumed_at IS NOT NULL OR NEW.consumed_by_attempt_id IS NOT NULL THEN
        RAISE EXCEPTION
            'authorization % must be inserted unconsumed',
            NEW.authorization_id;
    END IF;

    SELECT * INTO preview_row
    FROM public.paper_submission_preview
    WHERE preview_id = NEW.preview_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'authorization % names preview % which does not exist',
            NEW.authorization_id, NEW.preview_id;
    END IF;

    IF preview_row.refusals <> '[]' THEN
        RAISE EXCEPTION
            'preview % carries refusals and cannot be authorized',
            NEW.preview_id;
    END IF;

    -- Every field the human consented to is the stored preview's.
    IF preview_row.intent_governance_id IS DISTINCT FROM NEW.intent_governance_id
        OR preview_row.preview_version IS DISTINCT FROM NEW.preview_version
        OR preview_row.request_fingerprint IS DISTINCT FROM NEW.request_fingerprint
        OR preview_row.account_reference IS DISTINCT FROM NEW.account_reference
        OR preview_row.client_order_id IS DISTINCT FROM NEW.client_order_id
        OR preview_row.symbol IS DISTINCT FROM NEW.symbol
        OR preview_row.side IS DISTINCT FROM NEW.side
        OR preview_row.quantity IS DISTINCT FROM NEW.quantity
        OR preview_row.order_type IS DISTINCT FROM NEW.order_type
        OR preview_row.limit_price IS DISTINCT FROM NEW.limit_price
        OR preview_row.maximum_notional IS DISTINCT FROM NEW.maximum_notional
        OR preview_row.quote_bid IS DISTINCT FROM NEW.quote_bid
        OR preview_row.quote_ask IS DISTINCT FROM NEW.quote_ask
        OR preview_row.quote_captured_at IS DISTINCT FROM NEW.quote_captured_at
        OR preview_row.configuration_governance_id IS DISTINCT FROM NEW.configuration_governance_id
        OR preview_row.configuration_version IS DISTINCT FROM NEW.configuration_version
        OR preview_row.policy_fingerprint IS DISTINCT FROM NEW.policy_fingerprint
        OR preview_row.binding_fingerprint IS DISTINCT FROM NEW.preview_binding_fingerprint
    THEN
        RAISE EXCEPTION
            'authorization % does not describe preview %',
            NEW.authorization_id, NEW.preview_id;
    END IF;

    IF NEW.expires_at > preview_row.intent_expires_at THEN
        RAISE EXCEPTION
            'authorization % would outlive the approved intent of preview %',
            NEW.authorization_id, NEW.preview_id;
    END IF;

    IF NEW.basis_host_at IS NOT NULL
        AND NEW.basis_host_at > preview_row.created_at
            + make_interval(secs => preview_row.quote_maximum_age_seconds)
    THEN
        RAISE EXCEPTION
            'authorization % was granted on preview % after its quote freshness limit',
            NEW.authorization_id, NEW.preview_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_AUTHORIZATION_GUARD_BINDING_COLUMNS = """\
        OR NEW.symbol IS DISTINCT FROM OLD.symbol
        OR NEW.side IS DISTINCT FROM OLD.side
        OR NEW.quantity IS DISTINCT FROM OLD.quantity
        OR NEW.order_type IS DISTINCT FROM OLD.order_type
        OR NEW.limit_price IS DISTINCT FROM OLD.limit_price
        OR NEW.maximum_notional IS DISTINCT FROM OLD.maximum_notional
        OR NEW.quote_bid IS DISTINCT FROM OLD.quote_bid
        OR NEW.quote_ask IS DISTINCT FROM OLD.quote_ask
        OR NEW.quote_captured_at IS DISTINCT FROM OLD.quote_captured_at
        OR NEW.configuration_governance_id IS DISTINCT FROM OLD.configuration_governance_id
        OR NEW.configuration_version IS DISTINCT FROM OLD.configuration_version
        OR NEW.policy_fingerprint IS DISTINCT FROM OLD.policy_fingerprint
        OR NEW.preview_binding_fingerprint IS DISTINCT FROM OLD.preview_binding_fingerprint
"""

_ATTEMPT_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_execution_attempt_guard_update()
RETURNS trigger AS $$
DECLARE
    allowed text[];
BEGIN
    -- Identity is fixed at claim time.
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

    -- CORRECTIVE PASS (P2). A terminal attempt is the record of what happened and
    -- is immutable in full. SUPERSEDED: a same-state UPDATE was permitted even on a
    -- terminal row, so its broker order id and fills could be rewritten.
    IF OLD.state IN (__TERMINAL__) THEN
        RAISE EXCEPTION
            'attempt % is terminal in state % and is immutable',
            OLD.attempt_id, OLD.state;
    END IF;

    -- What the broker identified, and when this product sent and heard, is written
    -- once. Refreshing a non-terminal attempt may add these, never replace them.
    IF (OLD.broker_order_id IS NOT NULL
            AND NEW.broker_order_id IS DISTINCT FROM OLD.broker_order_id)
        OR (OLD.submitted_at IS NOT NULL
            AND NEW.submitted_at IS DISTINCT FROM OLD.submitted_at)
        OR (OLD.acknowledged_at IS NOT NULL
            AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at)
    THEN
        RAISE EXCEPTION
            'attempt % may not rewrite a broker order id or instant already recorded',
            OLD.attempt_id;
    END IF;

    IF NEW.state = OLD.state THEN
        RETURN NEW;
    END IF;

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

#: Executed by the database itself, so the refusal holds for an online upgrade and for
#: SQL rendered offline and applied later alike.
_REFUSE_TO_BACKFILL = """
DO $refuse$
BEGIN
    IF EXISTS (SELECT 1 FROM public.paper_submission_preview)
        OR EXISTS (SELECT 1 FROM public.paper_execution_authorization)
    THEN
        RAISE EXCEPTION
            'previews or authorizations exist; their send-time policy and preview binding '
            'cannot be derived after the fact, so this revision refuses to invent them';
    END IF;
END
$refuse$
"""


def upgrade() -> None:
    op.execute(_REFUSE_TO_BACKFILL)

    for column in (
        sa.Column("configuration_governance_id", sa.String(length=64), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("policy_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("maximum_notional", sa.Numeric(20, 8), nullable=False),
        sa.Column("quote_maximum_age_seconds", sa.Integer(), nullable=False),
        sa.Column("maximum_spread_percent", sa.Numeric(20, 8), nullable=False),
        sa.Column("policy_watchlist", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("policy_prohibited_instruments", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("earliest_entry_time", sa.Time(), nullable=False),
        sa.Column("latest_entry_time", sa.Time(), nullable=False),
        sa.Column("operator_timezone", sa.String(length=64), nullable=False),
        sa.Column("intent_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("binding_fingerprint", sa.String(length=64), nullable=False),
    ):
        op.add_column(_PREVIEW, column)
    for name, condition in (
        ("ck_paper_preview_policy_fingerprint", "policy_fingerprint ~ '^[0-9a-f]{64}$'"),
        ("ck_paper_preview_binding_fingerprint", "binding_fingerprint ~ '^[0-9a-f]{64}$'"),
        ("ck_paper_preview_notional_cap_positive", "maximum_notional > 0"),
        ("ck_paper_preview_quote_age_positive", "quote_maximum_age_seconds > 0"),
        ("ck_paper_preview_spread_limit_non_negative", "maximum_spread_percent >= 0"),
        ("ck_paper_preview_entry_window_ordered", "earliest_entry_time < latest_entry_time"),
        # Scoped to a priced LIMIT order so it never overlaps the order-type and
        # limit-shape CHECKs of `b1e9d47c30a5`: PostgreSQL evaluates CHECKs in name
        # order, and an overlapping rule here would report itself in their place.
        (
            "ck_paper_preview_authorizable_within_cap",
            "refusals <> '[]' OR order_type <> 'LIMIT' OR limit_price IS NULL "
            "OR limit_price * quantity <= maximum_notional",
        ),
    ):
        op.create_check_constraint(name, _PREVIEW, condition)

    for column in (
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("limit_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("maximum_notional", sa.Numeric(20, 8), nullable=False),
        sa.Column("quote_bid", sa.Numeric(20, 8), nullable=True),
        sa.Column("quote_ask", sa.Numeric(20, 8), nullable=True),
        sa.Column("quote_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("configuration_governance_id", sa.String(length=64), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("policy_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("preview_binding_fingerprint", sa.String(length=64), nullable=False),
    ):
        op.add_column(_AUTHORIZATION, column)
    op.create_check_constraint(
        "ck_paper_authorization_policy_fingerprint",
        _AUTHORIZATION,
        "policy_fingerprint ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_paper_authorization_binding_fingerprint",
        _AUTHORIZATION,
        "preview_binding_fingerprint ~ '^[0-9a-f]{64}$'",
    )

    # AFTER INSERT, deliberately. PostgreSQL evaluates CHECK and NOT NULL constraints
    # after BEFORE triggers, so a BEFORE guard would mask the earlier milestones'
    # constraints with its own message. Run after them, it adds refusals without
    # hiding any; an exception raised here still aborts the INSERT.
    op.execute(_PREVIEW_POLICY_FUNCTION)
    op.execute(
        "CREATE TRIGGER paper_submission_preview_guard_policy_trigger "
        "AFTER INSERT ON public.paper_submission_preview "
        "FOR EACH ROW EXECUTE FUNCTION public.paper_submission_preview_guard_policy()"
    )
    op.execute(_AUTHORIZATION_INSERT_FUNCTION)
    op.execute(
        "CREATE TRIGGER paper_execution_authorization_guard_insert_trigger "
        "AFTER INSERT ON public.paper_execution_authorization "
        "FOR EACH ROW EXECUTE FUNCTION public.paper_execution_authorization_guard_insert()"
    )

    basis = _history("d4f18a6c2e97_add_m085_intent_time_basis")
    op.execute(
        basis._AUTHORIZATION_GUARD_PREFIX
        + basis._AUTHORIZATION_GUARD_BASIS_COLUMNS
        + _AUTHORIZATION_GUARD_BINDING_COLUMNS
        + basis._AUTHORIZATION_GUARD_SUFFIX
    )
    op.execute(_ATTEMPT_UPDATE_FUNCTION)


def downgrade() -> None:
    schema = _history("b1e9d47c30a5_create_m085_paper_execution_schema")
    basis = _history("d4f18a6c2e97_add_m085_intent_time_basis")
    op.execute(schema._ATTEMPT_UPDATE_FUNCTION)
    op.execute(basis._AUTHORIZATION_GUARD_WITH_BASIS)

    op.execute(
        "DROP TRIGGER IF EXISTS paper_execution_authorization_guard_insert_trigger "
        "ON public.paper_execution_authorization"
    )
    op.execute("DROP FUNCTION IF EXISTS public.paper_execution_authorization_guard_insert()")
    op.execute(
        "DROP TRIGGER IF EXISTS paper_submission_preview_guard_policy_trigger "
        "ON public.paper_submission_preview"
    )
    op.execute("DROP FUNCTION IF EXISTS public.paper_submission_preview_guard_policy()")

    for name in (
        "ck_paper_authorization_binding_fingerprint",
        "ck_paper_authorization_policy_fingerprint",
    ):
        op.drop_constraint(name, _AUTHORIZATION, type_="check")
    for column_name in (
        "preview_binding_fingerprint",
        "policy_fingerprint",
        "configuration_version",
        "configuration_governance_id",
        "quote_captured_at",
        "quote_ask",
        "quote_bid",
        "maximum_notional",
        "limit_price",
        "order_type",
        "quantity",
        "side",
        "symbol",
    ):
        op.drop_column(_AUTHORIZATION, column_name)

    for name in (
        "ck_paper_preview_authorizable_within_cap",
        "ck_paper_preview_entry_window_ordered",
        "ck_paper_preview_spread_limit_non_negative",
        "ck_paper_preview_quote_age_positive",
        "ck_paper_preview_notional_cap_positive",
        "ck_paper_preview_binding_fingerprint",
        "ck_paper_preview_policy_fingerprint",
    ):
        op.drop_constraint(name, _PREVIEW, type_="check")
    for column_name in (
        "binding_fingerprint",
        "intent_expires_at",
        "operator_timezone",
        "latest_entry_time",
        "earliest_entry_time",
        "policy_prohibited_instruments",
        "policy_watchlist",
        "maximum_spread_percent",
        "quote_maximum_age_seconds",
        "maximum_notional",
        "policy_fingerprint",
        "configuration_version",
        "configuration_governance_id",
    ):
        op.drop_column(_PREVIEW, column_name)
