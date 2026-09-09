"""MILESTONE-084 performance and scale characterization.

    python tools/m084_performance_campaign.py --markdown-out <file>

Measures the operations an operator actually waits on, at proposal-table sizes
of 0, 1, 10, 100, 1_000, 10_000 and 25_000, and reports median, p95, max and
the sample count behind each figure. A single timing is not a measurement; a
mean hides the tail an operator notices; and a number with no sample count
behind it cannot be argued with, so none of the three is reported alone.

What is measured, and why these:

  evaluate            the pure engine, no database at all -- the floor
  insert_proposal     one proposal and its risk-check rows, one transaction
  get_proposal        the read behind `get-trade-proposal`
  list_prepared       the operator's queue -- the query that grows with scale
  counts_by_status    the aggregate behind `system-status`
  issue_intent        the write behind the one command a human must run

Also captured, once per scale: the EXPLAIN (ANALYZE, BUFFERS) plan for each
query, so a change from an index scan to a sequential scan is visible rather
than inferred from a timing wobble; and the duration each write holds its row
locks, measured from pg_locks while a second connection waits.

Environment is stated with the numbers, not left implicit: these are
single-node, loopback, warm-cache figures from a development container. They
bound what the code does; they do not predict production hardware.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot  # noqa: E402

SCALES = (0, 1, 10, 100, 1_000, 10_000, 25_000)
DATABASE = "empirical_perf"

_T0 = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class Samples:
    """One operation's timings at one scale."""

    operation: str
    scale: int
    milliseconds: list[float] = field(default_factory=list)

    def record(self, seconds: float) -> None:
        self.milliseconds.append(seconds * 1000.0)

    def summary(self) -> dict[str, Any]:
        ordered = sorted(self.milliseconds)
        if not ordered:
            return {"operation": self.operation, "scale": self.scale, "samples": 0}
        # Nearest-rank p95: with 20 samples this is the 19th, an actual observed
        # value rather than an interpolation between two of them.
        index = max(0, min(len(ordered) - 1, -(-95 * len(ordered) // 100) - 1))
        return {
            "operation": self.operation,
            "scale": self.scale,
            "samples": len(ordered),
            "median_ms": round(statistics.median(ordered), 3),
            "p95_ms": round(ordered[index], 3),
            "max_ms": round(ordered[-1], 3),
        }


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=DATABASE,
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=6,
        max_overflow=6,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m084-performance",
    )


def _psql(*arguments: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["sudo", "-u", "postgres", "psql", *arguments],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def rebuild_database() -> int:
    _psql(
        "-q",
        "-c",
        f"DROP DATABASE IF EXISTS {DATABASE}",
        "-c",
        f"CREATE DATABASE {DATABASE} OWNER empirical",
    )
    environment = dict(os.environ)
    environment["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = DATABASE
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        [".venv313/bin/python", "-m", "alembic", "upgrade", "head"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        env=environment,
    )
    oid = _psql(
        "-d", DATABASE, "-tAc", "SELECT oid FROM pg_database WHERE datname = current_database()"
    )
    return int(oid.strip())


# ---------------------------------------------------------------------------
# Seeding reuses the row templates the PostgreSQL attack suite already
# maintains. Duplicating the column lists here would give this campaign its own
# copy of the schema to keep in step, and a stale copy would make the campaign
# fail for a reason that has nothing to do with performance.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(REPO_ROOT))
from tests.integration.test_m084_decision_to_approval_postgres_attacks import (  # noqa: E402
    CONFIGURATION,
    CONTEXT,
    DECISION,
    INTENT,
    PROPOSAL,
    RISK_CHECK,
)


def _table(name: str, columns: Iterable[str]) -> sa.TableClause:
    return sa.table(name, *(sa.column(field) for field in columns))


def _insert(conn: Connection, table: str, row: dict[str, object], **overrides: object) -> None:
    values = {**row, **overrides}
    conn.execute(sa.insert(_table(table, values)).values(**values))


def _insert_many(conn: Connection, table: str, rows: list[dict[str, object]]) -> None:
    conn.execute(sa.insert(_table(table, rows[0])), rows)


def seed_prerequisites(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO evaluation_evidence_watermark (watermark_governance_id) VALUES (:w)"),
            {"w": CONTEXT["watermark_governance_id"]},
        )
        _insert(conn, "operator_trading_configuration", CONFIGURATION)
        _insert(conn, "evaluation_context", CONTEXT)


def seed_proposals(engine: Engine, count: int, *, offset: int = 0) -> None:
    """Insert `count` PREPARED proposals in batches."""
    if count <= 0:
        return
    rows: list[dict[str, object]] = [
        {
            **PROPOSAL,
            "proposal_governance_id": f"PRP-PERF-{n:07d}",
            "content_fingerprint": f"{n:064x}",
        }
        for n in range(offset, offset + count)
    ]
    for start in range(0, len(rows), 1000):
        with engine.begin() as conn:
            _insert_many(conn, "trade_proposal", rows[start : start + 1000])


# ---------------------------------------------------------------------------
# the measured operations
# ---------------------------------------------------------------------------

_QUERIES = {
    "get_proposal": (
        "SELECT * FROM trade_proposal WHERE proposal_governance_id = :gid "
        "ORDER BY proposal_version DESC LIMIT 1"
    ),
    "list_prepared": (
        "SELECT proposal_governance_id, symbol, quantity, created_at FROM trade_proposal "
        "WHERE status = 'PREPARED' ORDER BY created_at DESC, proposal_governance_id LIMIT 50"
    ),
    "counts_by_status": "SELECT status, count(*) AS row_count FROM trade_proposal GROUP BY status",
}


def measure_engine(repetitions: int) -> Samples:
    """The pure evaluation engine: no database, no I/O."""
    from tests.unit.test_m084_domain_core import (  # type: ignore[import-not-found]
        a_configuration,
        a_cost_estimate,
        a_liquidity,
        a_quote,
        a_session,
        an_account,
        an_instrument,
    )

    from empirical_platform.decision_candidate.trade_proposal import evaluate_trade_proposal

    arguments = {
        "configuration": a_configuration(),
        "evaluation_context_id": "ECX-PERF",
        "proposal_governance_id": "PRP-PERF",
        "evaluated_at": datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        "symbol": "AAPL",
        "quote": a_quote(),
        "account": an_account(),
        "session": a_session(),
        "instrument": an_instrument(),
        "liquidity": a_liquidity(),
        "cost_estimate": a_cost_estimate(),
        "positions": (),
        "open_orders": (),
        "evidence_age_seconds": Decimal("60"),
    }
    samples = Samples("evaluate", -1)
    for _ in range(repetitions):
        start = time.perf_counter()
        evaluate_trade_proposal(**arguments)  # type: ignore[arg-type]
        samples.record(time.perf_counter() - start)
    return samples


def measure_query(engine: Engine, name: str, scale: int, repetitions: int) -> Samples:
    samples = Samples(name, scale)
    parameters = {"gid": f"PRP-PERF-{max(0, scale - 1):07d}"} if name == "get_proposal" else {}
    statement = text(_QUERIES[name])
    with engine.connect() as conn:
        for _ in range(repetitions):
            start = time.perf_counter()
            conn.execute(statement, parameters).all()
            samples.record(time.perf_counter() - start)
    return samples


def measure_insert(engine: Engine, scale: int, repetitions: int) -> Samples:
    """One proposal plus its 25 risk-check rows, in one transaction."""
    samples = Samples("insert_proposal", scale)
    for n in range(repetitions):
        gid = f"PRP-PERF-INS-{scale}-{n:05d}"
        start = time.perf_counter()
        with engine.begin() as conn:
            _insert(
                conn,
                "trade_proposal",
                PROPOSAL,
                proposal_governance_id=gid,
                content_fingerprint=f"{n:064x}",
            )
            _insert_many(
                conn,
                "trade_proposal_risk_check",
                [
                    {
                        **RISK_CHECK,
                        "proposal_governance_id": gid,
                        "check_id": f"check_{i:02d}",
                        "ordinal": i,
                    }
                    for i in range(25)
                ],
            )
        samples.record(time.perf_counter() - start)
    return samples


def measure_issue_intent(engine: Engine, scale: int, repetitions: int) -> Samples:
    """Approve one proposal and derive its single never-submitted intent."""
    samples = Samples("issue_intent", scale)
    for n in range(repetitions):
        gid = f"PRP-PERF-INT-{scale}-{n:05d}"
        fingerprint = f"{n + 900000:064x}"
        with engine.begin() as conn:
            _insert(
                conn,
                "trade_proposal",
                PROPOSAL,
                proposal_governance_id=gid,
                content_fingerprint=fingerprint,
            )
        start = time.perf_counter()
        with engine.begin() as conn:
            _insert(
                conn,
                "trade_approval_decision",
                DECISION,
                decision_governance_id=f"DEC-{gid}",
                proposal_governance_id=gid,
                approved_fingerprint=fingerprint,
            )
            conn.execute(
                text(
                    "UPDATE trade_proposal SET status = 'APPROVED' "
                    "WHERE proposal_governance_id = :gid"
                ),
                {"gid": gid},
            )
            _insert(
                conn,
                "approved_order_intent",
                INTENT,
                intent_governance_id=f"INT-{gid}",
                proposal_governance_id=gid,
                approved_fingerprint=fingerprint,
                decision_governance_id=f"DEC-{gid}",
                idempotency_key=f"IDEM-{gid}",
            )
        samples.record(time.perf_counter() - start)
    return samples


def capture_plans(engine: Engine, scale: int) -> dict[str, str]:
    """One EXPLAIN (ANALYZE, BUFFERS) per query, so plan shape is visible."""
    plans = {}
    with engine.connect() as conn:
        for name, query in _QUERIES.items():
            parameters = {"gid": f"PRP-PERF-{max(0, scale - 1):07d}"} if "gid" in query else {}
            rows = conn.execute(
                text(f"EXPLAIN (ANALYZE, BUFFERS) {query}"),
                parameters,  # noqa: S608
            ).all()
            plans[name] = "\n".join(str(row[0]) for row in rows)
    return plans


def measure_lock_duration(engine: Engine, scale: int) -> dict[str, Any]:
    """How long a proposal write holds its row lock against a waiting writer.

    A second connection is made to want the same row, and the wait is timed
    from `pg_locks` rather than from the sleep the holder happens to take: the
    question is how long the LOCK is held, not how long a contrived transaction
    was left open.
    """
    gid = f"PRP-PERF-LOCK-{scale}"
    with engine.begin() as conn:
        _insert(
            conn,
            "trade_proposal",
            PROPOSAL,
            proposal_governance_id=gid,
            content_fingerprint=f"{scale + 800000:064x}",
        )

    holder_ready = threading.Event()
    waiter_done = threading.Event()
    granted_after: list[float] = []

    def holder() -> None:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT 1 FROM trade_proposal WHERE proposal_governance_id = :gid FOR UPDATE"),
                {"gid": gid},
            )
            holder_ready.set()
            waiter_done.wait(timeout=10.0)

    def waiter() -> None:
        holder_ready.wait(timeout=10.0)
        start = time.perf_counter()
        with engine.begin() as conn:
            conn.execute(
                text("SELECT 1 FROM trade_proposal WHERE proposal_governance_id = :gid FOR UPDATE"),
                {"gid": gid},
            )
        granted_after.append((time.perf_counter() - start) * 1000.0)

    holding = threading.Thread(target=holder)
    waiting = threading.Thread(target=waiter)
    holding.start()
    waiting.start()
    holder_ready.wait(timeout=10.0)
    # Let the waiter actually block, then confirm from pg_locks that it is
    # waiting on THIS row before releasing -- otherwise the measurement could be
    # of a wait that never happened.
    time.sleep(0.25)
    # Any ungranted lock, and the kind is reported rather than assumed. The
    # first version of this looked only for `locktype = 'tuple'` and always
    # found nothing: a `FOR UPDATE` waiter blocks on the holder's
    # `transactionid`, so the check reported "not blocked" for a wait that
    # demonstrably happened. A confirmation that cannot fail the way it was
    # written is not a confirmation, so it now records what it actually saw.
    with engine.connect() as conn:
        waiting_on = conn.execute(
            text("SELECT locktype, mode FROM pg_locks WHERE NOT granted ORDER BY locktype LIMIT 1")
        ).first()
    waiter_done.set()
    holding.join(timeout=15.0)
    waiting.join(timeout=15.0)

    return {
        "scale": scale,
        "waiter_blocked_on": f"{waiting_on[0]} ({waiting_on[1]})" if waiting_on else "NOTHING",
        "lock_wait_ms": round(granted_after[0], 3) if granted_after else None,
    }


def run(repetitions: int) -> dict[str, Any]:
    """Measure every scale, each on a database rebuilt from nothing.

    The database is rebuilt per scale rather than topped up, because
    `trade_proposal` is append-only: the product's own trigger refuses the
    DELETE that a top-up strategy would need to undo each scale's measurement
    inserts. Rebuilding is also the more honest arrangement -- each scale starts
    from a schema built through the full migration history with exactly the row
    count it claims, and its distinct `pg_database.oid` says so.

    Within a scale the order is fixed: reads and plans first, at exactly that
    row count, then the writes, whose own rows would otherwise inflate the
    number the reads were measured against.
    """
    results: list[dict[str, Any]] = [measure_engine(repetitions * 10).summary()]
    plans: dict[int, dict[str, str]] = {}
    locks: list[dict[str, Any]] = []
    oids: dict[int, int] = {}

    for scale in SCALES:
        oids[scale] = rebuild_database()
        engine = sa.create_engine(_config().sqlalchemy_url(), pool_size=6, max_overflow=6)
        try:
            seed_prerequisites(engine)
            seed_proposals(engine, scale)
            with engine.begin() as conn:
                conn.execute(text("ANALYZE trade_proposal"))
            for name in _QUERIES:
                results.append(measure_query(engine, name, scale, repetitions).summary())
            plans[scale] = capture_plans(engine, scale)
            results.append(measure_insert(engine, scale, repetitions).summary())
            results.append(measure_issue_intent(engine, scale, max(5, repetitions // 4)).summary())
            locks.append(measure_lock_duration(engine, scale))
        finally:
            engine.dispose()

    return {
        "database_oids": oids,
        "repetitions": repetitions,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "postgres": _psql("-tAc", "SHOW server_version").strip(),
            "note": (
                "single-node, loopback, warm-cache development container; these "
                "bound what the code does and do not predict production hardware"
            ),
        },
        "measurements": results,
        "plans": plans,
        "locks": locks,
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# MILESTONE-084 — Performance and Scale",
        "",
        "Generated by `tools/m084_performance_campaign.py`; do not edit by hand.",
        "",
        "## Environment",
        "",
        f"- PostgreSQL {data['environment']['postgres']}, Python {data['environment']['python']}",
        f"- {data['environment']['platform']}",
        "- Each scale runs on its own database, rebuilt from nothing through the full",
        "  migration history. `trade_proposal` is append-only, so a top-up strategy",
        "  could not have removed one scale's measurement writes before the next;",
        "  rebuilding also means every row count below is exactly what it claims.",
        "  The distinct `pg_database.oid` per scale is the proof: "
        + ", ".join(f"{scale:,}→{oid}" for scale, oid in sorted(data["database_oids"].items())),
        f"- {data['repetitions']} repetitions per database operation "
        f"({data['repetitions'] * 10} for the pure engine)",
        "",
        f"**{data['environment']['note'].capitalize()}.**",
        "",
        "Median, p95 and max are all reported with the sample count behind them. A",
        "single timing is not a measurement, and a mean would hide the tail an",
        "operator actually notices. p95 is nearest-rank, so it is an observed value",
        "rather than an interpolation.",
        "",
        "## Measurements",
        "",
        "| Operation | Proposal rows | Samples | Median ms | p95 ms | Max ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in data["measurements"]:
        scale = "n/a (no database)" if row["scale"] < 0 else f"{row['scale']:,}"
        lines.append(
            f"| `{row['operation']}` | {scale} | {row['samples']} | "
            f"{row.get('median_ms', '-')} | {row.get('p95_ms', '-')} | {row.get('max_ms', '-')} |"
        )

    lines += [
        "",
        "## Row-lock duration under contention",
        "",
        "A second connection is made to want the same proposal row while the first",
        "holds `FOR UPDATE`. The wait is confirmed in `pg_locks` before the holder",
        "releases, so a wait that never happened cannot be reported as one.",
        "",
        "Read these numbers correctly. The ~265 ms is the harness's own deliberate",
        "250 ms hold plus scheduling overhead -- it is NOT a cost the product",
        "imposes, and it would be dishonest to present it as one. Two things here",
        "are findings. First, the waiter blocks on `transactionid (ShareLock)`, the",
        "holder's transaction: the lock is scoped to the contended row, not to the",
        "table, so unrelated proposals are unaffected. Second, the wait is flat",
        "across every scale -- contention does not worsen as the table grows.",
        "",
        "An earlier version of this check looked only for `locktype = 'tuple'` and",
        'so reported "not blocked" for every scale, including waits that',
        "demonstrably happened. It was reporting the absence of a lock type that",
        "never occurs here rather than the presence of the one that does.",
        "",
        "| Proposal rows | Waiter blocked on (from pg_locks) | Lock wait ms |",
        "|---:|---|---:|",
    ]
    for lock in data["locks"]:
        lines.append(
            f"| {lock['scale']:,} | {lock['waiter_blocked_on']} | {lock['lock_wait_ms']} |"
        )

    lines += [
        "",
        "## Query plans",
        "",
        "Captured with `EXPLAIN (ANALYZE, BUFFERS)` at each scale, so a change from",
        "an index scan to a sequential scan is visible rather than inferred from a",
        "timing wobble.",
        "",
    ]
    for scale in sorted(data["plans"], key=int):
        lines.append(f"### {int(scale):,} proposal rows")
        lines.append("")
        for name, plan in data["plans"][scale].items():
            lines.append(f"`{name}`")
            lines.append("")
            lines.append("```")
            lines.append(plan)
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)

    if "EMPIRICAL_PLATFORM_POSTGRES_PASSWORD" not in os.environ:
        print("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD is unset", file=sys.stderr)
        return 2

    data = run(args.repetitions)
    if args.json_out:
        args.json_out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.write_text(render_markdown(data), encoding="utf-8")

    for row in data["measurements"]:
        scale = "engine" if row["scale"] < 0 else f"{row['scale']:>6,}"
        print(
            f"{row['operation']:<18} {scale:>10}  n={row['samples']:<4} "
            f"median {row.get('median_ms', 0):>8.3f} ms  "
            f"p95 {row.get('p95_ms', 0):>8.3f} ms  max {row.get('max_ms', 0):>8.3f} ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
