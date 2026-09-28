"""MILESTONE-085 time bases with distinct provenance: authorization interval, intent evidence.

WHY THIS EXISTS. Two defects in the basis added by `c7a41f0b52de`, both
reproduced deterministically before this revision was written.

1. THE AUTHORIZATION BASIS WAS NOT SIMULTANEOUS. `basis_host_at` was the command's
   `authorized_at`, stamped BEFORE `GET /v2/clock` was sent, while
   `basis_broker_earliest_at` was the broker's reply. The fetch latency landed in
   the mapping: with a 120 s fetch, a 300 s approval mapped to 420 s on the broker
   timeline. The pair columns are kept, and their meaning is now fixed: the host
   reading taken AFTER the response. The interval that justifies that pairing is
   stored beside them -- `basis_host_requested_at` and `basis_broker_latest_at` --
   and a row without the interval is legacy: not trusted, not repaired.

2. AN AUTHORIZATION-TIME BASIS CANNOT TRANSLATE AN OLDER M084 INTENT. The intent's
   deadlines were written under whatever host offset held when it was issued. A
   host clock that moved between issuance and authorization shifted them by that
   move. `paper_intent_time_basis` stores a basis measured AT ISSUANCE, tied
   immutably to the exact intent: its copied instants and fingerprint must equal
   the stored M084 row at insert, `intent_created_at` must equal `basis_host_at`
   (the issuance composition hands that reading to M084 as `created_at`), and the
   row is append-only. An intent without a row is not dispatchable.

NOT BACKFILLED. No UPDATE here writes a basis into an existing row, and no row is
inserted into the new table. An older authorization or intent stays without the
evidence and is refused at dispatch.

MILESTONE-084 IS NOT MODIFIED. `approved_order_intent` is READ by the insert guard
below and gains no column, constraint or trigger. The M085 authorization guard is
replaced so the basis columns are immutable too -- previously the consuming UPDATE
could have rewritten them -- and the downgrade restores its exact prior text.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d4f18a6c2e97"
down_revision: str | None = "c7a41f0b52de"
branch_labels: str | None = None
depends_on: str | None = None

_AUTHORIZATION = "paper_execution_authorization"
_INTENT_BASIS = "paper_intent_time_basis"
_PAPER_HOST = "paper-api.alpaca.markets"

_AUTHORIZATION_GUARD_PREFIX = """
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
"""

_AUTHORIZATION_GUARD_BASIS_COLUMNS = """\
        OR NEW.basis_host_at IS DISTINCT FROM OLD.basis_host_at
        OR NEW.basis_broker_earliest_at IS DISTINCT FROM OLD.basis_broker_earliest_at
        OR NEW.basis_host_requested_at IS DISTINCT FROM OLD.basis_host_requested_at
        OR NEW.basis_broker_latest_at IS DISTINCT FROM OLD.basis_broker_latest_at
"""

_AUTHORIZATION_GUARD_SUFFIX = """\
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

#: The guard with the basis columns frozen as well.
_AUTHORIZATION_GUARD_WITH_BASIS = (
    _AUTHORIZATION_GUARD_PREFIX + _AUTHORIZATION_GUARD_BASIS_COLUMNS + _AUTHORIZATION_GUARD_SUFFIX
)
#: Byte-for-byte the function `b1e9d47c30a5` installed, restored on downgrade.
_AUTHORIZATION_GUARD_ORIGINAL = _AUTHORIZATION_GUARD_PREFIX + _AUTHORIZATION_GUARD_SUFFIX

_INTENT_BASIS_INSERT_FUNCTION = """
CREATE OR REPLACE FUNCTION public.paper_execution_intent_time_basis_guard_insert()
RETURNS trigger AS $$
DECLARE
    intent_row public.approved_order_intent;
BEGIN
    SELECT * INTO intent_row
    FROM public.approved_order_intent
    WHERE intent_governance_id = NEW.intent_governance_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            '% references approved order intent % which does not exist',
            TG_TABLE_NAME, NEW.intent_governance_id;
    END IF;

    -- The evidence describes ONE exact intent. A copy that disagrees with the
    -- stored M084 row is evidence about something else and is refused.
    IF intent_row.approved_fingerprint IS DISTINCT FROM NEW.approved_fingerprint
        OR intent_row.created_at IS DISTINCT FROM NEW.intent_created_at
        OR intent_row.expires_at IS DISTINCT FROM NEW.intent_expires_at
        OR intent_row.mandatory_liquidation_at IS DISTINCT FROM NEW.intent_mandatory_liquidation_at
    THEN
        RAISE EXCEPTION
            'intent time basis for % does not describe the exact stored intent',
            NEW.intent_governance_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public
"""

_INTENT_BASIS_INSERT_TRIGGER = """
CREATE TRIGGER paper_intent_time_basis_guard_insert_trigger
BEFORE INSERT ON public.paper_intent_time_basis
FOR EACH ROW EXECUTE FUNCTION public.paper_execution_intent_time_basis_guard_insert()
"""

_INTENT_BASIS_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER paper_intent_time_basis_append_only_trigger
BEFORE UPDATE OR DELETE ON public.paper_intent_time_basis
FOR EACH ROW EXECUTE FUNCTION public.m085_append_only()
"""


def upgrade() -> None:
    op.add_column(
        _AUTHORIZATION,
        sa.Column("basis_host_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        _AUTHORIZATION,
        sa.Column("basis_broker_latest_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_paper_execution_authorization_basis_interval_paired",
        _AUTHORIZATION,
        "(basis_host_requested_at IS NULL) = (basis_broker_latest_at IS NULL)",
    )
    # The interval must bracket the pair it justifies, and the human act the
    # permission records cannot postdate the reading its expiry is mapped with --
    # otherwise a future-dated `authorized_at` would push the mapped expiry later.
    op.create_check_constraint(
        "ck_paper_execution_authorization_basis_interval_shape",
        _AUTHORIZATION,
        "basis_host_requested_at IS NULL OR ("
        "basis_host_at IS NOT NULL AND basis_broker_earliest_at IS NOT NULL"
        " AND basis_host_requested_at <= basis_host_at"
        " AND basis_broker_earliest_at <= basis_broker_latest_at"
        " AND authorized_at <= basis_host_at)",
    )
    op.execute(_AUTHORIZATION_GUARD_WITH_BASIS)

    op.create_table(
        _INTENT_BASIS,
        sa.Column("intent_governance_id", sa.String(length=64), primary_key=True),
        sa.Column("approved_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("intent_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("intent_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("intent_mandatory_liquidation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("broker_endpoint_host", sa.String(length=64), nullable=False),
        sa.Column("basis_host_requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_host_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_broker_earliest_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_broker_latest_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "approved_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_paper_intent_time_basis_fingerprint",
        ),
        sa.CheckConstraint(
            f"broker_endpoint_host = '{_PAPER_HOST}'",
            name="ck_paper_intent_time_basis_endpoint_host",
        ),
        sa.CheckConstraint(
            "basis_host_requested_at <= basis_host_at",
            name="ck_paper_intent_time_basis_host_interval",
        ),
        sa.CheckConstraint(
            "basis_broker_earliest_at <= basis_broker_latest_at",
            name="ck_paper_intent_time_basis_broker_interval",
        ),
        # THE ISSUANCE BINDING. The basis is measured first and its host reading
        # IS the intent's `created_at`; a basis measured later cannot equal it.
        sa.CheckConstraint(
            "intent_created_at = basis_host_at",
            name="ck_paper_intent_time_basis_bound_to_issuance",
        ),
        sa.CheckConstraint(
            "intent_expires_at > intent_created_at",
            name="ck_paper_intent_time_basis_expiry_follows",
        ),
    )
    op.execute(_INTENT_BASIS_INSERT_FUNCTION)
    op.execute(_INTENT_BASIS_INSERT_TRIGGER)
    op.execute(_INTENT_BASIS_APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS paper_intent_time_basis_append_only_trigger "
        "ON public.paper_intent_time_basis"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS paper_intent_time_basis_guard_insert_trigger "
        "ON public.paper_intent_time_basis"
    )
    op.drop_table(_INTENT_BASIS)
    op.execute("DROP FUNCTION IF EXISTS public.paper_execution_intent_time_basis_guard_insert()")

    op.execute(_AUTHORIZATION_GUARD_ORIGINAL)
    op.drop_constraint(
        "ck_paper_execution_authorization_basis_interval_shape", _AUTHORIZATION, type_="check"
    )
    op.drop_constraint(
        "ck_paper_execution_authorization_basis_interval_paired", _AUTHORIZATION, type_="check"
    )
    op.drop_column(_AUTHORIZATION, "basis_broker_latest_at")
    op.drop_column(_AUTHORIZATION, "basis_host_requested_at")
