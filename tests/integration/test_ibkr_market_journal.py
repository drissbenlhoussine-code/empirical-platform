"""Real isolated PostgreSQL concurrency/restart/immutability evidence."""

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from tests.unit.test_ibkr_market_access import NOW, Broker, plan, policy

from empirical_platform.decision_candidate.approved_plan import ExitTriggerKind
from empirical_platform.decision_candidate.market_plan import OrderPurpose
from empirical_platform.shared.persistence.database_safety import (
    TEST_IDENTITY,
    require_test_connection,
)
from empirical_platform.shared.persistence.market_journal import (
    MarketConfigurationRepository,
    MarketStore,
    PostgresMarketJournal,
)
from empirical_platform.usecases.decision_to_approval import (
    SaveOperatorTradingConfigurationCommand,
    SaveOperatorTradingConfigurationHandler,
)
from empirical_platform.usecases.decision_to_approval_io import (
    read_configuration,
    render_configuration_json,
)
from empirical_platform.usecases.market_access import MarketAccessService


@pytest.fixture(scope="module")
def store() -> Iterator[MarketStore]:
    url = os.environ.get("EMPIRICAL_IBKR_TEST_URL")
    if not url:
        pytest.skip("explicit IBKR isolated TEST database not configured")
    engine = create_engine(url)
    with engine.connect() as connection:
        require_test_connection(connection)
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
        connection.commit()
        config = Config("alembic-market-access.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    result = MarketStore(engine, expected_identity=TEST_IDENTITY)
    repository = MarketConfigurationRepository(
        result, encode=render_configuration_json, decode=read_configuration
    )
    saved = SaveOperatorTradingConfigurationHandler(configuration_repository=repository).handle(
        SaveOperatorTradingConfigurationCommand(policy())
    )
    assert repository.get(saved.configuration_governance_id, saved.configuration_version) == saved
    assert repository.latest(saved.configuration_governance_id) == saved
    yield result
    engine.dispose()


def test_full_journal_restart_and_concurrent_dispatch(store: MarketStore) -> None:
    journal = PostgresMarketJournal(store)
    p = replace(plan(), plan_id="PLAN-" + uuid4().hex)
    journal.save_plan(p)
    journal.approve(p.plan_id, "test-owner", p.fingerprint, NOW)
    with store.transaction() as connection:
        connection.execute(text("UPDATE market_safety SET engaged=false"))
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(
                lambda order_id: journal.reserve(
                    p, OrderPurpose.ENTRY, order_id, Decimal("1"), Decimal("100"), NOW
                ),
                (1, 2),
            )
        )
    records = [r for r in results if r is not None]
    assert len(records) == 1
    record = records[0]
    restarted = PostgresMarketJournal(store)
    assert restarted.get_plan(p.plan_id) == p
    assert restarted.dispatch(p.plan_id, OrderPurpose.ENTRY) == record
    broker = Broker()
    broker.sent.append(record)
    broker.fill(OrderPurpose.ENTRY)
    service = MarketAccessService(journal=restarted, broker=broker, policy=policy, now=lambda: NOW)
    service.submit_entry(p.plan_id)
    assert len(broker.sent) == 1
    assert restarted.truth(p.plan_id, OrderPurpose.ENTRY) == broker.truths[OrderPurpose.ENTRY]
    broker.bid, broker.ask = Decimal("110"), Decimal("111")
    service.manage_exits_once(now=NOW)
    assert len(broker.sent) == 2
    broker.fill(OrderPurpose.CLOSE)
    service.manage_exits_once(now=NOW)
    assert not restarted.active_plans()
    with store.transaction() as connection:
        zero = (
            connection.execute(
                text("SELECT * FROM market_zero_verification WHERE plan_id=:id"), {"id": p.plan_id}
            )
            .mappings()
            .one()
        )
        assert zero["position_count"] == 0 and zero["account_fingerprint"] == p.account.reference
    assert restarted.entry_count(NOW - timedelta(seconds=1)) == 1
    assert not restarted.claim_trigger(p.plan_id, ExitTriggerKind.STOP, NOW)


def test_identity_and_raw_mutation_refused(store: MarketStore) -> None:
    with pytest.raises(ValueError):
        with MarketStore(
            store.engine, expected_identity="PERSONAL_PAPER:MARKET_ACCESS:wrong"
        ).transaction():
            pytest.fail("wrong identity reached transaction")
    for sql in (
        "UPDATE market_configuration SET fingerprint=repeat('a',64)",
        "DELETE FROM market_observation",
        "UPDATE market_dispatch SET quantity=0.5",
    ):
        with pytest.raises(DBAPIError):
            with store.transaction() as connection:
                connection.execute(text(sql))


def test_cross_plan_concurrency_and_ambiguous_recovery(store: MarketStore) -> None:
    journal = PostgresMarketJournal(store)
    plans = [replace(plan(), plan_id="PLAN-" + uuid4().hex) for _ in range(2)]
    for p in plans:
        journal.save_plan(p)
        journal.approve(p.plan_id, "test-owner", p.fingerprint, NOW)
    with ThreadPoolExecutor(max_workers=2) as workers:
        records = list(
            workers.map(
                lambda i: journal.reserve(
                    plans[i], OrderPurpose.ENTRY, 10 + i, Decimal("1"), Decimal("100"), NOW
                ),
                (0, 1),
            )
        )
    assert sum(r is not None for r in records) == 1
    i = next(i for i, r in enumerate(records) if r is not None)
    record = records[i]
    assert record is not None
    journal.observe(plans[i], record, None)
    assert (
        PostgresMarketJournal(store).dispatch(plans[i].plan_id, OrderPurpose.ENTRY).state
        == "UNKNOWN"
    )
    assert (
        journal.reserve(plans[1 - i], OrderPurpose.ENTRY, 15, Decimal("1"), Decimal("100"), NOW)
        is None
    )


def test_real_market_journal_dump_restore_preserves_approval_unknown_and_zero(
    store: MarketStore, tmp_path: Path
) -> None:
    """Synthetic engineering state restored only into an independently marked TEST DB."""
    target_url = os.environ.get("EMPIRICAL_IBKR_RESTORE_TEST_URL")
    if not target_url:
        pytest.skip("explicit isolated restore TEST database not configured")
    target = create_engine(target_url)
    tables = (
        "alembic_version",
        "market_configuration",
        "market_plan",
        "market_dispatch",
        "market_observation",
        "market_cancel_claim",
        "market_safety",
        "market_zero_verification",
    )

    def snapshot(database: MarketStore) -> dict[str, list[str]]:
        with database.transaction() as connection:
            return {
                table: sorted(
                    json.dumps(row, sort_keys=True, default=str)
                    for row in connection.execute(
                        text(f"SELECT row_to_json(t) FROM {table} t")  # noqa: S608 - fixed table tuple
                    ).scalars()
                )
                for table in tables
            }

    def run_pg(
        name: str, engine_url: object, arguments: list[str]
    ) -> subprocess.CompletedProcess[str]:
        # sqlalchemy URL is retained locally; credentials never enter command arguments.
        from sqlalchemy.engine import make_url

        url = make_url(engine_url)
        executable = shutil.which(name)
        assert executable, f"{name} required for the isolated restore rehearsal"
        environment = dict(os.environ)
        environment.update(
            PGHOST=url.host or "",
            PGPORT=str(url.port or ""),
            PGUSER=url.username or "",
            PGDATABASE=url.database or "",
            PGPASSWORD=url.password or "",
        )
        result = subprocess.run(  # noqa: S603 - fixed PostgreSQL tools, guarded TEST endpoints
            [executable, *arguments],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{name} failed (server text withheld)"
        return result

    try:
        assert target.url != store.engine.url
        with store.engine.connect() as connection:
            require_test_connection(connection)
        with target.begin() as connection:
            require_test_connection(connection)  # Must precede all destructive SQL.
            connection.exec_driver_sql("DROP SCHEMA public CASCADE")
            connection.exec_driver_sql("CREATE SCHEMA public")
        expected = snapshot(store)
        assert expected["market_zero_verification"]
        assert any('"UNKNOWN"' in row for row in expected["market_dispatch"])
        dump = tmp_path / "synthetic-market-journal.dump"
        run_pg("pg_dump", store.engine.url, ["--format=custom", "--file", str(dump)])
        assert dump.stat().st_size > 0
        listing = run_pg("pg_restore", target.url, ["--list", str(dump)]).stdout
        assert "market_zero_verification" in listing
        run_pg(
            "pg_restore",
            target.url,
            ["--exit-on-error", "--dbname", target.url.database, str(dump)],
        )
        restored = MarketStore(target, expected_identity=TEST_IDENTITY)
        assert snapshot(restored) == expected
        for candidate in PostgresMarketJournal(restored).active_plans():
            record = PostgresMarketJournal(restored).dispatch(candidate.plan_id, OrderPurpose.ENTRY)
            if record is not None:
                assert record.state == "UNKNOWN"
    finally:
        target.dispose()
