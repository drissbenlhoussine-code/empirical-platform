"""MILESTONE-084 -- hostile PostgreSQL attacks against the real database.

Every attack here goes around the domain layer entirely: it speaks raw SQL to
a live PostgreSQL, the way a psql session, a future repository written in a
hurry, or a migration-era script would. The domain layer refuses all of these
states too; that is not what is being tested. What is being tested is that the
DATABASE refuses them, so that the refusal survives application code.

Attacks are grouped by the rule they attack, and each asserts the specific
error the rule raises rather than merely "something failed" -- an attack that
passes because of an unrelated typo in the SQL proves nothing.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]

_T0 = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
_EXPIRES = _T0 + timedelta(seconds=300)
_LIQUIDATION = _T0 + timedelta(minutes=45)
_DIGEST = "a" * 64
_OTHER_DIGEST = "b" * 64


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=6,
        max_overflow=6,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m084-attacks",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not _postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    eng = sa.create_engine(_config().sqlalchemy_url(), pool_size=10, max_overflow=10)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(scope="module")
def upgraded_schema(engine: Engine) -> Iterator[Engine]:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(_alembic_config(), "head")
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture
def db(upgraded_schema: Engine) -> Iterator[Connection]:
    """One transaction per attack, always rolled back.

    Attacks are destructive by design and many of them deliberately leave the
    transaction in an aborted state, so none of them may share state.
    """
    connection = upgraded_schema.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# Row builders. Each returns a complete, legal row; an attack overrides one
# field so that exactly one rule is under test.
# ---------------------------------------------------------------------------

CONFIGURATION: dict[str, object] = {
    "configuration_governance_id": "CFG-0001",
    "configuration_version": 1,
    "base_currency": "USD",
    "permitted_markets": ["XNAS"],
    "watchlist": ["AAPL", "MSFT"],
    "prohibited_instruments": ["PENNY"],
    "maximum_deployable_capital": 10000,
    "maximum_capital_per_trade": 2000,
    "maximum_percent_per_trade": 20,
    "minimum_cash_reserve": 1000,
    "maximum_simultaneous_positions": 3,
    "maximum_daily_loss": 500,
    "maximum_daily_order_count": 10,
    "minimum_price": 5,
    "maximum_price": 1000,
    "minimum_liquidity_shares": 100000,
    "maximum_spread_percent": 1,
    "maximum_estimated_slippage_percent": 1,
    "maximum_evidence_age_seconds": 86400,
    "maximum_market_data_age_seconds": 60,
    "permitted_session": "REGULAR",
    "earliest_entry_time": "10:00:00",
    "latest_entry_time": "15:30:00",
    "mandatory_liquidation_time": "15:45:00",
    "operator_timezone": "Europe/Helsinki",
    "exchange_calendar_policy": "XNAS-REGULAR-2026",
    "proposal_expiry_seconds": 300,
    "approval_expiry_seconds": 120,
    "default_order_type": "LIMIT",
    "permitted_order_types": ["LIMIT", "MARKET"],
    "limit_price_policy": "ASK",
    "stop_loss_percent": 2,
    "profit_exit_percent": 4,
    "maximum_leverage": 1,
    "short_selling_permitted": False,
    "overnight_positions_permitted": False,
    "account_mode": "PREPARATION",
    "kill_switch": "DISENGAGED",
}

CONTEXT: dict[str, object] = {
    "evaluation_context_id": "ECX-0001",
    "configuration_governance_id": "CFG-0001",
    "configuration_version": 1,
    "watermark_governance_id": "WM-0001",
    "consumed_receipt_count": 0,
    "consumed_receipt_digest": _DIGEST,
    "quote_id": "QTE-0001",
    "account_snapshot_id": "ACC-0001",
    "session_id": "SES-0001",
    "cost_estimate_id": "CST-0001",
    "research_session_id": None,
    "decision_candidate_id": None,
    "instrument_universe_version": "UNIVERSE-2026-06",
    "strategy_version": "STRATEGY-0001",
    "created_at": _T0,
}

PROPOSAL: dict[str, object] = {
    "proposal_governance_id": "PRP-0001",
    "proposal_version": 1,
    "evaluation_context_id": "ECX-0001",
    "configuration_governance_id": "CFG-0001",
    "configuration_version": 1,
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 9,
    "order_type": "LIMIT",
    "limit_price": "200.10",
    "currency": "USD",
    "estimated_notional": "1800.90",
    "estimated_fees": "1.00",
    "estimated_slippage_amount": "1.80",
    "estimated_total_cash_required": "1803.70",
    "stop_loss_price": "196.10",
    "profit_exit_price": "208.10",
    "mandatory_liquidation_at": _LIQUIDATION,
    "created_at": _T0,
    "expires_at": _EXPIRES,
    "status": "PREPARED",
    "content_fingerprint": _DIGEST,
}

DECISION: dict[str, object] = {
    "decision_governance_id": "DEC-0001",
    "proposal_governance_id": "PRP-0001",
    "proposal_version": 1,
    "approved_fingerprint": _DIGEST,
    "action": "APPROVE",
    "operator_identity": "operator-1",
    "decided_at": _T0 + timedelta(seconds=10),
    "expires_at": _T0 + timedelta(seconds=130),
    "resulting_status": "APPROVED",
}

INTENT: dict[str, object] = {
    "intent_governance_id": "INT-0001",
    "proposal_governance_id": "PRP-0001",
    "proposal_version": 1,
    "approved_fingerprint": _DIGEST,
    "decision_governance_id": "DEC-0001",
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 9,
    "order_type": "LIMIT",
    "limit_price": "200.10",
    "currency": "USD",
    "time_in_force": "DAY",
    "mandatory_liquidation_at": _LIQUIDATION,
    "account_mode_required": "PREPARATION",
    "idempotency_key": "IDEM-0001",
    "configuration_governance_id": "CFG-0001",
    "configuration_version": 1,
    "evaluation_context_id": "ECX-0001",
    "created_at": _T0 + timedelta(seconds=20),
    "expires_at": _EXPIRES,
    "submission_state": "NOT_SUBMITTED",
}


def _table(name: str, columns: Iterable[str]) -> sa.TableClause:
    return sa.table(name, *(sa.column(field) for field in columns))


def _insert(conn: Connection, table: str, row: dict[str, object], **overrides: object) -> None:
    """INSERT one row, built as a SQLAlchemy Core statement.

    Composed rather than string-formatted so that the statement carries no
    interpolated SQL text at all -- the attacks vary the VALUES, never the
    grammar, and building the grammar by hand would obscure that.
    """
    values = {**row, **overrides}
    conn.execute(sa.insert(_table(table, values)).values(**values))


def _seed_watermark(conn: Connection, watermark_id: str = "WM-0001") -> None:
    conn.execute(
        text("INSERT INTO evaluation_evidence_watermark (watermark_governance_id) VALUES (:wid)"),
        {"wid": watermark_id},
    )


def _seed_to_context(conn: Connection) -> None:
    _seed_watermark(conn)
    _insert(conn, "operator_trading_configuration", CONFIGURATION)
    _insert(conn, "evaluation_context", CONTEXT)


def _seed_to_proposal(conn: Connection, **proposal_overrides: object) -> None:
    _seed_to_context(conn)
    _insert(conn, "trade_proposal", PROPOSAL, **proposal_overrides)


def _set_status(conn: Connection, proposal_id: str, status: str) -> None:
    conn.execute(
        text("UPDATE trade_proposal SET status = :s WHERE proposal_governance_id = :p"),
        {"s": status, "p": proposal_id},
    )


def _seed_to_approved(conn: Connection, **decision_overrides: object) -> None:
    """Seed a proposal, an APPROVE decision, and the resulting APPROVED status.

    This is the legitimate order of operations: the decision is recorded while
    the proposal is still PREPARED, and only then does the status move.
    """
    _seed_to_proposal(conn)
    _insert(conn, "trade_approval_decision", DECISION, **decision_overrides)
    _set_status(conn, "PRP-0001", "APPROVED")


@contextmanager
def _refused(match: str) -> Iterator[None]:
    """Assert the enclosed statement is refused with a message naming the rule."""
    with pytest.raises((IntegrityError, DBAPIError), match=match):
        yield


# ===========================================================================
# A. Configuration: the four hard product invariants
# ===========================================================================


class TestConfigurationHardInvariantsInTheDatabase:
    @pytest.mark.parametrize("leverage", [2, "1.5", "0.5", 0, 100])
    def test_a_leveraged_configuration_cannot_be_stored(
        self, db: Connection, leverage: object
    ) -> None:
        with _refused("unleveraged"):
            _insert(db, "operator_trading_configuration", CONFIGURATION, maximum_leverage=leverage)

    def test_a_short_selling_configuration_cannot_be_stored(self, db: Connection) -> None:
        with _refused("long_only"):
            _insert(
                db, "operator_trading_configuration", CONFIGURATION, short_selling_permitted=True
            )

    def test_an_overnight_configuration_cannot_be_stored(self, db: Connection) -> None:
        with _refused("intraday_only"):
            _insert(
                db,
                "operator_trading_configuration",
                CONFIGURATION,
                overnight_positions_permitted=True,
            )

    @pytest.mark.parametrize("mode", ["PAPER", "LIVE", "paper", "PREPARATION "])
    def test_a_non_preparation_account_mode_cannot_be_stored(
        self, db: Connection, mode: str
    ) -> None:
        with _refused("preparation_only"):
            _insert(db, "operator_trading_configuration", CONFIGURATION, account_mode=mode)

    def test_the_legal_configuration_is_actually_storable(self, db: Connection) -> None:
        # Without this, every refusal above could be passing for the wrong
        # reason -- a builder that no database would ever accept.
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        stored = db.execute(
            text("SELECT count(*) FROM operator_trading_configuration")
        ).scalar_one()
        assert stored == 1


class TestConfigurationClosedEnumerations:
    @pytest.mark.parametrize("session", ["PRE_MARKET", "POST_MARKET", "EXTENDED", ""])
    def test_only_the_regular_session_is_storable(self, db: Connection, session: str) -> None:
        with _refused("regular_session_only"):
            _insert(db, "operator_trading_configuration", CONFIGURATION, permitted_session=session)

    @pytest.mark.parametrize("state", ["ON", "OFF", "disengaged", "MAYBE"])
    def test_an_unknown_kill_switch_state_is_refused(self, db: Connection, state: str) -> None:
        with _refused("kill_switch"):
            _insert(db, "operator_trading_configuration", CONFIGURATION, kill_switch=state)

    @pytest.mark.parametrize("order_type", ["STOP", "TRAILING_STOP", "limit", "MARKET_ON_CLOSE"])
    def test_an_unknown_default_order_type_is_refused(
        self, db: Connection, order_type: str
    ) -> None:
        with _refused("default_order_type"):
            _insert(
                db, "operator_trading_configuration", CONFIGURATION, default_order_type=order_type
            )

    def test_an_unknown_limit_price_policy_is_refused(self, db: Connection) -> None:
        with _refused("limit_price_policy"):
            _insert(db, "operator_trading_configuration", CONFIGURATION, limit_price_policy="BID")


class TestConfigurationOrderingAndUniverse:
    def test_an_approval_outliving_its_proposal_is_refused(self, db: Connection) -> None:
        with _refused("approval_within_proposal"):
            _insert(
                db,
                "operator_trading_configuration",
                CONFIGURATION,
                proposal_expiry_seconds=60,
                approval_expiry_seconds=61,
            )

    def test_an_inverted_entry_window_is_refused(self, db: Connection) -> None:
        with _refused("entry_window_ordered"):
            _insert(
                db,
                "operator_trading_configuration",
                CONFIGURATION,
                earliest_entry_time="15:00:00",
                latest_entry_time="10:00:00",
            )

    def test_a_liquidation_at_or_before_the_last_entry_is_refused(self, db: Connection) -> None:
        with _refused("liquidation_after_entry"):
            _insert(
                db,
                "operator_trading_configuration",
                CONFIGURATION,
                mandatory_liquidation_time="15:30:00",
            )

    def test_a_per_trade_cap_above_deployable_capital_is_refused(self, db: Connection) -> None:
        with _refused("per_trade_within_deployable"):
            _insert(
                db,
                "operator_trading_configuration",
                CONFIGURATION,
                maximum_capital_per_trade=99999,
            )

    def test_a_reserve_that_consumes_all_capital_is_refused(self, db: Connection) -> None:
        with _refused("reserve_leaves_capital"):
            _insert(db, "operator_trading_configuration", CONFIGURATION, minimum_cash_reserve=10000)

    @pytest.mark.parametrize("percent", [0, -1, 101])
    def test_a_per_trade_percentage_outside_its_range_is_refused(
        self, db: Connection, percent: int
    ) -> None:
        with _refused("percent_per_trade_range"):
            _insert(
                db,
                "operator_trading_configuration",
                CONFIGURATION,
                maximum_percent_per_trade=percent,
            )

    @pytest.mark.parametrize(("proposal_seconds", "approval_seconds"), [(0, 0), (-1, -1), (300, 0)])
    def test_a_non_positive_expiry_is_refused(
        self, db: Connection, proposal_seconds: int, approval_seconds: int
    ) -> None:
        with _refused("expiries_positive|approval_within_proposal"):
            _insert(
                db,
                "operator_trading_configuration",
                CONFIGURATION,
                proposal_expiry_seconds=proposal_seconds,
                approval_expiry_seconds=approval_seconds,
            )

    def test_an_empty_watchlist_is_refused(self, db: Connection) -> None:
        with _refused("universe_present"):
            _insert(db, "operator_trading_configuration", CONFIGURATION, watchlist=[])

    def test_an_empty_permitted_market_set_is_refused(self, db: Connection) -> None:
        with _refused("universe_present"):
            _insert(db, "operator_trading_configuration", CONFIGURATION, permitted_markets=[])

    def test_an_instrument_both_watchlisted_and_prohibited_is_refused(self, db: Connection) -> None:
        with _refused("no_universe_overlap"):
            _insert(
                db,
                "operator_trading_configuration",
                CONFIGURATION,
                watchlist=["AAPL"],
                prohibited_instruments=["AAPL"],
            )

    @pytest.mark.parametrize("identity", ["", "   ", "\t\n"])
    def test_a_blank_configuration_identity_is_refused(self, db: Connection, identity: str) -> None:
        with _refused("id_present"):
            _insert(
                db,
                "operator_trading_configuration",
                CONFIGURATION,
                configuration_governance_id=identity,
            )

    @pytest.mark.parametrize("version", [0, -1])
    def test_a_non_positive_configuration_version_is_refused(
        self, db: Connection, version: int
    ) -> None:
        with _refused("version_positive"):
            _insert(
                db, "operator_trading_configuration", CONFIGURATION, configuration_version=version
            )

    def test_the_same_configuration_version_cannot_be_stored_twice(self, db: Connection) -> None:
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        with _refused("pk_operator_trading_configuration"):
            _insert(db, "operator_trading_configuration", CONFIGURATION)

    def test_a_second_version_of_the_same_configuration_is_storable(self, db: Connection) -> None:
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        _insert(db, "operator_trading_configuration", CONFIGURATION, configuration_version=2)
        stored = db.execute(
            text("SELECT count(*) FROM operator_trading_configuration")
        ).scalar_one()
        assert stored == 2


# ===========================================================================
# B. Evaluation context: the M083 evidence binding
# ===========================================================================


class TestEvaluationContextBinding:
    def test_a_context_for_a_watermark_that_does_not_exist_is_refused(self, db: Connection) -> None:
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        with _refused("fk_evaluation_context_watermark"):
            _insert(db, "evaluation_context", CONTEXT)

    def test_a_context_with_no_watermark_at_all_is_refused(self, db: Connection) -> None:
        _seed_watermark(db)
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        with _refused("watermark_governance_id"):
            _insert(db, "evaluation_context", CONTEXT, watermark_governance_id=None)

    def test_a_context_for_a_configuration_version_that_does_not_exist_is_refused(
        self, db: Connection
    ) -> None:
        _seed_watermark(db)
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        with _refused("fk_evaluation_context_configuration"):
            _insert(db, "evaluation_context", CONTEXT, configuration_version=9)

    def test_a_legal_context_is_storable(self, db: Connection) -> None:
        _seed_to_context(db)
        stored = db.execute(text("SELECT count(*) FROM evaluation_context")).scalar_one()
        assert stored == 1

    @pytest.mark.parametrize("digest", ["", "not-a-digest", "A" * 64, "a" * 63, "g" * 64])
    def test_a_malformed_receipt_digest_is_refused(self, db: Connection, digest: str) -> None:
        _seed_watermark(db)
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        with _refused("receipt_digest_shape"):
            _insert(db, "evaluation_context", CONTEXT, consumed_receipt_digest=digest)

    def test_an_over_long_receipt_digest_is_refused_by_the_column_width(
        self, db: Connection
    ) -> None:
        # Refused before the shape check ever runs: the column is 64 characters
        # wide, so PostgreSQL rejects the value rather than truncating it.
        _seed_watermark(db)
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        with _refused("too long|StringDataRightTruncation"):
            _insert(db, "evaluation_context", CONTEXT, consumed_receipt_digest="a" * 65)

    def test_a_negative_receipt_count_is_refused(self, db: Connection) -> None:
        _seed_watermark(db)
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        with _refused("receipt_count_non_negative"):
            _insert(db, "evaluation_context", CONTEXT, consumed_receipt_count=-1)

    def test_a_zero_receipt_count_is_storable_because_it_is_an_honest_state(
        self, db: Connection
    ) -> None:
        _seed_to_context(db)
        count = db.execute(
            text("SELECT consumed_receipt_count FROM evaluation_context")
        ).scalar_one()
        assert count == 0

    def test_a_blank_context_identity_is_refused(self, db: Connection) -> None:
        _seed_watermark(db)
        _insert(db, "operator_trading_configuration", CONFIGURATION)
        with _refused("ck_evaluation_context_id_present"):
            _insert(db, "evaluation_context", CONTEXT, evaluation_context_id="   ")


# ===========================================================================
# C. Proposal: order terms that cannot express a forbidden order
# ===========================================================================


class TestProposalTermConstraints:
    def test_a_legal_proposal_is_storable(self, db: Connection) -> None:
        _seed_to_proposal(db)
        stored = db.execute(text("SELECT count(*) FROM trade_proposal")).scalar_one()
        assert stored == 1

    @pytest.mark.parametrize("side", ["SELL", "SHORT", "buy", ""])
    def test_a_proposal_that_is_not_a_buy_is_refused(self, db: Connection, side: str) -> None:
        _seed_to_context(db)
        with _refused("trade_proposal_long_only"):
            _insert(db, "trade_proposal", PROPOSAL, side=side)

    @pytest.mark.parametrize("quantity", [0, -1, -100])
    def test_a_non_positive_quantity_is_refused(self, db: Connection, quantity: int) -> None:
        _seed_to_context(db)
        with _refused("quantity_positive"):
            _insert(db, "trade_proposal", PROPOSAL, quantity=quantity)

    def test_a_limit_proposal_without_a_limit_price_is_refused(self, db: Connection) -> None:
        _seed_to_context(db)
        with _refused("limit_price_matches_order_type"):
            _insert(db, "trade_proposal", PROPOSAL, limit_price=None)

    def test_a_market_proposal_carrying_a_limit_price_is_refused(self, db: Connection) -> None:
        _seed_to_context(db)
        with _refused("limit_price_matches_order_type"):
            _insert(db, "trade_proposal", PROPOSAL, order_type="MARKET")

    @pytest.mark.parametrize("status", ["SUBMITTED", "FILLED", "prepared", "PENDING"])
    def test_a_status_outside_the_closed_set_is_refused(self, db: Connection, status: str) -> None:
        _seed_to_context(db)
        with _refused("trade_proposal_status"):
            _insert(db, "trade_proposal", PROPOSAL, status=status)

    @pytest.mark.parametrize("fingerprint", ["", "deadbeef", "A" * 64, "z" * 64])
    def test_a_malformed_fingerprint_is_refused(self, db: Connection, fingerprint: str) -> None:
        _seed_to_context(db)
        with _refused("fingerprint_shape"):
            _insert(db, "trade_proposal", PROPOSAL, content_fingerprint=fingerprint)

    def test_a_proposal_that_expires_before_it_was_created_is_refused(self, db: Connection) -> None:
        _seed_to_context(db)
        with _refused("expiry_after_creation"):
            _insert(db, "trade_proposal", PROPOSAL, expires_at=_T0 - timedelta(seconds=1))

    def test_a_profit_exit_below_the_stop_loss_is_refused(self, db: Connection) -> None:
        _seed_to_context(db)
        with _refused("exits_ordered"):
            _insert(db, "trade_proposal", PROPOSAL, profit_exit_price="100.00")

    def test_a_proposal_for_a_context_that_does_not_exist_is_refused(self, db: Connection) -> None:
        _seed_to_context(db)
        with _refused("fk_trade_proposal_evaluation_context"):
            _insert(db, "trade_proposal", PROPOSAL, evaluation_context_id="ECX-NOPE")

    def test_a_proposal_citing_a_configuration_version_that_does_not_exist_is_refused(
        self, db: Connection
    ) -> None:
        _seed_to_context(db)
        with _refused("fk_trade_proposal_configuration"):
            _insert(db, "trade_proposal", PROPOSAL, configuration_version=7)


# ===========================================================================
# D. The proposal state machine, enforced on UPDATE
# ===========================================================================


class TestProposalStateMachine:
    @pytest.mark.parametrize(
        "target", ["APPROVED", "REJECTED", "CANCELLED", "EXPIRED", "INVALIDATED"]
    )
    def test_every_edge_out_of_prepared_is_permitted(self, db: Connection, target: str) -> None:
        _seed_to_proposal(db)
        db.execute(
            text("UPDATE trade_proposal SET status = :s WHERE proposal_governance_id = 'PRP-0001'"),
            {"s": target},
        )
        status = db.execute(text("SELECT status FROM trade_proposal")).scalar_one()
        assert status == target

    @pytest.mark.parametrize(
        "start", ["APPROVED", "REJECTED", "CANCELLED", "EXPIRED", "INVALIDATED"]
    )
    @pytest.mark.parametrize("target", ["PREPARED", "APPROVED", "CANCELLED"])
    def test_no_status_may_change_once_the_proposal_is_terminal(
        self, db: Connection, start: str, target: str
    ) -> None:
        if start == target:
            pytest.skip("a no-op update is not a transition")
        _seed_to_proposal(db, status=start)
        with _refused("is terminal"):
            db.execute(
                text(
                    "UPDATE trade_proposal SET status = :s "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                ),
                {"s": target},
            )

    def test_a_rejected_proposal_cannot_be_revived_as_prepared(self, db: Connection) -> None:
        # The single most valuable case in the table above, called out by name:
        # reviving a rejection would let a refused order become approvable.
        _seed_to_proposal(db, status="REJECTED")
        with _refused("is terminal"):
            db.execute(
                text(
                    "UPDATE trade_proposal SET status = 'PREPARED' "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            )

    @pytest.mark.parametrize(
        ("column", "value"),
        [
            ("quantity", 100),
            ("symbol", "MSFT"),
            ("side", "SELL"),
            ("limit_price", "999.99"),
            ("order_type", "MARKET"),
            ("currency", "EUR"),
            ("estimated_notional", "1.00"),
            ("estimated_fees", "0.00"),
            ("estimated_slippage_amount", "0.00"),
            ("estimated_total_cash_required", "1.00"),
            ("stop_loss_price", "1.00"),
            ("profit_exit_price", "9999.00"),
            ("expires_at", _EXPIRES + timedelta(days=365)),
            ("created_at", _T0 - timedelta(days=365)),
            ("mandatory_liquidation_at", _LIQUIDATION + timedelta(days=365)),
            ("content_fingerprint", _OTHER_DIGEST),
            ("proposal_version", 2),
            ("evaluation_context_id", "ECX-OTHER"),
            ("configuration_version", 2),
        ],
    )
    def test_no_order_term_may_be_edited_after_the_proposal_exists(
        self, db: Connection, column: str, value: object
    ) -> None:
        _seed_to_proposal(db)
        proposal = _table("trade_proposal", (column, "proposal_governance_id"))
        with _refused("order terms are immutable"):
            db.execute(
                sa.update(proposal)
                .where(proposal.c.proposal_governance_id == "PRP-0001")
                .values(**{column: value})
            )

    def test_terms_may_not_be_edited_alongside_a_legal_status_change(self, db: Connection) -> None:
        # The interesting attack: hide a quantity change inside an approval.
        _seed_to_proposal(db)
        with _refused("order terms are immutable"):
            db.execute(
                text(
                    "UPDATE trade_proposal SET status = 'APPROVED', quantity = 500 "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            )

    def test_a_proposal_cannot_be_deleted(self, db: Connection) -> None:
        _seed_to_proposal(db)
        with _refused("append-only"):
            db.execute(text("DELETE FROM trade_proposal WHERE proposal_governance_id = 'PRP-0001'"))

    def test_a_proposal_cannot_be_deleted_by_an_unqualified_delete(self, db: Connection) -> None:
        _seed_to_proposal(db)
        with _refused("append-only"):
            db.execute(text("DELETE FROM trade_proposal"))

    def test_an_update_touching_no_row_is_harmless(self, db: Connection) -> None:
        _seed_to_proposal(db)
        db.execute(
            text("UPDATE trade_proposal SET status = 'APPROVED' WHERE proposal_governance_id = 'X'")
        )
        status = db.execute(text("SELECT status FROM trade_proposal")).scalar_one()
        assert status == "PREPARED"

    def test_a_no_op_status_update_is_permitted_and_changes_nothing(self, db: Connection) -> None:
        _seed_to_proposal(db)
        db.execute(
            text(
                "UPDATE trade_proposal SET status = 'PREPARED' "
                "WHERE proposal_governance_id = 'PRP-0001'"
            )
        )
        status = db.execute(text("SELECT status FROM trade_proposal")).scalar_one()
        assert status == "PREPARED"


# ===========================================================================
# E. Decision admission
# ===========================================================================


class TestDecisionAdmission:
    def test_a_legal_decision_is_storable(self, db: Connection) -> None:
        _seed_to_proposal(db)
        _insert(db, "trade_approval_decision", DECISION)
        stored = db.execute(text("SELECT count(*) FROM trade_approval_decision")).scalar_one()
        assert stored == 1

    def test_a_decision_about_a_proposal_that_does_not_exist_is_refused(
        self, db: Connection
    ) -> None:
        _seed_to_proposal(db)
        with _refused("fk_trade_approval_decision_proposal|no such proposal"):
            _insert(db, "trade_approval_decision", DECISION, proposal_governance_id="PRP-NOPE")

    @pytest.mark.parametrize(
        "status", ["APPROVED", "REJECTED", "CANCELLED", "EXPIRED", "INVALIDATED"]
    )
    def test_a_decision_may_only_be_recorded_while_the_proposal_is_prepared(
        self, db: Connection, status: str
    ) -> None:
        _seed_to_proposal(db, status=status)
        with _refused("may only be recorded while it is PREPARED"):
            _insert(db, "trade_approval_decision", DECISION)

    def test_a_decision_citing_the_wrong_proposal_version_is_refused(self, db: Connection) -> None:
        _seed_to_proposal(db)
        with _refused("but the stored proposal is version"):
            _insert(db, "trade_approval_decision", DECISION, proposal_version=2)

    def test_a_decision_carrying_a_fingerprint_the_proposal_does_not_have_is_refused(
        self, db: Connection
    ) -> None:
        _seed_to_proposal(db)
        with _refused("fingerprint does not match the proposal"):
            _insert(db, "trade_approval_decision", DECISION, approved_fingerprint=_OTHER_DIGEST)

    def test_only_one_decision_may_exist_for_one_proposal(self, db: Connection) -> None:
        _seed_to_proposal(db)
        _insert(db, "trade_approval_decision", DECISION)
        with _refused("one_per_proposal"):
            _insert(
                db,
                "trade_approval_decision",
                DECISION,
                decision_governance_id="DEC-0002",
                action="REJECT",
                resulting_status="REJECTED",
                expires_at=None,
            )

    @pytest.mark.parametrize("action", ["SUBMIT", "approve", "AUTO_APPROVE", ""])
    def test_an_action_outside_the_closed_set_is_refused(self, db: Connection, action: str) -> None:
        _seed_to_proposal(db)
        with _refused("decision_action"):
            _insert(db, "trade_approval_decision", DECISION, action=action)

    @pytest.mark.parametrize(
        ("action", "status"),
        [
            ("REJECT", "APPROVED"),
            ("CANCEL", "APPROVED"),
            ("APPROVE", "REJECTED"),
            ("APPROVE", "CANCELLED"),
            ("REJECT", "CANCELLED"),
        ],
    )
    def test_a_decision_may_not_be_filed_under_a_different_outcome(
        self, db: Connection, action: str, status: str
    ) -> None:
        _seed_to_proposal(db)
        with _refused("action_matches_status"):
            _insert(
                db,
                "trade_approval_decision",
                DECISION,
                action=action,
                resulting_status=status,
                expires_at=DECISION["expires_at"] if action == "APPROVE" else None,
            )

    def test_an_approval_without_an_expiry_is_refused(self, db: Connection) -> None:
        _seed_to_proposal(db)
        with _refused("expiry_only_for_approval"):
            _insert(db, "trade_approval_decision", DECISION, expires_at=None)

    def test_an_approval_whose_expiry_precedes_the_decision_is_refused(
        self, db: Connection
    ) -> None:
        _seed_to_proposal(db)
        with _refused("expiry_only_for_approval"):
            _insert(db, "trade_approval_decision", DECISION, expires_at=_T0)

    def test_a_rejection_carrying_an_expiry_is_refused(self, db: Connection) -> None:
        # A rejection that lapses would mean a refusal quietly stops applying.
        _seed_to_proposal(db)
        with _refused("expiry_only_for_approval"):
            _insert(
                db,
                "trade_approval_decision",
                DECISION,
                action="REJECT",
                resulting_status="REJECTED",
            )

    def test_a_blank_operator_identity_is_refused(self, db: Connection) -> None:
        _seed_to_proposal(db)
        with _refused("operator_present"):
            _insert(db, "trade_approval_decision", DECISION, operator_identity="  ")

    @pytest.mark.parametrize(
        "statement",
        [
            "UPDATE trade_approval_decision SET action = 'APPROVE'",
            "UPDATE trade_approval_decision SET operator_identity = 'someone-else'",
            "UPDATE trade_approval_decision SET expires_at = '2099-01-01T00:00:00+00'",
            "DELETE FROM trade_approval_decision",
        ],
    )
    def test_a_recorded_decision_can_never_be_changed_or_removed(
        self, db: Connection, statement: str
    ) -> None:
        _seed_to_proposal(db)
        _insert(db, "trade_approval_decision", DECISION)
        with _refused("append-only"):
            db.execute(text(statement))


# ===========================================================================
# F. Intent admission -- the hand-off that must not become a submission
# ===========================================================================


class TestIntentAdmission:
    def test_a_legal_intent_is_storable(self, db: Connection) -> None:
        _seed_to_approved(db)
        _insert(db, "approved_order_intent", INTENT)
        stored = db.execute(text("SELECT count(*) FROM approved_order_intent")).scalar_one()
        assert stored == 1

    def test_an_intent_from_a_rejection_is_refused(self, db: Connection) -> None:
        _seed_to_proposal(db)
        _insert(
            db,
            "trade_approval_decision",
            DECISION,
            action="REJECT",
            resulting_status="REJECTED",
            expires_at=None,
        )
        db.execute(
            text(
                "UPDATE trade_proposal SET status = 'REJECTED' "
                "WHERE proposal_governance_id = 'PRP-0001'"
            )
        )
        with _refused("requires an APPROVE decision"):
            _insert(db, "approved_order_intent", INTENT)

    @pytest.mark.parametrize("status", ["PREPARED", "REJECTED", "CANCELLED", "EXPIRED"])
    def test_an_intent_for_a_proposal_that_is_not_approved_is_refused(
        self, db: Connection, status: str
    ) -> None:
        _seed_to_proposal(db)
        _insert(db, "trade_approval_decision", DECISION)
        if status != "PREPARED":
            db.execute(
                text(
                    "UPDATE trade_proposal SET status = :s "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                ),
                {"s": status},
            )
        with _refused("not APPROVED"):
            _insert(db, "approved_order_intent", INTENT)

    def test_an_intent_citing_a_decision_for_a_different_proposal_is_refused(
        self, db: Connection
    ) -> None:
        _seed_to_approved(db)
        # A second, fully legitimate proposal with its own approval.
        _insert(db, "trade_proposal", PROPOSAL, proposal_governance_id="PRP-0002")
        _insert(
            db,
            "trade_approval_decision",
            DECISION,
            decision_governance_id="DEC-0002",
            proposal_governance_id="PRP-0002",
        )
        with _refused("does not belong to proposal"):
            _insert(db, "approved_order_intent", INTENT, decision_governance_id="DEC-0002")

    def test_an_intent_whose_fingerprint_matches_neither_row_is_refused(
        self, db: Connection
    ) -> None:
        _seed_to_approved(db)
        with _refused("fingerprint does not match"):
            _insert(db, "approved_order_intent", INTENT, approved_fingerprint=_OTHER_DIGEST)

    def test_an_intent_citing_a_different_proposal_version_is_refused(self, db: Connection) -> None:
        _seed_to_approved(db)
        with _refused("different proposal version"):
            _insert(db, "approved_order_intent", INTENT, proposal_version=2)

    @pytest.mark.parametrize(
        ("column", "value"),
        [
            ("symbol", "MSFT"),
            ("quantity", 500),
            ("order_type", "MARKET"),
            ("limit_price", "999.99"),
            ("currency", "EUR"),
            ("mandatory_liquidation_at", _LIQUIDATION + timedelta(hours=6)),
        ],
    )
    def test_an_intent_whose_terms_differ_from_the_approved_proposal_is_refused(
        self, db: Connection, column: str, value: object
    ) -> None:
        # This is the whole point of the milestone: what a human approved and
        # what would be handed onward must be the same order.
        _seed_to_approved(db)
        overrides: dict[str, object] = {column: value}
        if column == "order_type" and value == "MARKET":
            overrides["limit_price"] = None
        with _refused("differ from the proposal|limit_price_matches_order_type"):
            _insert(db, "approved_order_intent", INTENT, **overrides)

    def test_an_intent_created_after_the_approval_lapsed_is_refused(self, db: Connection) -> None:
        _seed_to_approved(db)
        with _refused("approval had lapsed"):
            _insert(
                db,
                "approved_order_intent",
                INTENT,
                created_at=_T0 + timedelta(seconds=131),
            )

    def test_an_intent_created_after_the_proposal_expired_is_refused(self, db: Connection) -> None:
        # The approval is given a long life so that the PROPOSAL's expiry is
        # unambiguously the rule under test.
        _seed_to_approved(db, expires_at=_T0 + timedelta(days=1))
        with _refused("proposal had expired"):
            _insert(
                db,
                "approved_order_intent",
                INTENT,
                created_at=_EXPIRES + timedelta(seconds=1),
                expires_at=_EXPIRES + timedelta(seconds=2),
            )

    def test_only_one_intent_may_exist_for_one_proposal(self, db: Connection) -> None:
        _seed_to_approved(db)
        _insert(db, "approved_order_intent", INTENT)
        with _refused("one_per_proposal"):
            _insert(
                db,
                "approved_order_intent",
                INTENT,
                intent_governance_id="INT-0002",
                idempotency_key="IDEM-0002",
            )

    def test_an_idempotency_key_cannot_be_reused_across_proposals(self, db: Connection) -> None:
        _seed_to_approved(db)
        _insert(db, "approved_order_intent", INTENT)
        _insert(db, "trade_proposal", PROPOSAL, proposal_governance_id="PRP-0002")
        _insert(
            db,
            "trade_approval_decision",
            DECISION,
            decision_governance_id="DEC-0002",
            proposal_governance_id="PRP-0002",
        )
        db.execute(
            text(
                "UPDATE trade_proposal SET status = 'APPROVED' "
                "WHERE proposal_governance_id = 'PRP-0002'"
            )
        )
        with _refused("idempotency_key"):
            _insert(
                db,
                "approved_order_intent",
                INTENT,
                intent_governance_id="INT-0002",
                proposal_governance_id="PRP-0002",
                decision_governance_id="DEC-0002",
            )


class TestIntentCannotBecomeASubmission:
    """MILESTONE-084 must be technically incapable of recording a submission."""

    @pytest.mark.parametrize(
        "state", ["SUBMITTED", "SENT", "PENDING", "ACKNOWLEDGED", "FILLED", "not_submitted", ""]
    )
    def test_no_submission_state_but_not_submitted_can_be_stored(
        self, db: Connection, state: str
    ) -> None:
        _seed_to_approved(db)
        with _refused("never_submitted"):
            _insert(db, "approved_order_intent", INTENT, submission_state=state)

    def test_a_stored_intent_cannot_be_updated_to_submitted(self, db: Connection) -> None:
        _seed_to_approved(db)
        _insert(db, "approved_order_intent", INTENT)
        with _refused("append-only"):
            db.execute(text("UPDATE approved_order_intent SET submission_state = 'SUBMITTED'"))

    def test_a_stored_intent_cannot_be_deleted_and_re_created_as_submitted(
        self, db: Connection
    ) -> None:
        _seed_to_approved(db)
        _insert(db, "approved_order_intent", INTENT)
        with _refused("append-only"):
            db.execute(text("DELETE FROM approved_order_intent"))

    @pytest.mark.parametrize("mode", ["PAPER", "LIVE", "preparation"])
    def test_an_intent_declaring_a_paper_or_live_account_is_refused(
        self, db: Connection, mode: str
    ) -> None:
        _seed_to_approved(db)
        with _refused("preparation_only"):
            _insert(db, "approved_order_intent", INTENT, account_mode_required=mode)

    @pytest.mark.parametrize("tif", ["GTC", "IOC", "FOK", "GTD", "day"])
    def test_an_intent_that_could_survive_the_session_is_refused(
        self, db: Connection, tif: str
    ) -> None:
        _seed_to_approved(db)
        with _refused("day_only"):
            _insert(db, "approved_order_intent", INTENT, time_in_force=tif)

    def test_a_sell_intent_is_refused(self, db: Connection) -> None:
        _seed_to_approved(db)
        with _refused("intent_long_only|differ from the proposal"):
            _insert(db, "approved_order_intent", INTENT, side="SELL")

    @pytest.mark.parametrize("quantity", [0, -9])
    def test_a_non_positive_intent_quantity_is_refused(self, db: Connection, quantity: int) -> None:
        _seed_to_approved(db)
        with _refused("quantity_positive|differ from the proposal"):
            _insert(db, "approved_order_intent", INTENT, quantity=quantity)


# ===========================================================================
# G. Going around the triggers
# ===========================================================================


class TestBypassAttempts:
    def test_a_multi_row_insert_is_checked_row_by_row(self, db: Connection) -> None:
        # A BEFORE ROW trigger fires per row; a caller cannot smuggle a bad row
        # in behind a good one.
        _seed_to_context(db)
        with _refused("trade_proposal_long_only"):
            db.execute(
                text(
                    "INSERT INTO trade_proposal (proposal_governance_id, proposal_version, "
                    "evaluation_context_id, configuration_governance_id, configuration_version, "
                    "symbol, side, quantity, order_type, limit_price, currency, "
                    "estimated_notional, estimated_fees, estimated_slippage_amount, "
                    "estimated_total_cash_required, stop_loss_price, profit_exit_price, "
                    "mandatory_liquidation_at, created_at, expires_at, status, "
                    "content_fingerprint) VALUES "
                    "('PRP-A', 1, 'ECX-0001', 'CFG-0001', 1, 'AAPL', 'BUY', 9, 'LIMIT', 200.10, "
                    "'USD', 1800.90, 1.00, 1.80, 1803.70, 196.10, 208.10, :liq, :t0, :exp, "
                    "'PREPARED', :fp), "
                    "('PRP-B', 1, 'ECX-0001', 'CFG-0001', 1, 'AAPL', 'SELL', 9, 'LIMIT', 200.10, "
                    "'USD', 1800.90, 1.00, 1.80, 1803.70, 196.10, 208.10, :liq, :t0, :exp, "
                    "'PREPARED', :fp)"
                ),
                {"liq": _LIQUIDATION, "t0": _T0, "exp": _EXPIRES, "fp": _DIGEST},
            )

    def test_an_insert_select_cannot_clone_a_proposal_into_a_forbidden_state(
        self, db: Connection
    ) -> None:
        _seed_to_proposal(db)
        with _refused("trade_proposal_long_only"):
            db.execute(
                text(
                    "INSERT INTO trade_proposal SELECT 'PRP-CLONE', proposal_version, "
                    "evaluation_context_id, configuration_governance_id, configuration_version, "
                    "symbol, 'SELL', quantity, order_type, limit_price, currency, "
                    "estimated_notional, estimated_fees, estimated_slippage_amount, "
                    "estimated_total_cash_required, stop_loss_price, profit_exit_price, "
                    "mandatory_liquidation_at, created_at, expires_at, status, "
                    "content_fingerprint FROM trade_proposal"
                )
            )

    def test_a_cte_update_is_still_an_update(self, db: Connection) -> None:
        _seed_to_proposal(db)
        with _refused("order terms are immutable"):
            db.execute(
                text(
                    "WITH bump AS (UPDATE trade_proposal SET quantity = 999 "
                    "WHERE proposal_governance_id = 'PRP-0001' RETURNING 1) "
                    "SELECT count(*) FROM bump"
                )
            )

    def test_on_conflict_do_update_cannot_edit_terms(self, db: Connection) -> None:
        _seed_to_proposal(db)
        with _refused("order terms are immutable"):
            _insert_on_conflict(db)

    def test_an_upsert_cannot_resurrect_a_terminal_proposal(self, db: Connection) -> None:
        _seed_to_proposal(db, status="REJECTED")
        with _refused("is terminal"):
            db.execute(
                text(
                    "INSERT INTO trade_proposal (proposal_governance_id, proposal_version, "
                    "evaluation_context_id, configuration_governance_id, configuration_version, "
                    "symbol, side, quantity, order_type, limit_price, currency, "
                    "estimated_notional, estimated_fees, estimated_slippage_amount, "
                    "estimated_total_cash_required, stop_loss_price, profit_exit_price, "
                    "mandatory_liquidation_at, created_at, expires_at, status, "
                    "content_fingerprint) VALUES "
                    "('PRP-0001', 1, 'ECX-0001', 'CFG-0001', 1, 'AAPL', 'BUY', 9, 'LIMIT', "
                    "200.10, 'USD', 1800.90, 1.00, 1.80, 1803.70, 196.10, 208.10, :liq, :t0, "
                    ":exp, 'PREPARED', :fp) "
                    "ON CONFLICT (proposal_governance_id) DO UPDATE SET status = 'PREPARED'"
                ),
                {"liq": _LIQUIDATION, "t0": _T0, "exp": _EXPIRES, "fp": _DIGEST},
            )

    def test_a_pg_temp_table_cannot_shadow_the_proposal_the_trigger_reads(
        self, db: Connection
    ) -> None:
        # The intent trigger reads `public.trade_proposal` by schema-qualified
        # name under a pinned search_path, so a same-named temp table with a
        # forged APPROVED row does not become the row it checks.
        _seed_to_proposal(db)
        _insert(db, "trade_approval_decision", DECISION)
        db.execute(text("CREATE TEMP TABLE trade_proposal (LIKE public.trade_proposal)"))
        db.execute(text("INSERT INTO pg_temp.trade_proposal SELECT * FROM public.trade_proposal"))
        db.execute(text("UPDATE pg_temp.trade_proposal SET status = 'APPROVED'"))
        with _refused("not APPROVED"):
            _insert(db, "approved_order_intent", INTENT)

    def test_the_copy_path_is_checked_too(self, db: Connection) -> None:
        # COPY runs on the raw driver connection, so the refusal arrives as a
        # psycopg error rather than one SQLAlchemy has wrapped.
        _seed_to_context(db)
        raw = db.connection.driver_connection
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="trade_proposal_long_only"),
            raw.cursor() as cursor,  # type: ignore[union-attr]
        ):
            with cursor.copy(
                "COPY trade_proposal (proposal_governance_id, proposal_version, "
                "evaluation_context_id, configuration_governance_id, configuration_version, "
                "symbol, side, quantity, order_type, limit_price, currency, estimated_notional, "
                "estimated_fees, estimated_slippage_amount, estimated_total_cash_required, "
                "stop_loss_price, profit_exit_price, mandatory_liquidation_at, created_at, "
                "expires_at, status, content_fingerprint) FROM STDIN"
            ) as copy:
                copy.write(
                    "PRP-COPY\t1\tECX-0001\tCFG-0001\t1\tAAPL\tSELL\t9\tLIMIT\t200.10\tUSD\t"
                    "1800.90\t1.00\t1.80\t1803.70\t196.10\t208.10\t"
                    f"{_LIQUIDATION.isoformat()}\t{_T0.isoformat()}\t{_EXPIRES.isoformat()}\t"
                    f"PREPARED\t{_DIGEST}\n"
                )


def _insert_on_conflict(conn: Connection) -> None:
    conn.execute(
        text(
            "INSERT INTO trade_proposal (proposal_governance_id, proposal_version, "
            "evaluation_context_id, configuration_governance_id, configuration_version, "
            "symbol, side, quantity, order_type, limit_price, currency, estimated_notional, "
            "estimated_fees, estimated_slippage_amount, estimated_total_cash_required, "
            "stop_loss_price, profit_exit_price, mandatory_liquidation_at, created_at, "
            "expires_at, status, content_fingerprint) VALUES "
            "('PRP-0001', 1, 'ECX-0001', 'CFG-0001', 1, 'AAPL', 'BUY', 9, 'LIMIT', 200.10, "
            "'USD', 1800.90, 1.00, 1.80, 1803.70, 196.10, 208.10, :liq, :t0, :exp, 'PREPARED', "
            ":fp) ON CONFLICT (proposal_governance_id) DO UPDATE SET quantity = 999"
        ),
        {"liq": _LIQUIDATION, "t0": _T0, "exp": _EXPIRES, "fp": _DIGEST},
    )


# ===========================================================================
# H. Earlier milestones are untouched
# ===========================================================================


class TestFrozenMilestonesArePreserved:
    def test_the_m083_watermark_table_still_behaves_as_m083_specified(self, db: Connection) -> None:
        _seed_watermark(db, "WM-PRESERVE")
        stored = db.execute(
            text(
                "SELECT receipt_governance_ids FROM evaluation_evidence_watermark "
                "WHERE watermark_governance_id = 'WM-PRESERVE'"
            )
        ).scalar_one()
        # The M083 capture trigger still supplies the set, and an empty receipt
        # table still yields an explicit empty array rather than NULL.
        assert stored == []

    def test_the_m083_watermark_is_still_immutable(self, db: Connection) -> None:
        _seed_watermark(db, "WM-PRESERVE")
        with _refused("append-only"):
            db.execute(text("DELETE FROM evaluation_evidence_watermark"))

    def test_m084_tables_do_not_appear_in_the_m083_schema_boundary(self, db: Connection) -> None:
        # M084 adds tables; it does not add columns to M083's.
        columns = (
            db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'evaluation_evidence_watermark' ORDER BY column_name"
                )
            )
            .scalars()
            .all()
        )
        assert columns == ["receipt_governance_ids", "watermark_governance_id"]
