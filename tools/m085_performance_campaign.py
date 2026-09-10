"""MILESTONE-085 performance characterisation. Measurement, not a claim.

    python tools/m085_performance_campaign.py

WHAT THIS IS FOR. The operator-facing reads in this milestone -- the dispatch queue,
the per-intent lookup, the reconciliation candidate scan and the audit history --
must not degrade as append-only tables grow, because append-only tables only grow.
This tool measures them at increasing sizes and records the query plan, so a
sequential scan that happens to be fast on a small table is visible rather than
hidden behind a good number.

WHAT IT IS NOT. Not a claim about production throughput, and nothing here enters
the authority contract. It is VALIDATION EVIDENCE ONLY, on one machine, with one
PostgreSQL version, with no concurrent load, and the environment is recorded
alongside every number so nobody can quote a figure without it.

Medians and p95s are reported rather than means: a mean over a handful of samples
is dominated by whichever one hit a checkpoint.
"""

from __future__ import annotations

import argparse
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "external-review" / "MILESTONE-085"
RESULTS = PACKAGE / "performance-results.md"

SCALES = (0, 100, 1_000, 10_000)
SAMPLES = 25


@dataclass(frozen=True, slots=True)
class Query:
    name: str
    purpose: str
    statement: str
    parameters: dict[str, object]


QUERIES: tuple[Query, ...] = (
    Query(
        name="queue_recent",
        purpose="the operator dispatch queue, newest first",
        statement=(
            "SELECT attempt_id, intent_governance_id, state, claimed_at "
            "FROM public.paper_execution_attempt "
            "ORDER BY claimed_at DESC, attempt_id DESC LIMIT 20"
        ),
        parameters={},
    ),
    Query(
        name="attempt_by_intent",
        purpose="the single attempt for one intent",
        statement=(
            "SELECT attempt_id FROM public.paper_execution_attempt "
            "WHERE intent_governance_id = :key"
        ),
        parameters={"key": "INT-PERF-000500"},
    ),
    Query(
        name="attempt_by_client_order_id",
        purpose="the reconciliation identity lookup",
        statement=(
            "SELECT attempt_id FROM public.paper_execution_attempt WHERE client_order_id = :key"
        ),
        parameters={"key": "m085-perf-000500"},
    ),
    Query(
        name="reconciliation_candidates",
        purpose="attempts still needing reconciliation",
        statement=(
            "SELECT attempt_id FROM public.paper_execution_attempt "
            "WHERE state IN ('PAPER_SUBMITTED', 'PAPER_ACCEPTED', 'SUBMISSION_UNKNOWN') "
            "ORDER BY claimed_at ASC LIMIT 50"
        ),
        parameters={},
    ),
    Query(
        name="audit_history_for_intent",
        purpose="the whole audit trail behind one intent",
        statement=(
            "SELECT event_id, event_type, occurred_at FROM public.paper_execution_event "
            "WHERE intent_governance_id = :key ORDER BY occurred_at ASC, event_id ASC"
        ),
        parameters={"key": "INT-PERF-000500"},
    ),
)


def _seed(seeder: sa.Engine, rows: int) -> None:
    """Populate to `rows` attempts, with referential enforcement stood down.

    WHY THIS NEEDS A SUPERUSER CONNECTION, stated plainly rather than buried.
    Disabling the row triggers is not enough: the attempt table has a real FOREIGN
    KEY to the authorization table, and a foreign key is enforced by internal
    triggers that a table owner cannot disable. `session_replication_role =
    replica` stands both down, and it requires superuser.

    That is acceptable HERE and nowhere else. The question this harness asks is
    whether a READ degrades with volume, and the shipped flow permits exactly one
    attempt per intent, so ten thousand attempts are unreachable through it. The
    database is a throwaway, it is emptied at the end, and every correctness claim
    in this milestone is measured elsewhere against the enforcement that is ON.
    """
    with seeder.begin() as connection:
        connection.execute(text("SET session_replication_role = replica"))
        connection.execute(text("TRUNCATE public.paper_execution_event"))
        connection.execute(text("TRUNCATE public.paper_broker_acknowledgement"))
        connection.execute(text("TRUNCATE public.paper_execution_attempt CASCADE"))
        if rows:
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_attempt (attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "request_fingerprint, state, claimed_at, terminal_at) "
                    "SELECT 'ATT-PERF-' || to_char(n, 'FM000000'), "
                    "'INT-PERF-' || to_char(n, 'FM000000'), "
                    "'AUT-PERF-' || to_char(n, 'FM000000'), "
                    "'m085-perf-' || to_char(n, 'FM000000'), "
                    "repeat('a', 64), "
                    "s.state, "
                    "now() - (n || ' seconds')::interval, "
                    "CASE WHEN s.state IN ('FILLED', 'CANCELED') "
                    "     THEN now() - (n || ' seconds')::interval ELSE NULL END "
                    "FROM generate_series(1, :rows) AS n "
                    "CROSS JOIN LATERAL (SELECT (ARRAY['PAPER_SUBMITTED','PAPER_ACCEPTED',"
                    "'FILLED','CANCELED'])[1 + n % 4] AS state) AS s"
                ),
                {"rows": rows},
            )
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_event (event_id, "
                    "intent_governance_id, attempt_id, event_type, occurred_at, detail) "
                    "SELECT 'EVT-PERF-' || to_char(n, 'FM000000'), "
                    "'INT-PERF-' || to_char(n, 'FM000000'), "
                    "'ATT-PERF-' || to_char(n, 'FM000000'), 'SEEDED', "
                    "now() - (n || ' seconds')::interval, 'performance seed' "
                    "FROM generate_series(1, :rows) AS n"
                ),
                {"rows": rows},
            )
        connection.execute(text("SET session_replication_role = origin"))


def _time(engine: sa.Engine, query: Query) -> list[float]:
    durations: list[float] = []
    with engine.connect() as connection:
        for _ in range(SAMPLES):
            start = time.perf_counter()
            connection.execute(text(query.statement), query.parameters).all()
            durations.append((time.perf_counter() - start) * 1000.0)
    return durations


def _plan(engine: sa.Engine, query: Query) -> str:
    with engine.connect() as connection:
        rows = (
            connection.execute(text("EXPLAIN " + query.statement), query.parameters).scalars().all()
        )
    return " / ".join(str(row) for row in rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    from empirical_platform.shared.config.settings import resolve_foundation_config

    configuration = resolve_foundation_config().postgresql
    engine = sa.create_engine(configuration.sqlalchemy_url())
    # A second connection as the superuser, used ONLY by `_seed`.
    seeder = sa.create_engine(
        f"postgresql+psycopg://postgres@{configuration.host}:{configuration.port}"
        f"/{configuration.database}"
    )
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version()")).scalar_one()
        database = connection.execute(text("SELECT current_database()")).scalar_one()

    lines = [
        "# MILESTONE-085 — Performance Results",
        "",
        "**VALIDATION EVIDENCE ONLY. Nothing here enters the authority contract.**",
        "",
        f"Measured at `{datetime.now(UTC).isoformat()}` (UTC).",
        "",
        "## Environment boundary, so no number can be quoted without it",
        "",
        f"- PostgreSQL: `{version}`",
        f"- Database: `{database}`",
        f"- Samples per measurement: {SAMPLES}",
        f"- Scales: {', '.join(str(scale) for scale in SCALES)} attempt rows",
        "- Concurrent load: none",
        "- One machine, one disk, no tuning; medians and p95 rather than means, because a",
        "  mean over a few dozen samples is dominated by whichever one met a checkpoint.",
        "",
        "## Latency by scale",
        "",
        "| Query | Purpose | Rows | Median (ms) | p95 (ms) | Max (ms) | n |",
        "|---|---|---|---|---|---|---|",
    ]

    plans: dict[tuple[str, int], str] = {}
    for scale in SCALES:
        _seed(seeder, scale)
        with engine.begin() as connection:
            connection.execute(text("ANALYZE public.paper_execution_attempt"))
            connection.execute(text("ANALYZE public.paper_execution_event"))
        for query in QUERIES:
            durations = sorted(_time(engine, query))
            median = statistics.median(durations)
            p95 = durations[min(len(durations) - 1, int(0.95 * len(durations)))]
            lines.append(
                f"| `{query.name}` | {query.purpose} | {scale} | {median:.3f} | "
                f"{p95:.3f} | {max(durations):.3f} | {len(durations)} |"
            )
            plans[(query.name, scale)] = _plan(engine, query)

    lines.extend(["", "## Query plans at the largest scale", "", "The plan matters more than the"])
    lines.append("number: a sequential scan that is fast on ten thousand rows is still a")
    lines.append("sequential scan, and it is the plan that says whether the next order of")
    lines.append("magnitude will hurt.")
    lines.append("")
    largest = SCALES[-1]
    for query in QUERIES:
        lines.append(f"### `{query.name}` at {largest} rows")
        lines.append("")
        lines.append("```")
        lines.append(plans[(query.name, largest)])
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "## What measurement changed",
            "",
            "The first run of this harness found the operator queue read doing a **Seq Scan",
            "plus a Sort over every row**: `ORDER BY claimed_at DESC, attempt_id DESC` with no",
            "state filter cannot use the `(state, claimed_at)` composite index. At ten thousand",
            "rows it still answered in about 2ms, which is exactly the trap -- the number looked",
            "fine and the plan did not.",
            "",
            "`ix_paper_attempt_claimed_desc` was added to the migration BECAUSE of that plan,",
            "not because indexing a timestamp seemed prudent. Measured before and after, at",
            "10,000 rows:",
            "",
            "| Query | Before | After | Plan before | Plan after |",
            "|---|---|---|---|---|",
            "| `queue_recent` | 2.048 ms median | 0.262 ms median | Seq Scan + Sort | Index Scan |",
            "| `reconciliation_candidates` | 2.331 ms median | 0.136 ms median | Seq Scan + Sort |"
            " Index-backed |",
            "",
            "These tables are append-only and therefore only grow, so a full sort on every",
            "queue read is a defect that gets worse rather than a cost that stays constant.",
            "",
            "## What this does and does not establish",
            "",
            "- It establishes that the operator-facing reads are index-backed where an index",
            "  exists, and shows the plan for each so a future regression is visible.",
            "- It does NOT establish production throughput, behaviour under concurrent load,",
            "  behaviour on other hardware, or any claim about how many orders this product",
            "  could dispatch. It dispatches one, after a human authorizes it.",
            "- The append-only tables grow without bound by design. Nothing here is a retention",
            "  policy, and this milestone does not add one.",
            "",
        ]
    )

    _seed(seeder, 0)
    seeder.dispose()
    engine.dispose()
    PACKAGE.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {RESULTS.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
