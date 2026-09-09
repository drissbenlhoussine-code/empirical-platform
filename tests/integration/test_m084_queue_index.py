"""MILESTONE-084 -- the operator's queue must not degrade with the table.

`trade_proposal` is append-only: nothing is ever deleted, so the table only
grows for the life of a deployment. The performance campaign measured the queue
query -- the newest PREPARED proposals awaiting a decision -- doing a sequential
scan of every row and then a top-N sort to return fifty: 0.12 ms at zero rows,
2.8 ms at ten thousand, 6.6 ms at twenty-five thousand, touching 834 shared
buffers. Linear growth in a table that never shrinks is the kind of thing that
looks acceptable in review and becomes a problem a year in.

`ix_trade_proposal_prepared_queue` fixes it: partial on PREPARED, carrying the
ORDER BY columns in the query's own order, so the LIMIT stops the scan instead
of sorting the whole match set. Re-measured: 0.163 ms at twenty-five thousand
rows, four buffers, and flat across every scale.

These tests assert the PLAN, not the timing. A timing threshold on shared CI
hardware fails for reasons that have nothing to do with this code, and passes on
a fast machine even after the index is dropped. The plan is the thing that
actually changed, so the plan is what is checked.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration.test_m084_decision_to_approval_postgres_attacks import (
    CONFIGURATION,
    CONTEXT,
    PROPOSAL,
)

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INDEX = "ix_trade_proposal_prepared_queue"

#: Enough rows that a sequential scan is clearly the wrong plan and the planner
#: agrees. Small enough that the fixture stays quick.
_ROWS = 2_000

_QUEUE_QUERY = (
    "SELECT proposal_governance_id, symbol, quantity, created_at FROM trade_proposal "
    "WHERE status = 'PREPARED' ORDER BY created_at DESC, proposal_governance_id LIMIT 50"
)


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=4,
        max_overflow=4,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m084-queue-index",
    )


def _table(name: str, columns: object) -> sa.TableClause:
    return sa.table(name, *(sa.column(field) for field in columns))  # type: ignore[union-attr]


@pytest.fixture(scope="module")
def populated(request: pytest.FixtureRequest) -> Iterator[Engine]:
    if not _postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    engine = sa.create_engine(_config().sqlalchemy_url(), pool_size=4, max_overflow=4)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    alembic_command.upgrade(cfg, "head")

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO evaluation_evidence_watermark (watermark_governance_id) VALUES (:w)"),
            {"w": CONTEXT["watermark_governance_id"]},
        )
        conn.execute(
            sa.insert(_table("operator_trading_configuration", CONFIGURATION)).values(
                **CONFIGURATION
            )
        )
        conn.execute(sa.insert(_table("evaluation_context", CONTEXT)).values(**CONTEXT))
    rows = [
        {
            **PROPOSAL,
            "proposal_governance_id": f"PRP-IDX-{n:06d}",
            "content_fingerprint": f"{n:064x}",
        }
        for n in range(_ROWS)
    ]
    for start in range(0, len(rows), 1000):
        with engine.begin() as conn:
            conn.execute(sa.insert(_table("trade_proposal", rows[0])), rows[start : start + 1000])
    with engine.begin() as conn:
        # Without ANALYZE the planner works from defaults, and the plan this
        # file asserts would be a statement about stale statistics.
        conn.execute(text("ANALYZE trade_proposal"))
    try:
        yield engine
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine.dispose()


def _plan(engine: Engine) -> str:
    with engine.connect() as conn:
        return "\n".join(
            str(row[0])
            for row in conn.execute(text(f"EXPLAIN {_QUEUE_QUERY}")).all()  # noqa: S608
        )


class TestTheQueueIndexExistsAndIsCorrect:
    def test_the_index_is_created_by_the_migration(self, populated: Engine) -> None:
        with populated.connect() as conn:
            definition = conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"), {"n": _INDEX}
            ).scalar()
        assert definition is not None, f"{_INDEX} is missing from the schema"
        assert "created_at DESC" in definition
        assert "proposal_governance_id" in definition

    def test_the_index_is_partial_on_prepared(self, populated: Engine) -> None:
        # Partial is the point: decided proposals are eventually the great
        # majority, and a full index would carry all of them for nothing.
        with populated.connect() as conn:
            definition = conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"), {"n": _INDEX}
            ).scalar()
        assert "WHERE" in str(definition)
        assert "PREPARED" in str(definition)


class TestTheQueueQueryUsesIt:
    def test_the_plan_is_an_index_scan_and_not_a_sequential_one(self, populated: Engine) -> None:
        plan = _plan(populated)
        assert _INDEX in plan, f"the queue query stopped using {_INDEX}:\n{plan}"
        assert "Seq Scan" not in plan, f"the queue query fell back to a table scan:\n{plan}"

    def test_the_plan_does_not_sort_the_whole_match_set(self, populated: Engine) -> None:
        # The LIMIT must stop the scan. A `Sort` node here would mean every
        # PREPARED row is ordered to return fifty, which is the cost the index
        # exists to remove.
        plan = _plan(populated)
        assert "Sort" not in plan, f"the queue query is still sorting its whole match set:\n{plan}"

    def test_dropping_the_index_restores_the_scan(self, populated: Engine) -> None:
        # Anti-vacuity. Without this, the two assertions above would pass just
        # as happily against a planner that never had a choice to make.
        with populated.begin() as conn:
            conn.execute(text(f"DROP INDEX {_INDEX}"))  # noqa: S608
        try:
            degraded = _plan(populated)
            assert "Seq Scan" in degraded
            assert "Sort" in degraded
        finally:
            with populated.begin() as conn:
                conn.execute(
                    text(
                        f"CREATE INDEX {_INDEX} ON trade_proposal "  # noqa: S608
                        "(created_at DESC, proposal_governance_id) WHERE status = 'PREPARED'"
                    )
                )
        assert _INDEX in _plan(populated)
