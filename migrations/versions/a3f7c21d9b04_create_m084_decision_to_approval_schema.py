"""MILESTONE-084 decision-to-approval product core schema.

ADDITIVE ONLY. No table, trigger, function, column or row belonging to any
earlier milestone is touched. `evaluation_evidence_watermark` (M083) and
`operator_event_receipt` (M082) are READ by the constraints below and never
written.

THE CLAIM, AND ONLY THIS. These tables record, durably and in a form the
database itself refuses to corrupt:

  - which versioned operator configuration governed one evaluation;
  - which persisted input identities -- including exactly one M083 watermark --
    that evaluation consumed;
  - the exact order terms of one proposal, and the digest of those terms;
  - one explicit human decision about that one proposal version;
  - at most one approved order intent per proposal, which is NOT_SUBMITTED and
    for which this milestone provides no transition away from NOT_SUBMITTED.

WHAT IT DOES NOT CLAIM. Nothing here asserts that a proposal was profitable,
fillable, or acceptable to any broker; that the M082 receipts behind the
watermark describe anything historically true; or that an order was, could be,
or ever will be sent. MILESTONE-084 has no order-submission capability at all --
see the package-wide architecture rule in `tools/check_architecture.py`.

WHY TRIGGERS AND NOT APPLICATION CHECKS. The domain layer refuses all of the
same states, but application code is one import away from being bypassed by a
direct SQL statement, a psql session, or a future repository written in a
hurry. Every rule below that would let a human approve one order and end up
with a different one is therefore enforced at the database boundary as well.

THE FOUR HARD PRODUCT INVARIANTS ARE CHECK CONSTRAINTS, NOT DEFAULTS. Leverage
exactly 1, short selling forbidden, overnight positions forbidden, account mode
PREPARATION. A row expressing any other policy cannot be stored, so there is no
configuration in this database that a future milestone could load and act on.

THE PROPOSAL STATE MACHINE IS CLOSED AND ENFORCED ON UPDATE. Only PREPARED has
outgoing edges (to APPROVED, REJECTED, CANCELLED, EXPIRED, INVALIDATED). Every
other status is terminal. The BEFORE UPDATE trigger additionally refuses any
change to a proposal's ORDER TERMS: only `status` may ever change after insert.
That is what makes the approval fingerprint binding durable rather than
advisory -- the terms a human approved cannot be edited underneath the
approval, so a stale approval cannot come to authorize a different order.

ONE DECISION PER PROPOSAL, ONE INTENT PER PROPOSAL. Both are UNIQUE
constraints, not application conventions. A decision may only be recorded
against a proposal that is still PREPARED and whose fingerprint matches the one
being approved; an intent may only be created for a proposal that is APPROVED,
from an APPROVE decision belonging to that same proposal version, with all
three fingerprints equal. There is no path to an intent through the absence of
a rejection, and no decision row that can cover more than one proposal.

IMMUTABILITY, THE SAME NARROW SHAPE AS M082 AND M083. The decision and intent
tables carry BEFORE UPDATE OR DELETE row triggers that refuse both operations
unconditionally. That is ROW-LEVEL UPDATE/DELETE IMMUTABILITY UNDER THE
INSTALLED TRIGGERS ONLY: TRUNCATE is statement-level and not intercepted by a
row trigger, and DROP TRIGGER, DROP TABLE, ALTER TABLE ... DISABLE TRIGGER,
`session_replication_role = replica` and superuser mutation all remain
possible. This must not be described as absolute database immutability.

BLANK IDENTITY. Identity columns use the identical frozen 29-character Python
3.13 `str.strip()` blank set that M082's and M083's migrations froze locally,
reproduced here rather than imported, because a migration is history and must
not depend on mutable application code.

Revision ID: a3f7c21d9b04
Revises: 9e4e647347ad
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a3f7c21d9b04"
down_revision: str | None = "9e4e647347ad"
branch_labels: None = None
depends_on: None = None

# FROZEN LITERAL, reproduced from M082/M083 rather than imported -- see the
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

_PROPOSAL_STATUSES = "'PREPARED', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED', 'INVALIDATED'"

# ---------------------------------------------------------------------------
# Shared immutability trigger function
# ---------------------------------------------------------------------------

_IMMUTABLE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.m084_append_only()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

# ---------------------------------------------------------------------------
# The proposal state machine and term immutability
# ---------------------------------------------------------------------------

# Only `status` may change, and only along a permitted edge. Comparing the row
# field by field rather than comparing OLD to NEW wholesale is deliberate: a
# wholesale comparison would silently start permitting any column added later.
_PROPOSAL_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.trade_proposal_guard_update()
RETURNS trigger AS $$
BEGIN
    IF NEW.proposal_governance_id IS DISTINCT FROM OLD.proposal_governance_id
        OR NEW.proposal_version IS DISTINCT FROM OLD.proposal_version
        OR NEW.evaluation_context_id IS DISTINCT FROM OLD.evaluation_context_id
        OR NEW.configuration_governance_id IS DISTINCT FROM OLD.configuration_governance_id
        OR NEW.configuration_version IS DISTINCT FROM OLD.configuration_version
        OR NEW.symbol IS DISTINCT FROM OLD.symbol
        OR NEW.side IS DISTINCT FROM OLD.side
        OR NEW.quantity IS DISTINCT FROM OLD.quantity
        OR NEW.order_type IS DISTINCT FROM OLD.order_type
        OR NEW.limit_price IS DISTINCT FROM OLD.limit_price
        OR NEW.currency IS DISTINCT FROM OLD.currency
        OR NEW.estimated_notional IS DISTINCT FROM OLD.estimated_notional
        OR NEW.estimated_fees IS DISTINCT FROM OLD.estimated_fees
        OR NEW.estimated_slippage_amount IS DISTINCT FROM OLD.estimated_slippage_amount
        OR NEW.estimated_total_cash_required IS DISTINCT FROM OLD.estimated_total_cash_required
        OR NEW.stop_loss_price IS DISTINCT FROM OLD.stop_loss_price
        OR NEW.profit_exit_price IS DISTINCT FROM OLD.profit_exit_price
        OR NEW.mandatory_liquidation_at IS DISTINCT FROM OLD.mandatory_liquidation_at
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
        OR NEW.content_fingerprint IS DISTINCT FROM OLD.content_fingerprint
    THEN
        RAISE EXCEPTION
            'trade_proposal order terms are immutable: only status may change';
    END IF;

    IF NEW.status = OLD.status THEN
        RETURN NEW;
    END IF;

    IF OLD.status <> 'PREPARED' THEN
        RAISE EXCEPTION
            'trade_proposal % is terminal: % -> % is not an allowed transition',
            OLD.proposal_governance_id, OLD.status, NEW.status;
    END IF;

    IF NEW.status NOT IN ('APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED', 'INVALIDATED') THEN
        RAISE EXCEPTION
            'trade_proposal % -> % is not an allowed transition',
            OLD.status, NEW.status;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_PROPOSAL_UPDATE_TRIGGER = """
CREATE TRIGGER trade_proposal_guard_update_trigger
BEFORE UPDATE ON public.trade_proposal
FOR EACH ROW EXECUTE FUNCTION public.trade_proposal_guard_update()
"""

# A proposal is history once it exists. Deleting one would orphan the decision
# and intent that cite it, and would erase the record of what was proposed.
_PROPOSAL_DELETE_TRIGGER = """
CREATE TRIGGER trade_proposal_refuse_delete_trigger
BEFORE DELETE ON public.trade_proposal
FOR EACH ROW EXECUTE FUNCTION public.m084_append_only()
"""

# ---------------------------------------------------------------------------
# Decision admission
# ---------------------------------------------------------------------------

# The decision must be about a proposal that is STILL PREPARED and must carry
# that proposal's CURRENT fingerprint. Both are read here, inside the database,
# rather than trusted from the caller: a caller that had to be trusted for this
# could record an approval of terms nobody was shown.
_DECISION_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.trade_approval_decision_guard_insert()
RETURNS trigger AS $$
DECLARE
    proposal_status text;
    proposal_fingerprint text;
    proposal_version_stored integer;
BEGIN
    SELECT p.status, p.content_fingerprint, p.proposal_version
      INTO proposal_status, proposal_fingerprint, proposal_version_stored
      FROM public.trade_proposal p
     WHERE p.proposal_governance_id = NEW.proposal_governance_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'no such proposal: %', NEW.proposal_governance_id;
    END IF;

    IF proposal_status <> 'PREPARED' THEN
        RAISE EXCEPTION
            'proposal % is %, and a decision may only be recorded while it is PREPARED',
            NEW.proposal_governance_id, proposal_status;
    END IF;

    IF NEW.proposal_version <> proposal_version_stored THEN
        RAISE EXCEPTION
            'decision cites proposal version %, but the stored proposal is version %',
            NEW.proposal_version, proposal_version_stored;
    END IF;

    IF NEW.approved_fingerprint <> proposal_fingerprint THEN
        RAISE EXCEPTION
            'decision fingerprint does not match the proposal it decides';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_DECISION_INSERT_TRIGGER = """
CREATE TRIGGER trade_approval_decision_guard_insert_trigger
BEFORE INSERT ON public.trade_approval_decision
FOR EACH ROW EXECUTE FUNCTION public.trade_approval_decision_guard_insert()
"""

_DECISION_IMMUTABLE_TRIGGER = """
CREATE TRIGGER trade_approval_decision_append_only_trigger
BEFORE UPDATE OR DELETE ON public.trade_approval_decision
FOR EACH ROW EXECUTE FUNCTION public.m084_append_only()
"""

# ---------------------------------------------------------------------------
# Intent admission
# ---------------------------------------------------------------------------

# Everything an intent claims is re-derived from the two rows it cites. An
# intent that disagrees with either of them by one field is refused rather than
# stored and reconciled later.
_INTENT_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.approved_order_intent_guard_insert()
RETURNS trigger AS $$
DECLARE
    p public.trade_proposal%ROWTYPE;
    d public.trade_approval_decision%ROWTYPE;
BEGIN
    SELECT * INTO p
      FROM public.trade_proposal
     WHERE proposal_governance_id = NEW.proposal_governance_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such proposal: %', NEW.proposal_governance_id;
    END IF;

    SELECT * INTO d
      FROM public.trade_approval_decision
     WHERE decision_governance_id = NEW.decision_governance_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such decision: %', NEW.decision_governance_id;
    END IF;

    IF d.proposal_governance_id <> NEW.proposal_governance_id THEN
        RAISE EXCEPTION
            'decision % does not belong to proposal %',
            NEW.decision_governance_id, NEW.proposal_governance_id;
    END IF;

    IF d.action <> 'APPROVE' THEN
        RAISE EXCEPTION
            'an order intent requires an APPROVE decision, not %', d.action;
    END IF;

    IF p.status <> 'APPROVED' THEN
        RAISE EXCEPTION
            'proposal % is %, not APPROVED', NEW.proposal_governance_id, p.status;
    END IF;

    IF NEW.approved_fingerprint <> p.content_fingerprint
        OR NEW.approved_fingerprint <> d.approved_fingerprint THEN
        RAISE EXCEPTION
            'the approved fingerprint does not match both the proposal and the decision';
    END IF;

    IF NEW.proposal_version <> p.proposal_version
        OR NEW.proposal_version <> d.proposal_version THEN
        RAISE EXCEPTION
            'the intent cites a different proposal version than the proposal or decision';
    END IF;

    IF NEW.symbol <> p.symbol
        OR NEW.side <> p.side
        OR NEW.quantity <> p.quantity
        OR NEW.order_type <> p.order_type
        OR NEW.limit_price IS DISTINCT FROM p.limit_price
        OR NEW.currency <> p.currency
        OR NEW.mandatory_liquidation_at <> p.mandatory_liquidation_at THEN
        RAISE EXCEPTION
            'the intent order terms differ from the proposal that was approved';
    END IF;

    IF d.expires_at IS NULL OR NEW.created_at >= d.expires_at THEN
        RAISE EXCEPTION
            'the approval had lapsed when the intent was created';
    END IF;

    IF NEW.created_at >= p.expires_at THEN
        RAISE EXCEPTION
            'the proposal had expired when the intent was created';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_INTENT_INSERT_TRIGGER = """
CREATE TRIGGER approved_order_intent_guard_insert_trigger
BEFORE INSERT ON public.approved_order_intent
FOR EACH ROW EXECUTE FUNCTION public.approved_order_intent_guard_insert()
"""

_INTENT_IMMUTABLE_TRIGGER = """
CREATE TRIGGER approved_order_intent_append_only_trigger
BEFORE UPDATE OR DELETE ON public.approved_order_intent
FOR EACH ROW EXECUTE FUNCTION public.m084_append_only()
"""


def upgrade() -> None:
    _create_configuration_table()
    _create_evaluation_context_table()
    _create_proposal_table()
    _create_decision_table()
    _create_intent_table()

    op.execute(_IMMUTABLE_FUNCTION)
    op.execute(_PROPOSAL_UPDATE_FUNCTION)
    op.execute(_PROPOSAL_UPDATE_TRIGGER)
    op.execute(_PROPOSAL_DELETE_TRIGGER)
    op.execute(_DECISION_INSERT_FUNCTION)
    op.execute(_DECISION_INSERT_TRIGGER)
    op.execute(_DECISION_IMMUTABLE_TRIGGER)
    op.execute(_INTENT_INSERT_FUNCTION)
    op.execute(_INTENT_INSERT_TRIGGER)
    op.execute(_INTENT_IMMUTABLE_TRIGGER)


def _create_configuration_table() -> None:
    op.create_table(
        "operator_trading_configuration",
        sa.Column("configuration_governance_id", sa.String(length=64), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("permitted_markets", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("watchlist", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("prohibited_instruments", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("maximum_deployable_capital", sa.Numeric(20, 8), nullable=False),
        sa.Column("maximum_capital_per_trade", sa.Numeric(20, 8), nullable=False),
        sa.Column("maximum_percent_per_trade", sa.Numeric(20, 8), nullable=False),
        sa.Column("minimum_cash_reserve", sa.Numeric(20, 8), nullable=False),
        sa.Column("maximum_simultaneous_positions", sa.Integer(), nullable=False),
        sa.Column("maximum_daily_loss", sa.Numeric(20, 8), nullable=False),
        sa.Column("maximum_daily_order_count", sa.Integer(), nullable=False),
        sa.Column("minimum_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("maximum_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("minimum_liquidity_shares", sa.BigInteger(), nullable=False),
        sa.Column("maximum_spread_percent", sa.Numeric(20, 8), nullable=False),
        sa.Column("maximum_estimated_slippage_percent", sa.Numeric(20, 8), nullable=False),
        sa.Column("maximum_evidence_age_seconds", sa.Integer(), nullable=False),
        sa.Column("maximum_market_data_age_seconds", sa.Integer(), nullable=False),
        sa.Column("permitted_session", sa.String(length=16), nullable=False),
        sa.Column("earliest_entry_time", sa.Time(), nullable=False),
        sa.Column("latest_entry_time", sa.Time(), nullable=False),
        sa.Column("mandatory_liquidation_time", sa.Time(), nullable=False),
        sa.Column("operator_timezone", sa.String(length=64), nullable=False),
        sa.Column("exchange_calendar_policy", sa.String(length=64), nullable=False),
        sa.Column("proposal_expiry_seconds", sa.Integer(), nullable=False),
        sa.Column("approval_expiry_seconds", sa.Integer(), nullable=False),
        sa.Column("default_order_type", sa.String(length=16), nullable=False),
        sa.Column("permitted_order_types", sa.ARRAY(sa.String(length=16)), nullable=False),
        sa.Column("limit_price_policy", sa.String(length=16), nullable=False),
        sa.Column("stop_loss_percent", sa.Numeric(20, 8), nullable=False),
        sa.Column("profit_exit_percent", sa.Numeric(20, 8), nullable=False),
        sa.Column("maximum_leverage", sa.Numeric(20, 8), nullable=False),
        sa.Column("short_selling_permitted", sa.Boolean(), nullable=False),
        sa.Column("overnight_positions_permitted", sa.Boolean(), nullable=False),
        sa.Column("account_mode", sa.String(length=16), nullable=False),
        sa.Column("kill_switch", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint(
            "configuration_governance_id",
            "configuration_version",
            name="pk_operator_trading_configuration",
        ),
        sa.CheckConstraint(
            _not_blank("configuration_governance_id"),
            name="ck_operator_trading_configuration_id_present",
        ),
        sa.CheckConstraint(
            "configuration_version >= 1",
            name="ck_operator_trading_configuration_version_positive",
        ),
        # --- the four hard product invariants ---------------------------
        sa.CheckConstraint(
            "maximum_leverage = 1",
            name="ck_operator_trading_configuration_unleveraged",
        ),
        sa.CheckConstraint(
            "short_selling_permitted = false",
            name="ck_operator_trading_configuration_long_only",
        ),
        sa.CheckConstraint(
            "overnight_positions_permitted = false",
            name="ck_operator_trading_configuration_intraday_only",
        ),
        sa.CheckConstraint(
            "account_mode = 'PREPARATION'",
            name="ck_operator_trading_configuration_preparation_only",
        ),
        # --- closed enumerations -----------------------------------------
        sa.CheckConstraint(
            "permitted_session = 'REGULAR'",
            name="ck_operator_trading_configuration_regular_session_only",
        ),
        sa.CheckConstraint(
            "kill_switch IN ('DISENGAGED', 'ENGAGED')",
            name="ck_operator_trading_configuration_kill_switch",
        ),
        sa.CheckConstraint(
            "default_order_type IN ('MARKET', 'LIMIT')",
            name="ck_operator_trading_configuration_default_order_type",
        ),
        sa.CheckConstraint(
            "limit_price_policy IN ('LAST_TRADE', 'MID_QUOTE', 'ASK')",
            name="ck_operator_trading_configuration_limit_price_policy",
        ),
        # --- ordering and range ------------------------------------------
        sa.CheckConstraint(
            "approval_expiry_seconds <= proposal_expiry_seconds",
            name="ck_operator_trading_configuration_approval_within_proposal",
        ),
        sa.CheckConstraint(
            "earliest_entry_time < latest_entry_time",
            name="ck_operator_trading_configuration_entry_window_ordered",
        ),
        sa.CheckConstraint(
            "mandatory_liquidation_time > latest_entry_time",
            name="ck_operator_trading_configuration_liquidation_after_entry",
        ),
        sa.CheckConstraint(
            "maximum_capital_per_trade <= maximum_deployable_capital",
            name="ck_operator_trading_configuration_per_trade_within_deployable",
        ),
        sa.CheckConstraint(
            "minimum_cash_reserve < maximum_deployable_capital",
            name="ck_operator_trading_configuration_reserve_leaves_capital",
        ),
        sa.CheckConstraint(
            "maximum_percent_per_trade > 0 AND maximum_percent_per_trade <= 100",
            name="ck_operator_trading_configuration_percent_per_trade_range",
        ),
        sa.CheckConstraint(
            "proposal_expiry_seconds > 0 AND approval_expiry_seconds > 0",
            name="ck_operator_trading_configuration_expiries_positive",
        ),
        sa.CheckConstraint(
            "cardinality(watchlist) > 0 AND cardinality(permitted_markets) > 0",
            name="ck_operator_trading_configuration_universe_present",
        ),
        # An instrument that is both watchlisted and prohibited makes the
        # operator's own policy ambiguous, so it is not storable.
        sa.CheckConstraint(
            "NOT (watchlist && prohibited_instruments)",
            name="ck_operator_trading_configuration_no_universe_overlap",
        ),
    )


def _create_evaluation_context_table() -> None:
    op.create_table(
        "evaluation_context",
        sa.Column("evaluation_context_id", sa.String(length=64), primary_key=True),
        sa.Column("configuration_governance_id", sa.String(length=64), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        # The M083 binding. NOT NULL and a foreign key: a context for a
        # watermark that does not exist cannot be stored, so the evidence
        # binding cannot be a dangling identifier.
        sa.Column("watermark_governance_id", sa.String(length=64), nullable=False),
        sa.Column("consumed_receipt_count", sa.Integer(), nullable=False),
        sa.Column("consumed_receipt_digest", sa.String(length=64), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("account_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("cost_estimate_id", sa.String(length=64), nullable=True),
        sa.Column("research_session_id", sa.String(length=64), nullable=True),
        sa.Column("decision_candidate_id", sa.String(length=64), nullable=True),
        sa.Column("instrument_universe_version", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["configuration_governance_id", "configuration_version"],
            [
                "operator_trading_configuration.configuration_governance_id",
                "operator_trading_configuration.configuration_version",
            ],
            name="fk_evaluation_context_configuration",
        ),
        sa.ForeignKeyConstraint(
            ["watermark_governance_id"],
            ["evaluation_evidence_watermark.watermark_governance_id"],
            name="fk_evaluation_context_watermark",
        ),
        sa.CheckConstraint(
            _not_blank("evaluation_context_id"),
            name="ck_evaluation_context_id_present",
        ),
        sa.CheckConstraint(
            "consumed_receipt_count >= 0",
            name="ck_evaluation_context_receipt_count_non_negative",
        ),
        sa.CheckConstraint(
            f"consumed_receipt_digest {_HEX_DIGEST}",
            name="ck_evaluation_context_receipt_digest_shape",
        ),
    )


def _create_proposal_table() -> None:
    op.create_table(
        "trade_proposal",
        sa.Column("proposal_governance_id", sa.String(length=64), primary_key=True),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("evaluation_context_id", sa.String(length=64), nullable=False),
        sa.Column("configuration_governance_id", sa.String(length=64), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("limit_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("estimated_notional", sa.Numeric(20, 8), nullable=False),
        sa.Column("estimated_fees", sa.Numeric(20, 8), nullable=False),
        sa.Column("estimated_slippage_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("estimated_total_cash_required", sa.Numeric(20, 8), nullable=False),
        sa.Column("stop_loss_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("profit_exit_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("mandatory_liquidation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_context_id"],
            ["evaluation_context.evaluation_context_id"],
            name="fk_trade_proposal_evaluation_context",
        ),
        sa.ForeignKeyConstraint(
            ["configuration_governance_id", "configuration_version"],
            [
                "operator_trading_configuration.configuration_governance_id",
                "operator_trading_configuration.configuration_version",
            ],
            name="fk_trade_proposal_configuration",
        ),
        sa.CheckConstraint(
            _not_blank("proposal_governance_id"),
            name="ck_trade_proposal_id_present",
        ),
        sa.CheckConstraint("proposal_version >= 1", name="ck_trade_proposal_version_positive"),
        # This product is long-only. A sell proposal is not storable at all.
        sa.CheckConstraint("side = 'BUY'", name="ck_trade_proposal_long_only"),
        sa.CheckConstraint("quantity > 0", name="ck_trade_proposal_quantity_positive"),
        sa.CheckConstraint(
            "order_type IN ('MARKET', 'LIMIT')",
            name="ck_trade_proposal_order_type",
        ),
        sa.CheckConstraint(
            "(order_type = 'LIMIT' AND limit_price IS NOT NULL)"
            " OR (order_type = 'MARKET' AND limit_price IS NULL)",
            name="ck_trade_proposal_limit_price_matches_order_type",
        ),
        sa.CheckConstraint(
            f"status IN ({_PROPOSAL_STATUSES})",
            name="ck_trade_proposal_status",
        ),
        sa.CheckConstraint(
            f"content_fingerprint {_HEX_DIGEST}",
            name="ck_trade_proposal_fingerprint_shape",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_trade_proposal_expiry_after_creation",
        ),
        sa.CheckConstraint(
            "stop_loss_price > 0 AND profit_exit_price > stop_loss_price",
            name="ck_trade_proposal_exits_ordered",
        ),
    )


def _create_decision_table() -> None:
    op.create_table(
        "trade_approval_decision",
        sa.Column("decision_governance_id", sa.String(length=64), primary_key=True),
        sa.Column("proposal_governance_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("approved_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("operator_identity", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resulting_status", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_governance_id"],
            ["trade_proposal.proposal_governance_id"],
            name="fk_trade_approval_decision_proposal",
        ),
        # ONE DECISION PER PROPOSAL. A decision row that could be reused across
        # proposals would be a generic approval, which this product refuses.
        sa.UniqueConstraint(
            "proposal_governance_id",
            name="uq_trade_approval_decision_one_per_proposal",
        ),
        sa.CheckConstraint(
            _not_blank("decision_governance_id"),
            name="ck_trade_approval_decision_id_present",
        ),
        sa.CheckConstraint(
            _not_blank("operator_identity"),
            name="ck_trade_approval_decision_operator_present",
        ),
        sa.CheckConstraint(
            "action IN ('APPROVE', 'REJECT', 'CANCEL')",
            name="ck_trade_approval_decision_action",
        ),
        # The resulting status is not free text: each action produces exactly
        # one status, so a rejection cannot be filed as an approval.
        sa.CheckConstraint(
            "(action = 'APPROVE' AND resulting_status = 'APPROVED')"
            " OR (action = 'REJECT' AND resulting_status = 'REJECTED')"
            " OR (action = 'CANCEL' AND resulting_status = 'CANCELLED')",
            name="ck_trade_approval_decision_action_matches_status",
        ),
        # Only an approval lapses. A rejection or cancellation is permanent, so
        # carrying an expiry on one would suggest it could stop applying.
        sa.CheckConstraint(
            "(action = 'APPROVE' AND expires_at IS NOT NULL AND expires_at > decided_at)"
            " OR (action <> 'APPROVE' AND expires_at IS NULL)",
            name="ck_trade_approval_decision_expiry_only_for_approval",
        ),
        sa.CheckConstraint(
            f"approved_fingerprint {_HEX_DIGEST}",
            name="ck_trade_approval_decision_fingerprint_shape",
        ),
    )


def _create_intent_table() -> None:
    op.create_table(
        "approved_order_intent",
        sa.Column("intent_governance_id", sa.String(length=64), primary_key=True),
        sa.Column("proposal_governance_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("approved_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("decision_governance_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("limit_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("time_in_force", sa.String(length=8), nullable=False),
        sa.Column("mandatory_liquidation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_mode_required", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("configuration_governance_id", sa.String(length=64), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("evaluation_context_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submission_state", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_governance_id"],
            ["trade_proposal.proposal_governance_id"],
            name="fk_approved_order_intent_proposal",
        ),
        sa.ForeignKeyConstraint(
            ["decision_governance_id"],
            ["trade_approval_decision.decision_governance_id"],
            name="fk_approved_order_intent_decision",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_context_id"],
            ["evaluation_context.evaluation_context_id"],
            name="fk_approved_order_intent_evaluation_context",
        ),
        # ONE INTENT PER PROPOSAL. One approval authorizes one order, so a
        # second intent for the same proposal is refused by the database rather
        # than deduplicated later by whoever happens to read the table.
        sa.UniqueConstraint(
            "proposal_governance_id",
            name="uq_approved_order_intent_one_per_proposal",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_approved_order_intent_idempotency_key",
        ),
        sa.CheckConstraint(
            _not_blank("intent_governance_id"),
            name="ck_approved_order_intent_id_present",
        ),
        sa.CheckConstraint(
            _not_blank("idempotency_key"),
            name="ck_approved_order_intent_idempotency_key_present",
        ),
        # NOT_SUBMITTED IS THE ONLY STORABLE STATE. MILESTONE-084 provides no
        # transition away from it, and the append-only trigger means an existing
        # row cannot acquire one either. Together these make "this milestone
        # cannot record having sent an order" a property of the schema.
        sa.CheckConstraint(
            "submission_state = 'NOT_SUBMITTED'",
            name="ck_approved_order_intent_never_submitted",
        ),
        sa.CheckConstraint(
            "account_mode_required = 'PREPARATION'",
            name="ck_approved_order_intent_preparation_only",
        ),
        sa.CheckConstraint(
            "time_in_force = 'DAY'",
            name="ck_approved_order_intent_day_only",
        ),
        sa.CheckConstraint("side = 'BUY'", name="ck_approved_order_intent_long_only"),
        sa.CheckConstraint("quantity > 0", name="ck_approved_order_intent_quantity_positive"),
        sa.CheckConstraint(
            "order_type IN ('MARKET', 'LIMIT')",
            name="ck_approved_order_intent_order_type",
        ),
        sa.CheckConstraint(
            "(order_type = 'LIMIT' AND limit_price IS NOT NULL)"
            " OR (order_type = 'MARKET' AND limit_price IS NULL)",
            name="ck_approved_order_intent_limit_price_matches_order_type",
        ),
        sa.CheckConstraint(
            f"approved_fingerprint {_HEX_DIGEST}",
            name="ck_approved_order_intent_fingerprint_shape",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_approved_order_intent_expiry_after_creation",
        ),
    )


def downgrade() -> None:
    # Removes ONLY MILESTONE-084 objects. The M083 watermark table and the M082
    # receipt table are referenced by foreign key but never altered, and both
    # survive this downgrade unchanged.
    op.execute(
        "DROP TRIGGER IF EXISTS approved_order_intent_append_only_trigger "
        "ON public.approved_order_intent"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS approved_order_intent_guard_insert_trigger "
        "ON public.approved_order_intent"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trade_approval_decision_append_only_trigger "
        "ON public.trade_approval_decision"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trade_approval_decision_guard_insert_trigger "
        "ON public.trade_approval_decision"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trade_proposal_refuse_delete_trigger ON public.trade_proposal"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trade_proposal_guard_update_trigger ON public.trade_proposal"
    )

    op.drop_table("approved_order_intent")
    op.drop_table("trade_approval_decision")
    op.drop_table("trade_proposal")
    op.drop_table("evaluation_context")
    op.drop_table("operator_trading_configuration")

    op.execute("DROP FUNCTION IF EXISTS public.approved_order_intent_guard_insert()")
    op.execute("DROP FUNCTION IF EXISTS public.trade_approval_decision_guard_insert()")
    op.execute("DROP FUNCTION IF EXISTS public.trade_proposal_guard_update()")
    op.execute("DROP FUNCTION IF EXISTS public.m084_append_only()")
