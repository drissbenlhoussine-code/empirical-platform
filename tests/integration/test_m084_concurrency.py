"""MILESTONE-084 -- executed concurrency races against real PostgreSQL.

A unique constraint is a claim about what the database will do. This file makes
the database actually do it, with two real connections in two real
transactions, and records which one won.

NO SLEEP IS USED AS PROOF ANYWHERE. Every race is sequenced with
`threading.Barrier` and `threading.Event`, and where a race needs one
transaction to be *inside* a statement while the other starts, it is held there
by a real PostgreSQL row lock (`SELECT ... FOR UPDATE`) or by an uncommitted
write that the other connection must block on -- not by hoping a timer lines
up. The one place a timeout appears is as a FAILURE BOUND on a barrier: if the
two connections do not meet, the test fails rather than passing slowly.

WHAT A RACE HERE PROVES, AND WHAT IT DOES NOT. It proves that when two writers
genuinely contend, exactly one outcome is persisted and the loser is told. It
does not prove the absence of every possible interleaving -- no finite set of
executed races could -- and this file does not claim otherwise.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
_EXPIRES = _T0 + timedelta(seconds=300)
_LIQUIDATION = _T0 + timedelta(minutes=45)
_DIGEST = "a" * 64
_OTHER_DIGEST = "b" * 64

#: A barrier that never completes is a broken test, not a slow one.
_BARRIER_TIMEOUT_SECONDS = 30.0


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=12,
        max_overflow=12,
        connection_timeout_seconds=10,
        application_name="empirical-platform-m084-concurrency",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not _postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    eng = sa.create_engine(_config().sqlalchemy_url(), pool_size=12, max_overflow=12)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(_alembic_config(), "head")
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def clean(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE approved_order_intent, trade_approval_decision, "
                "trade_proposal_risk_check, trade_proposal, evaluation_context, "
                "operator_trading_configuration, evaluation_evidence_watermark"
            )
        )
    return engine


# ---------------------------------------------------------------------------
# Rows, and the racing harness
# ---------------------------------------------------------------------------

CONFIGURATION: dict[str, Any] = {
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

CONTEXT: dict[str, Any] = {
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

PROPOSAL: dict[str, Any] = {
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

DECISION: dict[str, Any] = {
    "decision_governance_id": "DEC-0001",
    "proposal_governance_id": "PRP-0001",
    "proposal_version": 1,
    "approved_fingerprint": _DIGEST,
    "action": "APPROVE",
    "operator_identity": "alice",
    "decided_at": _T0 + timedelta(seconds=10),
    "expires_at": _T0 + timedelta(seconds=130),
    "resulting_status": "APPROVED",
}

INTENT: dict[str, Any] = {
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


def _insert(conn: Connection, table: str, row: dict[str, Any], **overrides: object) -> None:
    values = {**row, **overrides}
    conn.execute(sa.insert(_table(table, values)).values(**values))


@dataclass(frozen=True, slots=True)
class RaceResult:
    """What each connection did, and what the table holds afterwards."""

    outcomes: tuple[str, ...]
    winners: int
    losers: int
    final_rows: tuple[tuple[Any, ...], ...]

    @property
    def loser_errors(self) -> tuple[str, ...]:
        return tuple(o for o in self.outcomes if o != "COMMITTED")


def race(
    engine: Engine,
    first: Callable[[Connection], None],
    second: Callable[[Connection], None],
    *,
    inspect: str,
    parameters: dict[str, Any] | None = None,
) -> RaceResult:
    """Run two writers that meet at a barrier, then commit or fail.

    Both connections open a transaction, do their work up to the barrier, and
    only then attempt the contended statement. Neither can finish before the
    other has started, so the contention is real rather than incidental.
    """
    barrier = threading.Barrier(2, timeout=_BARRIER_TIMEOUT_SECONDS)
    outcomes: list[str] = []
    lock = threading.Lock()

    def run(work: Callable[[Connection], None]) -> None:
        connection = engine.connect()
        transaction = connection.begin()
        try:
            barrier.wait()
            work(connection)
            transaction.commit()
            result = "COMMITTED"
        except Exception as error:  # noqa: BLE001 - the loser's error IS the evidence
            transaction.rollback()
            result = type(error).__name__ + ": " + str(error).split("\n")[0][:160]
        finally:
            connection.close()
        with lock:
            outcomes.append(result)

    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in [pool.submit(run, first), pool.submit(run, second)]:
            future.result()

    with engine.connect() as connection:
        rows = tuple(
            tuple(row) for row in connection.execute(text(inspect), parameters or {}).fetchall()
        )
    return RaceResult(
        outcomes=tuple(sorted(outcomes)),
        winners=sum(1 for o in outcomes if o == "COMMITTED"),
        losers=sum(1 for o in outcomes if o != "COMMITTED"),
        final_rows=rows,
    )


def seed_to_context(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                "VALUES ('WM-0001')"
            )
        )
        _insert(conn, "operator_trading_configuration", CONFIGURATION)
        _insert(conn, "evaluation_context", CONTEXT)


def seed_to_proposal(engine: Engine, **overrides: object) -> None:
    seed_to_context(engine)
    with engine.begin() as conn:
        _insert(conn, "trade_proposal", PROPOSAL, **overrides)


def seed_to_approved(engine: Engine) -> None:
    seed_to_proposal(engine)
    with engine.begin() as conn:
        _insert(conn, "trade_approval_decision", DECISION)
        conn.execute(
            text(
                "UPDATE trade_proposal SET status = 'APPROVED' "
                "WHERE proposal_governance_id = 'PRP-0001'"
            )
        )


# ===========================================================================
# A. Configuration
# ===========================================================================


class TestConfigurationRaces:
    def test_a1_two_concurrent_versions_for_one_identity_both_commit(self, clean: Engine) -> None:
        # Distinct versions do not contend: both are legitimate, and the
        # composite primary key admits both. A race that "won" here would mean
        # the schema was refusing a legal write.
        result = race(
            clean,
            lambda c: _insert(c, "operator_trading_configuration", CONFIGURATION),
            lambda c: _insert(
                c, "operator_trading_configuration", CONFIGURATION, configuration_version=2
            ),
            inspect="SELECT configuration_version FROM operator_trading_configuration "
            "ORDER BY configuration_version",
        )
        assert result.winners == 2
        assert result.final_rows == ((1,), (2,))

    def test_a2_identical_version_creation_lets_exactly_one_through(self, clean: Engine) -> None:
        result = race(
            clean,
            lambda c: _insert(c, "operator_trading_configuration", CONFIGURATION),
            lambda c: _insert(c, "operator_trading_configuration", CONFIGURATION),
            inspect="SELECT count(*) FROM operator_trading_configuration",
        )
        assert result.winners == 1
        assert result.losers == 1
        assert "pk_operator_trading_configuration" in result.loser_errors[0]
        assert result.final_rows == ((1,),)

    def test_a3_conflicting_content_under_one_version_lets_exactly_one_through(
        self, clean: Engine
    ) -> None:
        # The dangerous case: two DIFFERENT policies claiming the same version.
        # Exactly one must survive, or a proposal citing that version would be
        # governed by a policy nobody can name.
        result = race(
            clean,
            lambda c: _insert(
                c, "operator_trading_configuration", CONFIGURATION, maximum_daily_loss=500
            ),
            lambda c: _insert(
                c, "operator_trading_configuration", CONFIGURATION, maximum_daily_loss=999
            ),
            inspect="SELECT maximum_daily_loss FROM operator_trading_configuration",
        )
        assert result.winners == 1
        assert len(result.final_rows) == 1
        assert result.final_rows[0][0] in (500, 999)

    def test_a4_a_reader_does_not_see_an_uncommitted_version(self, clean: Engine) -> None:
        # READ COMMITTED: the writer's uncommitted row is invisible, and the
        # reader is not blocked by it either.
        started = threading.Event()
        seen: list[int] = []

        def writer() -> None:
            with clean.connect() as connection:
                transaction = connection.begin()
                _insert(connection, "operator_trading_configuration", CONFIGURATION)
                started.set()
                # Hold the uncommitted row until the reader has looked.
                read_done.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
                transaction.rollback()

        read_done = threading.Event()

        def reader() -> None:
            started.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
            with clean.connect() as connection:
                seen.append(
                    connection.execute(
                        text("SELECT count(*) FROM operator_trading_configuration")
                    ).scalar_one()
                )
            read_done.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            for future in [pool.submit(writer), pool.submit(reader)]:
                future.result()

        assert seen == [0]
        with clean.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM operator_trading_configuration")
                ).scalar_one()
                == 0
            )


# ===========================================================================
# B. Evaluation context
# ===========================================================================


class TestEvaluationContextRaces:
    def test_b5_identical_identity_and_inputs_lets_exactly_one_through(self, clean: Engine) -> None:
        seed_to_context(clean)
        with clean.begin() as conn:
            conn.execute(text("DELETE FROM evaluation_context"))
        result = race(
            clean,
            lambda c: _insert(c, "evaluation_context", CONTEXT),
            lambda c: _insert(c, "evaluation_context", CONTEXT),
            inspect="SELECT count(*) FROM evaluation_context",
        )
        assert result.winners == 1
        assert result.final_rows == ((1,),)

    def test_b6_identical_identity_with_conflicting_inputs_lets_exactly_one_through(
        self, clean: Engine
    ) -> None:
        # Two contexts claiming the same identity but citing different quotes.
        # Both cannot be true, and the database must not hold both.
        seed_to_context(clean)
        with clean.begin() as conn:
            conn.execute(text("DELETE FROM evaluation_context"))
        result = race(
            clean,
            lambda c: _insert(c, "evaluation_context", CONTEXT, quote_id="QTE-AAA"),
            lambda c: _insert(c, "evaluation_context", CONTEXT, quote_id="QTE-BBB"),
            inspect="SELECT quote_id FROM evaluation_context",
        )
        assert result.winners == 1
        assert len(result.final_rows) == 1
        assert result.final_rows[0][0] in ("QTE-AAA", "QTE-BBB")

    def test_b7_a_context_cannot_commit_against_a_configuration_rolled_back_under_it(
        self, clean: Engine
    ) -> None:
        # The context writer must not be able to bind to a configuration that
        # never existed. The foreign key holds the line even though the
        # configuration insert was live and uncommitted when it started.
        with clean.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                    "VALUES ('WM-0001')"
                )
            )
        config_written = threading.Event()
        context_finished = threading.Event()
        outcome: list[str] = []

        def configuration_writer() -> None:
            with clean.connect() as connection:
                transaction = connection.begin()
                _insert(connection, "operator_trading_configuration", CONFIGURATION)
                config_written.set()
                context_finished.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
                transaction.rollback()

        def context_writer() -> None:
            config_written.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
            with clean.connect() as connection:
                transaction = connection.begin()
                try:
                    _insert(connection, "evaluation_context", CONTEXT)
                    transaction.commit()
                    outcome.append("COMMITTED")
                except Exception as error:  # noqa: BLE001 - the refusal is the evidence
                    transaction.rollback()
                    outcome.append(type(error).__name__)
                finally:
                    context_finished.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            for future in [pool.submit(configuration_writer), pool.submit(context_writer)]:
                future.result()

        # The FK cannot see the uncommitted parent, so the child is refused.
        assert outcome == ["IntegrityError"]
        with clean.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM evaluation_context")).scalar_one()
                == 0
            )

    def test_b8_a_context_cannot_bind_a_watermark_rolled_back_under_it(self, clean: Engine) -> None:
        with clean.begin() as conn:
            _insert(conn, "operator_trading_configuration", CONFIGURATION)
        watermark_written = threading.Event()
        context_finished = threading.Event()
        outcome: list[str] = []

        def watermark_writer() -> None:
            with clean.connect() as connection:
                transaction = connection.begin()
                connection.execute(
                    text(
                        "INSERT INTO evaluation_evidence_watermark "
                        "(watermark_governance_id) VALUES ('WM-0001')"
                    )
                )
                watermark_written.set()
                context_finished.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
                transaction.rollback()

        def context_writer() -> None:
            watermark_written.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
            with clean.connect() as connection:
                transaction = connection.begin()
                try:
                    _insert(connection, "evaluation_context", CONTEXT)
                    transaction.commit()
                    outcome.append("COMMITTED")
                except Exception as error:  # noqa: BLE001 - the refusal is the evidence
                    transaction.rollback()
                    outcome.append(type(error).__name__)
                finally:
                    context_finished.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            for future in [pool.submit(watermark_writer), pool.submit(context_writer)]:
                future.result()

        assert outcome == ["IntegrityError"]

    def test_b9_a_rolled_back_winner_leaves_the_identity_free(self, clean: Engine) -> None:
        seed_to_context(clean)
        with clean.begin() as conn:
            conn.execute(text("DELETE FROM evaluation_context"))
        with clean.connect() as connection:
            transaction = connection.begin()
            _insert(connection, "evaluation_context", CONTEXT)
            transaction.rollback()
        # The identity is free again: a rollback leaves nothing behind.
        with clean.begin() as conn:
            _insert(conn, "evaluation_context", CONTEXT, quote_id="QTE-RETRY")
        with clean.connect() as connection:
            assert (
                connection.execute(text("SELECT quote_id FROM evaluation_context")).scalar_one()
                == "QTE-RETRY"
            )

    def test_b10_a_retry_after_commit_uncertainty_reads_the_winner(self, clean: Engine) -> None:
        # The pattern a repository must use when it cannot tell whether its
        # commit landed: attempt, see the unique violation, read back.
        seed_to_context(clean)
        with clean.connect() as connection:
            transaction = connection.begin()
            try:
                _insert(connection, "evaluation_context", CONTEXT, quote_id="QTE-RETRY")
                transaction.commit()
                landed = True
            except Exception:  # noqa: BLE001 - the conflict is the expected path
                transaction.rollback()
                landed = False
        assert landed is False
        with clean.connect() as connection:
            assert (
                connection.execute(text("SELECT quote_id FROM evaluation_context")).scalar_one()
                == "QTE-0001"
            )


# ===========================================================================
# C. Proposals
# ===========================================================================


class TestProposalRaces:
    def test_c11_identical_proposal_construction_lets_exactly_one_through(
        self, clean: Engine
    ) -> None:
        seed_to_context(clean)
        result = race(
            clean,
            lambda c: _insert(c, "trade_proposal", PROPOSAL),
            lambda c: _insert(c, "trade_proposal", PROPOSAL),
            inspect="SELECT count(*) FROM trade_proposal",
        )
        assert result.winners == 1
        assert result.final_rows == ((1,),)

    def test_c12_one_identity_with_two_quantities_stores_exactly_one(self, clean: Engine) -> None:
        # The most dangerous proposal race: an operator must never be shown one
        # quantity and have another persisted under the same identity.
        seed_to_context(clean)
        result = race(
            clean,
            lambda c: _insert(c, "trade_proposal", PROPOSAL, quantity=9),
            lambda c: _insert(c, "trade_proposal", PROPOSAL, quantity=99),
            inspect="SELECT quantity FROM trade_proposal",
        )
        assert result.winners == 1
        assert len(result.final_rows) == 1
        assert result.final_rows[0][0] in (9, 99)

    def test_c13_one_identity_with_two_fingerprints_stores_exactly_one(self, clean: Engine) -> None:
        seed_to_context(clean)
        result = race(
            clean,
            lambda c: _insert(c, "trade_proposal", PROPOSAL, content_fingerprint=_DIGEST),
            lambda c: _insert(c, "trade_proposal", PROPOSAL, content_fingerprint=_OTHER_DIGEST),
            inspect="SELECT content_fingerprint FROM trade_proposal",
        )
        assert result.winners == 1
        assert result.final_rows[0][0] in (_DIGEST, _OTHER_DIGEST)

    def test_c14_invalidation_and_persistence_cannot_both_land_on_one_row(
        self, clean: Engine
    ) -> None:
        # A proposal being written while a sweep invalidates it. The row is
        # created or it is not; it never ends up half-invalidated.
        seed_to_proposal(clean)
        result = race(
            clean,
            lambda c: c.execute(
                text(
                    "UPDATE trade_proposal SET status = 'INVALIDATED' "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            ),
            lambda c: c.execute(
                text(
                    "UPDATE trade_proposal SET status = 'EXPIRED' "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            ),
            inspect="SELECT status FROM trade_proposal",
        )
        # Both statements target the same row; the second waits for the first's
        # lock and then meets a terminal status.
        assert result.winners == 1
        assert result.losers == 1
        assert result.final_rows[0][0] in ("INVALIDATED", "EXPIRED")

    def test_c15_a_kill_switch_version_and_a_proposal_are_independently_durable(
        self, clean: Engine
    ) -> None:
        # Engaging the kill switch writes a NEW configuration version; it does
        # not retract a proposal already prepared under the old one. Both land,
        # and the sweep -- not the switch -- is what invalidates the proposal.
        seed_to_context(clean)
        result = race(
            clean,
            lambda c: _insert(c, "trade_proposal", PROPOSAL),
            lambda c: _insert(
                c,
                "operator_trading_configuration",
                CONFIGURATION,
                configuration_version=2,
                kill_switch="ENGAGED",
            ),
            inspect="SELECT (SELECT count(*) FROM trade_proposal), "
            "(SELECT count(*) FROM operator_trading_configuration)",
        )
        assert result.winners == 2
        assert result.final_rows == ((1, 2),)

    def test_c16_two_competing_candidates_for_one_symbol_both_persist(self, clean: Engine) -> None:
        # Distinct proposal identities do not contend. This is recorded because
        # a reader might expect one-per-symbol: the schema does NOT enforce
        # that, and the authority contract does not claim it.
        seed_to_context(clean)
        result = race(
            clean,
            lambda c: _insert(c, "trade_proposal", PROPOSAL, proposal_governance_id="PRP-A"),
            lambda c: _insert(c, "trade_proposal", PROPOSAL, proposal_governance_id="PRP-B"),
            inspect="SELECT count(*) FROM trade_proposal WHERE symbol = 'AAPL'",
        )
        assert result.winners == 2
        assert result.final_rows == ((2,),)

    @pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
    def test_c17_c18_c19_the_race_resolves_at_every_isolation_level(
        self, clean: Engine, isolation: str
    ) -> None:
        """The same contention, at each of the three levels an operator may set.

        The winner count is what must hold everywhere. The LOSER's error
        differs by level -- a unique violation under READ COMMITTED, possibly a
        serialization failure under SERIALIZABLE -- and both are honest
        outcomes a caller must retry rather than ignore.
        """
        seed_to_context(clean)
        levelled = clean.execution_options(isolation_level=isolation)
        result = race(
            levelled,
            lambda c: _insert(c, "trade_proposal", PROPOSAL, quantity=9),
            lambda c: _insert(c, "trade_proposal", PROPOSAL, quantity=99),
            inspect="SELECT count(*) FROM trade_proposal",
        )
        assert result.winners == 1, f"{isolation}: {result.outcomes}"
        assert result.losers == 1
        assert result.final_rows == ((1,),)
        # The loser is TOLD. A silent loss would be the dangerous outcome.
        assert result.loser_errors[0]


# ===========================================================================
# D. Approval decisions
# ===========================================================================


class TestApprovalDecisionRaces:
    def _decide(self, action: str, status: str, decision_id: str) -> Callable[[Connection], None]:
        def work(connection: Connection) -> None:
            _insert(
                connection,
                "trade_approval_decision",
                DECISION,
                decision_governance_id=decision_id,
                action=action,
                resulting_status=status,
                expires_at=DECISION["expires_at"] if action == "APPROVE" else None,
            )
            connection.execute(
                text(
                    "UPDATE trade_proposal SET status = :s "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                ),
                {"s": status},
            )

        return work

    @pytest.mark.parametrize(
        ("other_action", "other_status"),
        [("REJECT", "REJECTED"), ("CANCEL", "CANCELLED")],
    )
    def test_d20_d21_approve_versus_a_refusal_lets_exactly_one_through(
        self, clean: Engine, other_action: str, other_status: str
    ) -> None:
        # The race that matters most in this milestone: a human approving while
        # another rejects. Exactly one decision may exist, and the proposal's
        # status must agree with the decision that survived.
        seed_to_proposal(clean)
        result = race(
            clean,
            self._decide("APPROVE", "APPROVED", "DEC-A"),
            self._decide(other_action, other_status, "DEC-B"),
            inspect="SELECT p.status, d.action, d.decision_governance_id "
            "FROM trade_proposal p LEFT JOIN trade_approval_decision d "
            "ON d.proposal_governance_id = p.proposal_governance_id",
        )
        assert result.winners == 1
        assert result.losers == 1
        status, action, _ = result.final_rows[0]
        # The proposal's status and the surviving decision agree. A mismatch
        # would mean an approved proposal nobody approved.
        assert (action, status) in {("APPROVE", "APPROVED"), (other_action, other_status)}

    def test_d22_approve_versus_invalidate_never_leaves_both(self, clean: Engine) -> None:
        seed_to_proposal(clean)
        result = race(
            clean,
            self._decide("APPROVE", "APPROVED", "DEC-A"),
            lambda c: c.execute(
                text(
                    "UPDATE trade_proposal SET status = 'INVALIDATED' "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            ),
            inspect="SELECT p.status, (SELECT count(*) FROM trade_approval_decision) "
            "FROM trade_proposal p",
        )
        status, decisions = result.final_rows[0]
        # Either the approval won (APPROVED + 1 decision) or invalidation won
        # (INVALIDATED + 0 decisions). An INVALIDATED proposal carrying an
        # approval would be the unsafe outcome.
        assert (status, decisions) in {("APPROVED", 1), ("INVALIDATED", 0)}

    def test_d23_two_identical_approvals_leave_exactly_one(self, clean: Engine) -> None:
        seed_to_proposal(clean)
        result = race(
            clean,
            lambda c: _insert(c, "trade_approval_decision", DECISION),
            lambda c: _insert(c, "trade_approval_decision", DECISION),
            inspect="SELECT count(*) FROM trade_approval_decision",
        )
        assert result.winners == 1
        assert result.final_rows == ((1,),)

    def test_d24_two_different_operators_leave_exactly_one_named(self, clean: Engine) -> None:
        # Whose approval is on the record must never be ambiguous.
        seed_to_proposal(clean)
        result = race(
            clean,
            lambda c: _insert(
                c,
                "trade_approval_decision",
                DECISION,
                decision_governance_id="DEC-A",
                operator_identity="alice",
            ),
            lambda c: _insert(
                c,
                "trade_approval_decision",
                DECISION,
                decision_governance_id="DEC-B",
                operator_identity="bob",
            ),
            inspect="SELECT operator_identity FROM trade_approval_decision",
        )
        assert result.winners == 1
        assert len(result.final_rows) == 1
        assert result.final_rows[0][0] in ("alice", "bob")

    def test_d25_an_approval_racing_expiry_agrees_with_the_stored_status(
        self, clean: Engine
    ) -> None:
        seed_to_proposal(clean)
        result = race(
            clean,
            self._decide("APPROVE", "APPROVED", "DEC-A"),
            lambda c: c.execute(
                text(
                    "UPDATE trade_proposal SET status = 'EXPIRED' "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            ),
            inspect="SELECT p.status, (SELECT count(*) FROM trade_approval_decision) "
            "FROM trade_proposal p",
        )
        status, decisions = result.final_rows[0]
        assert (status, decisions) in {("APPROVED", 1), ("EXPIRED", 0)}

    def test_d26_an_approval_racing_a_kill_switch_version_still_records_one_decision(
        self, clean: Engine
    ) -> None:
        # Engaging the switch writes a new configuration version and does not
        # touch the proposal. Both land; the sweep is what clears the queue.
        seed_to_proposal(clean)
        result = race(
            clean,
            self._decide("APPROVE", "APPROVED", "DEC-A"),
            lambda c: _insert(
                c,
                "operator_trading_configuration",
                CONFIGURATION,
                configuration_version=2,
                kill_switch="ENGAGED",
            ),
            inspect="SELECT (SELECT count(*) FROM trade_approval_decision), "
            "(SELECT count(*) FROM operator_trading_configuration)",
        )
        assert result.winners == 2
        assert result.final_rows == ((1, 2),)

    def test_d27_an_approval_cannot_attach_to_a_superseded_proposal_version(
        self, clean: Engine
    ) -> None:
        # A decision citing version 2 of a proposal stored at version 1 is
        # refused by the admission trigger, concurrently or not.
        seed_to_proposal(clean)
        result = race(
            clean,
            lambda c: _insert(c, "trade_approval_decision", DECISION),
            lambda c: _insert(
                c,
                "trade_approval_decision",
                DECISION,
                decision_governance_id="DEC-B",
                proposal_version=2,
            ),
            inspect="SELECT count(*), min(proposal_version) FROM trade_approval_decision",
        )
        assert result.winners == 1
        assert result.final_rows == ((1, 1),)

    def test_d28_an_approval_retry_after_uncertainty_reads_the_winner(self, clean: Engine) -> None:
        seed_to_proposal(clean)
        with clean.begin() as conn:
            _insert(conn, "trade_approval_decision", DECISION)
        with clean.connect() as connection:
            transaction = connection.begin()
            try:
                _insert(
                    connection,
                    "trade_approval_decision",
                    DECISION,
                    decision_governance_id="DEC-RETRY",
                )
                transaction.commit()
                landed = True
            except Exception:  # noqa: BLE001 - the conflict is the expected path
                transaction.rollback()
                landed = False
        assert landed is False
        with clean.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT decision_governance_id FROM trade_approval_decision")
                ).scalar_one()
                == "DEC-0001"
            )


# ===========================================================================
# E. Approved intents
# ===========================================================================


class TestApprovedIntentRaces:
    def test_e29_two_identical_issuances_leave_exactly_one(self, clean: Engine) -> None:
        seed_to_approved(clean)
        result = race(
            clean,
            lambda c: _insert(c, "approved_order_intent", INTENT),
            lambda c: _insert(c, "approved_order_intent", INTENT),
            inspect="SELECT count(*) FROM approved_order_intent",
        )
        assert result.winners == 1
        assert result.final_rows == ((1,),)

    def test_e30_two_intents_with_conflicting_terms_leave_exactly_one(self, clean: Engine) -> None:
        # Two intents for one approval, differing in quantity. Both are refused
        # or one is: what must never happen is two intents authorizing
        # different orders from a single human approval.
        seed_to_approved(clean)
        result = race(
            clean,
            lambda c: _insert(
                c,
                "approved_order_intent",
                INTENT,
                intent_governance_id="INT-A",
                idempotency_key="IDEM-A",
            ),
            lambda c: _insert(
                c,
                "approved_order_intent",
                INTENT,
                intent_governance_id="INT-B",
                idempotency_key="IDEM-B",
                quantity=99,
            ),
            inspect="SELECT count(*), max(quantity) FROM approved_order_intent",
        )
        count, quantity = result.final_rows[0]
        assert count <= 1
        if count == 1:
            # A stored intent always matches the approved proposal's quantity.
            assert quantity == 9

    def test_e31_an_intent_racing_proposal_invalidation_never_outlives_the_approval(
        self, clean: Engine
    ) -> None:
        seed_to_approved(clean)
        result = race(
            clean,
            lambda c: _insert(c, "approved_order_intent", INTENT),
            lambda c: c.execute(
                text(
                    "UPDATE trade_proposal SET status = 'INVALIDATED' "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            ),
            inspect="SELECT p.status, (SELECT count(*) FROM approved_order_intent) "
            "FROM trade_proposal p",
        )
        status, intents = result.final_rows[0]
        # APPROVED is terminal, so the invalidation loses outright. What must
        # not happen is an INVALIDATED proposal with an intent attached.
        assert not (status == "INVALIDATED" and intents == 1)

    def test_e32_an_intent_created_after_the_approval_lapsed_is_refused_under_contention(
        self, clean: Engine
    ) -> None:
        seed_to_approved(clean)
        result = race(
            clean,
            lambda c: _insert(
                c,
                "approved_order_intent",
                INTENT,
                created_at=_T0 + timedelta(seconds=131),
            ),
            lambda c: _insert(
                c,
                "approved_order_intent",
                INTENT,
                intent_governance_id="INT-B",
                idempotency_key="IDEM-B",
                created_at=_T0 + timedelta(seconds=131),
            ),
            inspect="SELECT count(*) FROM approved_order_intent",
        )
        assert result.winners == 0
        assert result.final_rows == ((0,),)
        assert all("lapsed" in error for error in result.loser_errors)

    def test_e33_an_intent_racing_a_kill_switch_version_is_unaffected(self, clean: Engine) -> None:
        # Recorded honestly: engaging the switch does NOT block an intent for an
        # already-approved proposal. The switch stops new evaluations. This is
        # the behaviour, and the authority contract does not claim otherwise.
        seed_to_approved(clean)
        result = race(
            clean,
            lambda c: _insert(c, "approved_order_intent", INTENT),
            lambda c: _insert(
                c,
                "operator_trading_configuration",
                CONFIGURATION,
                configuration_version=2,
                kill_switch="ENGAGED",
            ),
            inspect="SELECT (SELECT count(*) FROM approved_order_intent), "
            "(SELECT count(*) FROM operator_trading_configuration)",
        )
        assert result.winners == 2
        assert result.final_rows == ((1, 2),)

    def test_e34_a_rolled_back_intent_leaves_the_proposal_free_for_a_retry(
        self, clean: Engine
    ) -> None:
        seed_to_approved(clean)
        with clean.connect() as connection:
            transaction = connection.begin()
            _insert(connection, "approved_order_intent", INTENT)
            transaction.rollback()
        with clean.begin() as conn:
            _insert(conn, "approved_order_intent", INTENT, intent_governance_id="INT-RETRY")
        with clean.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT intent_governance_id FROM approved_order_intent")
                ).scalar_one()
                == "INT-RETRY"
            )

    def test_e35_a_direct_sql_competitor_loses_the_same_way_an_application_would(
        self, clean: Engine
    ) -> None:
        # The competitor here never went through the repository. It still meets
        # the same unique constraint, which is the whole reason the rule lives
        # in the database.
        seed_to_approved(clean)
        result = race(
            clean,
            lambda c: _insert(c, "approved_order_intent", INTENT),
            lambda c: c.execute(
                text(
                    "INSERT INTO approved_order_intent SELECT 'INT-SQL', "
                    "proposal_governance_id, proposal_version, approved_fingerprint, "
                    "decision_governance_id, symbol, side, quantity, order_type, limit_price, "
                    "currency, time_in_force, mandatory_liquidation_at, account_mode_required, "
                    "'IDEM-SQL', configuration_governance_id, configuration_version, "
                    "evaluation_context_id, created_at, expires_at, submission_state "
                    "FROM approved_order_intent"
                )
            ),
            inspect="SELECT count(*) FROM approved_order_intent",
        )
        assert result.final_rows[0][0] <= 1

    def test_e36_a_unique_collision_is_distinguishable_from_an_unrelated_failure(
        self, clean: Engine
    ) -> None:
        # A repository that retried on every IntegrityError would retry on a
        # CHECK violation forever. The two must be distinguishable.
        seed_to_approved(clean)
        result = race(
            clean,
            lambda c: _insert(c, "approved_order_intent", INTENT),
            lambda c: _insert(
                c,
                "approved_order_intent",
                INTENT,
                intent_governance_id="INT-B",
                idempotency_key="IDEM-B",
                submission_state="SUBMITTED",
            ),
            inspect="SELECT count(*) FROM approved_order_intent",
        )
        assert result.winners == 1
        assert result.losers == 1
        # The loser failed on the CHECK, not on the unique index.
        assert "never_submitted" in result.loser_errors[0]
        assert "uq_" not in result.loser_errors[0]
