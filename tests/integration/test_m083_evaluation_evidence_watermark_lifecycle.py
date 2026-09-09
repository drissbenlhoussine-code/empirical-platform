"""MILESTONE-083 hostile execution against real PostgreSQL.

Mandated attack categories: set correctness (1-8), caller/direct-SQL attacks
(9-15), concurrency and snapshot boundary (16-24), immutability and migration
(25-32). Deterministic pause/barrier coordination via `threading.Event`
handshakes is used wherever ordering matters -- never inferred from sleep
timing alone; a `time.sleep` appears only as a bounded safety margin AFTER an
Event handshake has already established the ordering.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors.foundation import FoundationError
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.evaluation_evidence_watermark_repository import (  # noqa: E501
    PostgresEvaluationEvidenceWatermarkRepository,
)
from empirical_platform.usecases.evaluation_evidence_watermark_io import (
    render_evaluation_evidence_watermark_json,
    render_evaluation_evidence_watermark_text,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 2, 1, tzinfo=UTC)


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _m082_head(cfg: Config) -> str:
    """The revision immediately below the M083 migration -- read from the
    migration graph itself, never hardcoded, so this test cannot drift from
    whatever the actual down_revision is.
    """
    head_revision = ScriptDirectory.from_config(cfg).get_revision("head")
    assert head_revision is not None
    assert head_revision.down_revision is not None
    return str(head_revision.down_revision)


def _config(database: str | None = None) -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=database
        or os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=6,
        max_overflow=6,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m083-test",
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
def clean_tables(upgraded_schema: Engine) -> Engine:
    with upgraded_schema.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE evaluation_evidence_watermark, operator_event_receipt, "
                "operator_position_event"
            )
        )
    return upgraded_schema


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _seed_receipt(engine: Engine, *, event_gid: str, receipt_gid: str) -> None:
    """Directly seed one committed M076 event and its M082 receipt.

    Raw SQL, deliberately bypassing the M082 repository: M083 does not care
    about event semantics, only that a receipt row exists in
    `operator_event_receipt`, and going straight to SQL keeps this file
    decoupled from M082 internals.

    TWO SEPARATE transactions, deliberately: M082's own prior-committed-event
    trigger refuses a receipt whose event was written by the SAME, still-open
    transaction. Combining both INSERTs into one `engine.begin()` block would
    trip that M082 guarantee, not the M083 primitive this file is testing.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO operator_position_event (runtime_id, governance_id, "
                "position_governance_id, instrument_symbol, event_kind, quantity, "
                "asserted_price, event_timestamp, recorded_at) VALUES "
                "(:rt, :gid, :pos, 'AAPL', 'OPENED', 1, 100, :t, :t)"
            ),
            {"rt": f"rt-{event_gid}", "gid": event_gid, "pos": f"POS-{event_gid}", "t": _T0},
        )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO operator_event_receipt (receipt_governance_id, "
                "event_governance_id, system_received_at, attested_by, attester_version) "
                "VALUES (:rid, :gid, now(), 'test', 'test.1')"
            ),
            {"rid": receipt_gid, "gid": event_gid},
        )


def _seed_event_only(engine: Engine, *, event_gid: str) -> None:
    """Commit one M076 event with no receipt, in its own transaction."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO operator_position_event (runtime_id, governance_id, "
                "position_governance_id, instrument_symbol, event_kind, quantity, "
                "asserted_price, event_timestamp, recorded_at) VALUES "
                "(:rt, :gid, :pos, 'AAPL', 'OPENED', 1, 100, :t, :t)"
            ),
            {"rt": f"rt-{event_gid}", "gid": event_gid, "pos": f"POS-{event_gid}", "t": _T0},
        )


def _capture(config: PostgreSQLConfigSnapshot, watermark_gid: str) -> EvaluationEvidenceWatermark:
    with postgres_repository_runtime(config) as runtime:
        return runtime.evaluation_evidence_watermarks.capture(watermark_governance_id=watermark_gid)


def _get(
    config: PostgreSQLConfigSnapshot, watermark_gid: str
) -> EvaluationEvidenceWatermark | None:
    with postgres_repository_runtime(config) as runtime:
        return runtime.evaluation_evidence_watermarks.get(watermark_gid)


def _row_count(engine: Engine, table: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()  # noqa: S608
    assert result is not None
    return int(result)


# --------------------------------------------------------------------------
# 1-8: set correctness
# --------------------------------------------------------------------------


def test_1_empty_receipt_table_produces_an_explicit_empty_set(clean_tables: Engine) -> None:
    watermark = _capture(_config(), "WM-EMPTY")
    assert watermark.receipt_governance_ids == ()
    assert watermark.captured_receipt_count == 0
    with clean_tables.begin() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT receipt_governance_ids, receipt_governance_ids IS NULL AS is_null "
                    "FROM evaluation_evidence_watermark WHERE watermark_governance_id='WM-EMPTY'"
                )
            )
            .mappings()
            .one()
        )
    assert row["is_null"] is False
    assert row["receipt_governance_ids"] == []


def test_2_one_receipt_is_captured_exactly_once(clean_tables: Engine) -> None:
    _seed_receipt(clean_tables, event_gid="EV-1", receipt_gid="RC-1")
    watermark = _capture(_config(), "WM-ONE")
    assert watermark.receipt_governance_ids == ("RC-1",)


def test_3_many_receipts_are_stored_in_canonical_lexical_order(clean_tables: Engine) -> None:
    for n, rid in enumerate(["RC-Z", "RC-M", "RC-A", "RC-Q"]):
        _seed_receipt(clean_tables, event_gid=f"EV-{n}", receipt_gid=rid)
    watermark = _capture(_config(), "WM-ORDER")
    assert watermark.receipt_governance_ids == ("RC-A", "RC-M", "RC-Q", "RC-Z")


def test_4_insertion_order_does_not_affect_the_stored_representation(clean_tables: Engine) -> None:
    for n, rid in enumerate(["RC-3", "RC-1", "RC-2"]):
        _seed_receipt(clean_tables, event_gid=f"EV-FWD{n}", receipt_gid=rid)
    forward = _capture(_config(), "WM-FWD")

    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE evaluation_evidence_watermark, operator_event_receipt, "
                "operator_position_event"
            )
        )
    # The identical id SET, inserted in the exact reverse physical order.
    for n, rid in enumerate(["RC-2", "RC-1", "RC-3"]):
        _seed_receipt(clean_tables, event_gid=f"EV-REV{n}", receipt_gid=rid)
    reverse = _capture(_config(), "WM-REV")

    assert (
        forward.receipt_governance_ids
        == reverse.receipt_governance_ids
        == (
            "RC-1",
            "RC-2",
            "RC-3",
        )
    )


def test_5_later_receipt_insertion_does_not_change_an_existing_watermark(
    clean_tables: Engine,
) -> None:
    _seed_receipt(clean_tables, event_gid="EV-EARLY", receipt_gid="RC-EARLY")
    first = _capture(_config(), "WM-STABLE")
    assert first.receipt_governance_ids == ("RC-EARLY",)

    _seed_receipt(clean_tables, event_gid="EV-LATE", receipt_gid="RC-LATE")
    reread = _get(_config(), "WM-STABLE")
    assert reread == first
    assert reread.receipt_governance_ids == ("RC-EARLY",)


def test_6_backdating_a_later_receipt_label_does_not_change_an_existing_watermark(
    clean_tables: Engine,
) -> None:
    """M083 does not read `system_received_at` at all -- a backdated label
    cannot even be observed by the capture query, let alone change a result.
    """
    _seed_receipt(clean_tables, event_gid="EV-X", receipt_gid="RC-X")
    watermark = _capture(_config(), "WM-BACKDATE")

    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO operator_position_event (runtime_id, governance_id, "
                "position_governance_id, instrument_symbol, event_kind, quantity, "
                "asserted_price, event_timestamp, recorded_at) VALUES "
                "('rt-EV-OLD','EV-OLD','POS-OLD','AAPL','OPENED',1,100,:t,:t)"
            ),
            {"t": _T0},
        )
    # SEPARATE transaction: M082's prior-committed-event trigger refuses a
    # receipt for an event still open in the same transaction, so the event
    # above must commit before this receipt can be attested to it at all.
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO operator_event_receipt (receipt_governance_id, "
                "event_governance_id, system_received_at, attested_by, attester_version) "
                "VALUES ('RC-BACKDATED', 'EV-OLD', '1999-01-01T00:00:00+00', 'test', 'test.1')"
            )
        )
    reread = _get(_config(), "WM-BACKDATE")
    assert reread == watermark
    assert "RC-BACKDATED" not in reread.receipt_governance_ids


def test_7_an_unreceipted_m076_event_never_appears(clean_tables: Engine) -> None:
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO operator_position_event (runtime_id, governance_id, "
                "position_governance_id, instrument_symbol, event_kind, quantity, "
                "asserted_price, event_timestamp, recorded_at) VALUES "
                "('rt-EV-BARE','EV-BARE','POS-BARE','AAPL','OPENED',1,100,:t,:t)"
            ),
            {"t": _T0},
        )
    watermark = _capture(_config(), "WM-BARE")
    assert watermark.receipt_governance_ids == ()
    text_out = render_evaluation_evidence_watermark_text(watermark)
    assert "EV-BARE" not in text_out


def test_8_no_event_payload_or_receipt_metadata_appears(clean_tables: Engine) -> None:
    _seed_receipt(clean_tables, event_gid="EV-PAY", receipt_gid="RC-PAY")
    watermark = _capture(_config(), "WM-PAY")
    text_out = render_evaluation_evidence_watermark_text(watermark)
    json_out = render_evaluation_evidence_watermark_json(watermark)
    for forbidden in ("AAPL", "OPENED", "100", "EV-PAY", "test.1", "attested_by"):
        assert forbidden not in text_out
    assert set(json_out) == {
        "banner",
        "watermark_governance_id",
        "receipt_governance_ids",
        "captured_receipt_count",
    }


# --------------------------------------------------------------------------
# 9-15: caller and direct-SQL attacks
# --------------------------------------------------------------------------


def test_9_caller_supplied_omitted_subset_is_overwritten(clean_tables: Engine) -> None:
    _seed_receipt(clean_tables, event_gid="EV-S1", receipt_gid="RC-S1")
    _seed_receipt(clean_tables, event_gid="EV-S2", receipt_gid="RC-S2")
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark "
                "(watermark_governance_id, receipt_governance_ids) "
                "VALUES ('WM-SUBSET', ARRAY['RC-S1'])"
            )
        )
    watermark = _get(_config(), "WM-SUBSET")
    assert watermark is not None
    assert watermark.receipt_governance_ids == ("RC-S1", "RC-S2")


def test_10_caller_supplied_extra_nonexistent_id_is_overwritten(clean_tables: Engine) -> None:
    _seed_receipt(clean_tables, event_gid="EV-E1", receipt_gid="RC-E1")
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark "
                "(watermark_governance_id, receipt_governance_ids) "
                "VALUES ('WM-EXTRA', ARRAY['RC-E1','RC-DOES-NOT-EXIST'])"
            )
        )
    watermark = _get(_config(), "WM-EXTRA")
    assert watermark is not None
    assert watermark.receipt_governance_ids == ("RC-E1",)


def test_11_caller_supplied_duplicates_and_reordering_is_overwritten(clean_tables: Engine) -> None:
    _seed_receipt(clean_tables, event_gid="EV-D1", receipt_gid="RC-D1")
    _seed_receipt(clean_tables, event_gid="EV-D2", receipt_gid="RC-D2")
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark "
                "(watermark_governance_id, receipt_governance_ids) "
                "VALUES ('WM-DUP', ARRAY['RC-D2','RC-D2','RC-D1','RC-D2'])"
            )
        )
    watermark = _get(_config(), "WM-DUP")
    assert watermark is not None
    assert watermark.receipt_governance_ids == ("RC-D1", "RC-D2")


def test_12_direct_sql_without_membership_produces_the_exact_database_set(
    clean_tables: Engine,
) -> None:
    _seed_receipt(clean_tables, event_gid="EV-N1", receipt_gid="RC-N1")
    _seed_receipt(clean_tables, event_gid="EV-N2", receipt_gid="RC-N2")
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                "VALUES ('WM-NOCOL')"
            )
        )
    watermark = _get(_config(), "WM-NOCOL")
    assert watermark is not None
    assert watermark.receipt_governance_ids == ("RC-N1", "RC-N2")


def test_13_pg_temp_relation_shadowing_cannot_alter_the_result(
    clean_tables: Engine, engine: Engine
) -> None:
    _seed_receipt(clean_tables, event_gid="EV-REAL", receipt_gid="RC-REAL")
    with engine.connect() as conn:
        try:
            with conn.begin():
                conn.execute(
                    text(
                        "CREATE TEMP TABLE operator_event_receipt "
                        "(receipt_governance_id text, event_governance_id text, "
                        "system_received_at timestamptz, attested_by text, attester_version text)"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO operator_event_receipt VALUES "
                        "('RC-DECOY', 'EV-DECOY', now(), 'attacker', 'fake')"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                        "VALUES ('WM-SHADOW')"
                    )
                )
                result = conn.execute(
                    text(
                        "SELECT receipt_governance_ids FROM evaluation_evidence_watermark "
                        "WHERE watermark_governance_id='WM-SHADOW'"
                    )
                ).scalar()
        finally:
            # A session-scoped TEMP TABLE outlives this transaction and would
            # otherwise leak into the connection pool, silently shadowing
            # `operator_event_receipt` for whichever later test happens to
            # reuse this exact pooled DBAPI connection. Invalidating it forces
            # the pool to discard the physical connection instead of reusing
            # a tainted one -- proven necessary: without this, later tests in
            # this module intermittently failed depending on pool reuse.
            conn.invalidate()
    assert result == ["RC-REAL"]
    assert "RC-DECOY" not in result


@pytest.mark.parametrize("blank_id", ["", "   ", "\t"])
def test_14_blank_watermark_ids_are_refused_by_python_and_postgresql(
    clean_tables: Engine, blank_id: str
) -> None:
    from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
        EvaluationEvidenceWatermark,
    )

    with pytest.raises(ValueError):
        EvaluationEvidenceWatermark(watermark_governance_id=blank_id, receipt_governance_ids=())

    with pytest.raises(Exception, match="ck_evaluation_evidence_watermark_id_present|check"):
        with clean_tables.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                    "VALUES (:v)"
                ),
                {"v": blank_id},
            )


def test_15_an_unexpected_database_failure_propagates_with_no_empty_set_fallback(
    clean_tables: Engine,
) -> None:
    unreachable = PostgreSQLConfigSnapshot(
        host="127.0.0.1",
        port=1,  # nothing listens here
        database="empirical_platform",
        user="empirical",
        password=SecretStr("wrong"),
        pool_size=1,
        max_overflow=0,
        connection_timeout_seconds=1,
        application_name="empirical-platform-m083-failure-test",
    )
    service = PostgresPersistenceService(unreachable)
    try:
        with pytest.raises(FoundationError):
            # `initialize()` itself probes connectivity and fails here for an
            # unreachable host; either way, the failure PROPAGATES as a
            # FoundationError rather than being swallowed into an empty read.
            service.initialize()
            repository = PostgresEvaluationEvidenceWatermarkRepository(service)
            repository.get("WM-ANYTHING")
    finally:
        service.close()


# --------------------------------------------------------------------------
# 16-24: concurrency and snapshot boundary
# --------------------------------------------------------------------------


def test_16_a_receipt_committed_before_capture_is_included(clean_tables: Engine) -> None:
    _seed_receipt(clean_tables, event_gid="EV-BEFORE", receipt_gid="RC-BEFORE")
    watermark = _capture(_config(), "WM-BEFORE")
    assert "RC-BEFORE" in watermark.receipt_governance_ids


def test_17_a_receipt_uncommitted_in_another_transaction_is_excluded(
    clean_tables: Engine, engine: Engine
) -> None:
    """Deterministic handshake, not sleep-inferred: the writer signals AFTER
    its INSERT has executed but BEFORE it commits; the capture only starts
    once that signal is observed, and the writer only commits after the
    capture confirms it has read.
    """
    inserted = threading.Event()
    proceed_to_commit = threading.Event()
    captured: dict[str, object] = {}

    def slow_writer() -> None:
        # The event must be COMMITTED first: M082's own prior-committed-event
        # trigger refuses a receipt for an event still open in the writer's
        # own transaction, which would test that guarantee, not this one.
        _seed_event_only(engine, event_gid="EV-SLOW")
        with engine.connect() as conn:
            tx = conn.begin()
            conn.execute(
                text(
                    "INSERT INTO operator_event_receipt (receipt_governance_id, "
                    "event_governance_id, system_received_at, attested_by, attester_version) "
                    "VALUES ('RC-SLOW', 'EV-SLOW', now(), 'test', 'test.1')"
                )
            )
            inserted.set()
            proceed_to_commit.wait(timeout=10)
            tx.commit()

    thread = threading.Thread(target=slow_writer)
    thread.start()
    assert inserted.wait(timeout=10), "writer failed to signal after its INSERT"
    captured["watermark"] = _capture(_config(), "WM-UNCOMMITTED")
    proceed_to_commit.set()
    thread.join(timeout=10)

    watermark = captured["watermark"]
    assert "RC-SLOW" not in watermark.receipt_governance_ids  # type: ignore[attr-defined]


def test_18_and_19_a_receipt_committed_after_the_snapshot_is_excluded_and_a_later_watermark_may_include_it(  # noqa: E501
    clean_tables: Engine,
) -> None:
    _seed_receipt(clean_tables, event_gid="EV-PRE", receipt_gid="RC-A-PRE")
    early = _capture(_config(), "WM-EARLY")
    assert early.receipt_governance_ids == ("RC-A-PRE",)

    _seed_receipt(clean_tables, event_gid="EV-POST", receipt_gid="RC-Z-POST")
    late = _capture(_config(), "WM-LATE")
    assert late.receipt_governance_ids == ("RC-A-PRE", "RC-Z-POST")

    # Capturing WM-LATE must not have mutated WM-EARLY.
    reread_early = _get(_config(), "WM-EARLY")
    assert reread_early == early


def test_20_same_transaction_receipt_visibility_is_statement_snapshot_not_prior_commit(
    clean_tables: Engine, engine: Engine
) -> None:
    """MEASURED, PRECISELY: a receipt inserted earlier in the SAME transaction
    as the watermark capture IS visible to the capture statement, even though
    it has not committed. This is ordinary PostgreSQL own-transaction-write
    visibility, not a "prior committed" guarantee -- M083 makes no such claim.
    """
    # The event is committed FIRST, in its own transaction: M082's own
    # prior-committed-event trigger refuses a receipt for an event still open
    # in the writer's own transaction, which is a DIFFERENT guarantee than
    # the one under test here (receipt-to-watermark same-transaction
    # visibility, not event-to-receipt same-transaction visibility).
    _seed_event_only(engine, event_gid="EV-SAMETX")
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO operator_event_receipt (receipt_governance_id, "
                    "event_governance_id, system_received_at, attested_by, attester_version) "
                    "VALUES ('RC-SAMETX', 'EV-SAMETX', now(), 'test', 'test.1')"
                )
            )
            # SAME transaction, SAME connection, later statement.
            conn.execute(
                text(
                    "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                    "VALUES ('WM-SAMETX')"
                )
            )
            visible_within_tx = conn.execute(
                text(
                    "SELECT receipt_governance_ids FROM evaluation_evidence_watermark "
                    "WHERE watermark_governance_id='WM-SAMETX'"
                )
            ).scalar()
    assert visible_within_tx == ["RC-SAMETX"]
    persisted = _get(_config(), "WM-SAMETX")
    assert persisted is not None
    assert persisted.receipt_governance_ids == ("RC-SAMETX",)


def test_21_two_concurrent_captures_with_different_ids_are_each_internally_coherent(
    clean_tables: Engine,
) -> None:
    _seed_receipt(clean_tables, event_gid="EV-CO1", receipt_gid="RC-CO1")
    _seed_receipt(clean_tables, event_gid="EV-CO2", receipt_gid="RC-CO2")
    results: dict[str, EvaluationEvidenceWatermark] = {}
    errors: list[Exception] = []

    def worker(name: str) -> None:
        try:
            results[name] = _capture(_config(), name)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("WM-CO-A", "WM-CO-B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert results["WM-CO-A"].receipt_governance_ids == ("RC-CO1", "RC-CO2")
    assert results["WM-CO-B"].receipt_governance_ids == ("RC-CO1", "RC-CO2")


def test_22_two_concurrent_captures_with_the_same_id_yield_one_immutable_winner(
    clean_tables: Engine,
) -> None:
    _seed_receipt(clean_tables, event_gid="EV-RACE", receipt_gid="RC-RACE")
    results: list[EvaluationEvidenceWatermark] = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            results.append(_capture(_config(), "WM-RACE"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len({(w.watermark_governance_id, w.receipt_governance_ids) for w in results}) == 1
    assert _row_count(clean_tables, "evaluation_evidence_watermark") == 1


def test_23_rollback_leaves_no_header_or_partial_set(clean_tables: Engine, engine: Engine) -> None:
    with engine.connect() as conn:
        tx = conn.begin()
        conn.execute(
            text("INSERT INTO evaluation_evidence_watermark (watermark_governance_id) VALUES (:v)"),
            {"v": "WM-ROLLED-BACK"},
        )
        tx.rollback()
    assert _get(_config(), "WM-ROLLED-BACK") is None
    with clean_tables.begin() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM evaluation_evidence_watermark "
                "WHERE watermark_governance_id='WM-ROLLED-BACK'"
            )
        ).scalar()
    assert count == 0


def test_24_the_count_can_never_split_from_membership(clean_tables: Engine) -> None:
    """There is no separate stored count column: `captured_receipt_count` is
    always `len(receipt_governance_ids)`, computed in Python from the exact
    same tuple that is rendered -- structurally impossible to desynchronise.
    """
    for n, rid in enumerate(["RC-CNT1", "RC-CNT2", "RC-CNT3"]):
        _seed_receipt(clean_tables, event_gid=f"EV-CNT{n}", receipt_gid=rid)
    watermark = _capture(_config(), "WM-COUNT")
    assert watermark.captured_receipt_count == len(watermark.receipt_governance_ids) == 3
    with clean_tables.begin() as conn:
        columns = (
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='evaluation_evidence_watermark'"
                )
            )
            .scalars()
            .all()
        )
    assert set(columns) == {"watermark_governance_id", "receipt_governance_ids"}


# --------------------------------------------------------------------------
# 25-32: immutability and migration
# --------------------------------------------------------------------------


def test_25_update_is_refused(clean_tables: Engine) -> None:
    _capture(_config(), "WM-NOUPD")
    with pytest.raises(Exception, match="append-only"):
        with clean_tables.begin() as conn:
            conn.execute(
                text(
                    "UPDATE evaluation_evidence_watermark SET watermark_governance_id='X' "
                    "WHERE watermark_governance_id='WM-NOUPD'"
                )
            )


def test_26_delete_is_refused(clean_tables: Engine) -> None:
    _capture(_config(), "WM-NODEL")
    with pytest.raises(Exception, match="append-only"):
        with clean_tables.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM evaluation_evidence_watermark "
                    "WHERE watermark_governance_id='WM-NODEL'"
                )
            )


def test_27_identity_collision_is_handled_honestly_not_silently_refreshed(
    clean_tables: Engine,
) -> None:
    """Capturing the SAME identity twice, with receipts added in between,
    returns the ORIGINAL frozen set both times -- a retry can never smuggle a
    later receipt into an already-persisted watermark.
    """
    _seed_receipt(clean_tables, event_gid="EV-COL1", receipt_gid="RC-COL1")
    first = _capture(_config(), "WM-COLLIDE")
    _seed_receipt(clean_tables, event_gid="EV-COL2", receipt_gid="RC-COL2")
    second = _capture(_config(), "WM-COLLIDE")
    assert first == second
    assert second.receipt_governance_ids == ("RC-COL1",)


def test_28_migration_up_down_up_is_clean(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = _alembic_config()
    alembic_command.upgrade(cfg, "head")
    with engine.begin() as conn:
        assert conn.execute(
            text("SELECT to_regclass('public.evaluation_evidence_watermark') IS NOT NULL")
        ).scalar()
    alembic_command.downgrade(cfg, _m082_head(cfg))
    with engine.begin() as conn:
        assert not conn.execute(
            text("SELECT to_regclass('public.evaluation_evidence_watermark') IS NOT NULL")
        ).scalar()
    alembic_command.upgrade(cfg, "head")
    with engine.begin() as conn:
        assert conn.execute(
            text("SELECT to_regclass('public.evaluation_evidence_watermark') IS NOT NULL")
        ).scalar()
    # restore a clean upgraded schema for subsequent tests in this module
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(cfg, "head")


def test_29_m082_survives_m083_downgrade_unchanged(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = _alembic_config()
    alembic_command.upgrade(cfg, "head")

    _seed_receipt(engine, event_gid="EV-PRESERVE", receipt_gid="RC-PRESERVE")
    with engine.begin() as conn:
        before_receipt_count = conn.execute(
            text("SELECT count(*) FROM operator_event_receipt")
        ).scalar()
        before_event_count = conn.execute(
            text("SELECT count(*) FROM operator_position_event")
        ).scalar()

    alembic_command.downgrade(cfg, _m082_head(cfg))

    with engine.begin() as conn:
        after_receipt_count = conn.execute(
            text("SELECT count(*) FROM operator_event_receipt")
        ).scalar()
        after_event_count = conn.execute(
            text("SELECT count(*) FROM operator_position_event")
        ).scalar()
        # M082's own immutability trigger must still be installed and working.
        with pytest.raises(Exception, match="append-only"):
            conn.execute(
                text("DELETE FROM operator_event_receipt WHERE receipt_governance_id='RC-PRESERVE'")
            )
    assert (before_receipt_count, before_event_count) == (after_receipt_count, after_event_count)
    assert after_receipt_count == 1

    alembic_command.upgrade(cfg, "head")
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(cfg, "head")


def test_31_a_watermark_read_is_byte_identical_after_unrelated_future_inserts(
    clean_tables: Engine,
) -> None:
    _seed_receipt(clean_tables, event_gid="EV-FIX", receipt_gid="RC-FIX")
    watermark = _capture(_config(), "WM-FIXED")
    rendered_before = (
        render_evaluation_evidence_watermark_text(watermark),
        render_evaluation_evidence_watermark_json(watermark),
    )

    for n in range(3):
        _seed_receipt(clean_tables, event_gid=f"EV-FUTURE-{n}", receipt_gid=f"RC-FUTURE-{n}")
    _capture(_config(), "WM-UNRELATED")

    reread = _get(_config(), "WM-FIXED")
    assert reread is not None
    rendered_after = (
        render_evaluation_evidence_watermark_text(reread),
        render_evaluation_evidence_watermark_json(reread),
    )
    assert rendered_before == rendered_after


def test_32_truncate_drop_and_trigger_disable_are_outside_the_enforcement_boundary(
    clean_tables: Engine, engine: Engine
) -> None:
    """EXECUTED, not merely claimed, and rolled back afterward: DDL is
    transactional in PostgreSQL, so disabling the trigger and inserting a
    forged row is fully undone by ROLLBACK, leaving `clean_tables` unaffected
    for later tests.
    """
    _seed_receipt(clean_tables, event_gid="EV-TRIG", receipt_gid="RC-TRIG")
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(
                text(
                    "ALTER TABLE evaluation_evidence_watermark "
                    "DISABLE TRIGGER evaluation_evidence_watermark_capture_receipt_set_trigger"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO evaluation_evidence_watermark "
                    "(watermark_governance_id, receipt_governance_ids) "
                    "VALUES ('WM-FORGED', ARRAY['RC-FORGED-NEVER-EXISTED'])"
                )
            )
            forged = conn.execute(
                text(
                    "SELECT receipt_governance_ids FROM evaluation_evidence_watermark "
                    "WHERE watermark_governance_id='WM-FORGED'"
                )
            ).scalar()
            assert forged == ["RC-FORGED-NEVER-EXISTED"], (
                "a superuser disabling the trigger CAN forge a set -- this is the "
                "documented, executed boundary of what the trigger enforces"
            )
        finally:
            tx.rollback()
    # After rollback, neither the disable nor the forged row persisted.
    assert _get(_config(), "WM-FORGED") is None
    with clean_tables.begin() as conn:
        still_enabled = conn.execute(
            text(
                "SELECT tgenabled FROM pg_trigger WHERE tgname="
                "'evaluation_evidence_watermark_capture_receipt_set_trigger'"
            )
        ).scalar()
    assert still_enabled == "O"  # 'O' = origin, i.e. enabled


# --------------------------------------------------------------------------
# blank-set agreement: migration literal vs. domain constant vs. live database
# --------------------------------------------------------------------------


def test_the_migration_literal_the_domain_constant_and_the_database_all_agree(
    engine: Engine,
) -> None:
    """The M083 migration freezes its own copy of the 29-character blank set
    rather than importing `BLANK_CHARACTERS` (a migration is history and must
    not depend on mutable application code). Parity is asserted against the
    INSTALLED constraint definition read back from `pg_constraint`, not
    against an expression this test invents, so a divergence in any of the
    three places -- migration literal, domain constant, or what PostgreSQL
    actually parsed the E'' escapes into -- would fail this test.
    """
    from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
        BLANK_CHARACTERS,
    )

    complete = {chr(c) for c in range(0x110000) if chr(c) and not chr(c).strip()}
    assert set(BLANK_CHARACTERS) == complete
    assert len(BLANK_CHARACTERS) == 29

    with engine.begin() as conn:
        definition = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_evaluation_evidence_watermark_id_present'"
            )
        ).scalar_one()
        literal = definition.split("btrim(", 1)[1]
        literal = literal[literal.index(",") + 1 : literal.rindex(") <>")].strip()
        resolved = conn.execute(text(f"SELECT {literal}")).scalar_one()  # noqa: S608
    assert set(resolved) == set(BLANK_CHARACTERS)
    assert len(resolved) == 29
