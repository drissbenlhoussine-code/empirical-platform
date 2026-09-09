"""MILESTONE-083 -- extended hostile PostgreSQL attacks against real PostgreSQL.

Owner mission Phase E: additional high-value attacks beyond the 33 already
committed in `test_m083_evaluation_evidence_watermark_lifecycle.py`. This
file adds attacks that were genuinely NOT exercised by the original 33:
multi-row/derived-source INSERT forms, an explicit forged-empty and an
explicit NULL supplied value, the COPY path, a real column-length boundary,
non-default isolation levels (REPEATABLE READ, SERIALIZABLE with a genuine
serialization failure and retry), a named-schema `search_path` attack
distinct from the existing `pg_temp` attack, and a real (not faked)
unrelated-constraint-violation propagation test. Every existing attack and
fixture style in the sibling file is reused unchanged; this file adds to the
campaign, it does not replace or renumber it.
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

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 2, 1, tzinfo=UTC)


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


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
        application_name="empirical-platform-m083-extended-test",
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


def _seed_receipt(engine: Engine, *, event_gid: str, receipt_gid: str) -> None:
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


def _capture(config: PostgreSQLConfigSnapshot, watermark_gid: str) -> EvaluationEvidenceWatermark:
    with postgres_repository_runtime(config) as runtime:
        return runtime.evaluation_evidence_watermarks.capture(watermark_governance_id=watermark_gid)


def _get(
    config: PostgreSQLConfigSnapshot, watermark_gid: str
) -> EvaluationEvidenceWatermark | None:
    with postgres_repository_runtime(config) as runtime:
        return runtime.evaluation_evidence_watermarks.get(watermark_gid)


# --------------------------------------------------------------------------
# E1/E2: multi-row and derived-source INSERT forms.
# --------------------------------------------------------------------------


def test_e1_multi_row_single_statement_insert_each_row_gets_the_full_set(
    clean_tables: Engine,
) -> None:
    """A single INSERT statement naming two watermark rows in one VALUES
    list. The row trigger fires FOR EACH ROW: both rows must independently
    receive the identical, complete, correctly-ordered receipt set."""
    _seed_receipt(clean_tables, event_gid="EV-MULTI1", receipt_gid="RC-MULTI1")
    _seed_receipt(clean_tables, event_gid="EV-MULTI2", receipt_gid="RC-MULTI2")
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                "VALUES ('WM-MULTI-A'), ('WM-MULTI-B')"
            )
        )
    first = _get(_config(), "WM-MULTI-A")
    second = _get(_config(), "WM-MULTI-B")
    assert first is not None and second is not None
    assert first.receipt_governance_ids == ("RC-MULTI1", "RC-MULTI2")
    assert second.receipt_governance_ids == first.receipt_governance_ids


def test_e2_insert_select_derived_source_still_fires_the_capture_trigger(
    clean_tables: Engine,
) -> None:
    """`INSERT ... SELECT` is a different SQL surface from a VALUES list; the
    row trigger must fire identically because it is a FOR EACH ROW trigger,
    not a statement-level default."""
    _seed_receipt(clean_tables, event_gid="EV-SEL", receipt_gid="RC-SEL")
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                "SELECT 'WM-FROM-SELECT'"
            )
        )
    watermark = _get(_config(), "WM-FROM-SELECT")
    assert watermark is not None
    assert watermark.receipt_governance_ids == ("RC-SEL",)


# --------------------------------------------------------------------------
# E3/E4: forged empty array, and an explicit NULL, both overwritten.
# --------------------------------------------------------------------------


def test_e3_caller_supplied_empty_array_is_overwritten_when_receipts_exist(
    clean_tables: Engine,
) -> None:
    """The caller explicitly asserts emptiness while real receipts exist --
    a stronger attack than merely omitting the column (test_12) because it
    supplies a value the trigger must actively discard, not merely default."""
    _seed_receipt(clean_tables, event_gid="EV-FORCE-EMPTY", receipt_gid="RC-FORCE-EMPTY")
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark "
                "(watermark_governance_id, receipt_governance_ids) "
                "VALUES ('WM-FORCED-EMPTY', ARRAY[]::text[])"
            )
        )
    watermark = _get(_config(), "WM-FORCED-EMPTY")
    assert watermark is not None
    assert watermark.receipt_governance_ids == ("RC-FORCE-EMPTY",)


def test_e4_caller_supplied_null_is_overwritten_before_not_null_is_checked(
    clean_tables: Engine,
) -> None:
    """PostgreSQL runs BEFORE ROW triggers before NOT NULL validation, so a
    caller-supplied NULL never reaches the constraint at all -- the trigger
    replaces it first. Proven by executing an INSERT with an explicit NULL
    and observing success (not a NOT NULL violation) with the real set."""
    _seed_receipt(clean_tables, event_gid="EV-NULLED", receipt_gid="RC-NULLED")
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark "
                "(watermark_governance_id, receipt_governance_ids) "
                "VALUES ('WM-NULLED', NULL)"
            )
        )
    watermark = _get(_config(), "WM-NULLED")
    assert watermark is not None
    assert watermark.receipt_governance_ids == ("RC-NULLED",)


# --------------------------------------------------------------------------
# E5: the COPY path fires the same row trigger.
# --------------------------------------------------------------------------


def test_e5_copy_from_stdin_fires_the_same_capture_trigger(clean_tables: Engine) -> None:
    _seed_receipt(clean_tables, event_gid="EV-COPY", receipt_gid="RC-COPY")
    raw = clean_tables.raw_connection()
    try:
        cursor = raw.cursor()
        with cursor.copy(
            "COPY evaluation_evidence_watermark (watermark_governance_id) FROM STDIN"
        ) as copy:
            copy.write_row(("WM-VIA-COPY",))
        raw.commit()
    finally:
        raw.close()
    watermark = _get(_config(), "WM-VIA-COPY")
    assert watermark is not None
    assert watermark.receipt_governance_ids == ("RC-COPY",)


# --------------------------------------------------------------------------
# E6: real column-length boundary at the database, not the Python layer.
# --------------------------------------------------------------------------


def test_e6_exactly_64_characters_succeeds_65_is_rejected_by_the_column_type(
    clean_tables: Engine,
) -> None:
    exactly_64 = "W" * 64
    too_long = "W" * 65
    with clean_tables.begin() as conn:
        conn.execute(
            text("INSERT INTO evaluation_evidence_watermark (watermark_governance_id) VALUES (:v)"),
            {"v": exactly_64},
        )
    watermark = _get(_config(), exactly_64)
    assert watermark is not None

    with pytest.raises(Exception, match="(?i)value too long"):
        with clean_tables.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                    "VALUES (:v)"
                ),
                {"v": too_long},
            )


# --------------------------------------------------------------------------
# E7: REPEATABLE READ -- a transaction's snapshot is fixed at its FIRST
# statement, not retaken per statement as under (default) READ COMMITTED.
# --------------------------------------------------------------------------


def test_e7_repeatable_read_holds_one_snapshot_across_the_whole_transaction(
    clean_tables: Engine, engine: Engine
) -> None:
    """Deterministic handshake: open a REPEATABLE READ transaction, take its
    snapshot with a first statement, then -- from another connection --
    commit a new receipt, THEN capture a watermark inside the still-open
    REPEATABLE READ transaction. Under REPEATABLE READ the new receipt must
    NOT be visible, unlike the default READ COMMITTED behaviour already
    proven in test_18_and_19 (where a later capture DOES see it)."""
    _seed_receipt(clean_tables, event_gid="EV-RR-PRE", receipt_gid="RC-RR-PRE")

    snapshot_taken = threading.Event()
    proceed_to_capture = threading.Event()
    result: dict[str, object] = {}

    def rr_transaction() -> None:
        with engine.connect() as conn:
            tx = conn.begin()
            conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            # First real statement pins the snapshot.
            conn.execute(text("SELECT 1"))
            snapshot_taken.set()
            proceed_to_capture.wait(timeout=10)
            rows = conn.execute(
                text(
                    "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                    "VALUES ('WM-RR') RETURNING receipt_governance_ids"
                )
            ).scalar()
            result["receipt_ids"] = rows
            tx.commit()

    thread = threading.Thread(target=rr_transaction)
    thread.start()
    assert snapshot_taken.wait(timeout=10), "REPEATABLE READ transaction failed to signal"
    _seed_receipt(clean_tables, event_gid="EV-RR-POST", receipt_gid="RC-RR-POST")
    proceed_to_capture.set()
    thread.join(timeout=10)

    assert result["receipt_ids"] == ["RC-RR-PRE"], (
        "REPEATABLE READ must not see a receipt committed after its snapshot"
    )


# --------------------------------------------------------------------------
# E8: SERIALIZABLE -- a genuine serialization failure, executed, not merely
# asserted, plus a successful retry.
# --------------------------------------------------------------------------


def test_e8_serializable_write_skew_raises_and_retry_succeeds(
    clean_tables: Engine, engine: Engine
) -> None:
    """The textbook SSI write-skew shape, executed for real: both
    transactions SELECT count(*) (a shared read predicate over the whole
    table) under SERIALIZABLE, synchronize on a barrier, then each INSERT a
    DIFFERENT watermark row. No row-level lock contention is possible (the
    two INSERTs target different primary keys), so any failure is a genuine
    predicate-based serialization failure (SQLSTATE 40001), not physical
    blocking. PostgreSQL's SSI must abort exactly one side at commit; the
    loser's retry -- a fresh transaction repeating the identical INSERT --
    must then succeed cleanly."""
    ready = threading.Barrier(2, timeout=10)
    outcomes: dict[int, str] = {}
    lock = threading.Lock()

    def attempt(worker_id: int, watermark_id: str) -> None:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                conn.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
                conn.execute(text("SELECT count(*) FROM evaluation_evidence_watermark"))
                ready.wait()
                conn.execute(
                    text(
                        "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                        "VALUES (:v)"
                    ),
                    {"v": watermark_id},
                )
                tx.commit()
                with lock:
                    outcomes[worker_id] = "committed"
            except Exception as exc:  # noqa: BLE001
                tx.rollback()
                sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
                with lock:
                    outcomes[worker_id] = f"failed:{sqlstate}"

    ids = {1: "WM-SSI-A", 2: "WM-SSI-B"}
    threads = [threading.Thread(target=attempt, args=(wid, wm)) for wid, wm in ids.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert set(outcomes.values()) == {"committed", "failed:40001"}, outcomes
    loser = next(wid for wid, outcome in outcomes.items() if outcome.startswith("failed"))

    # Retry: a fresh transaction repeating the identical INSERT must succeed.
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO evaluation_evidence_watermark (watermark_governance_id) VALUES (:v)"),
            {"v": ids[loser]},
        )
    with engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM evaluation_evidence_watermark "
                "WHERE watermark_governance_id IN ('WM-SSI-A', 'WM-SSI-B')"
            )
        ).scalar()
    assert count == 2, "both watermarks must exist after the retry"


# --------------------------------------------------------------------------
# E9: named-schema search_path attack, distinct from the existing pg_temp
# attack (test_13) -- a hostile schema explicitly prepended to search_path.
# --------------------------------------------------------------------------


def test_e9_hostile_named_schema_on_search_path_cannot_alter_the_result(
    clean_tables: Engine, engine: Engine
) -> None:
    _seed_receipt(clean_tables, event_gid="EV-SP-REAL", receipt_gid="RC-SP-REAL")
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS hostile_evil_schema"))
            conn.execute(
                text(
                    "CREATE TABLE hostile_evil_schema.operator_event_receipt "
                    "(receipt_governance_id text, event_governance_id text, "
                    "system_received_at timestamptz, attested_by text, attester_version text)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO hostile_evil_schema.operator_event_receipt "
                    "(receipt_governance_id, event_governance_id) "
                    "VALUES ('RC-FORGED-VIA-SEARCH-PATH', 'EV-FORGED')"
                )
            )
            conn.execute(text("SET search_path = hostile_evil_schema, public"))
            conn.execute(
                text(
                    "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                    "VALUES ('WM-SEARCHPATH-ATTACK')"
                )
            )
    try:
        watermark = _get(_config(), "WM-SEARCHPATH-ATTACK")
        assert watermark is not None
        assert watermark.receipt_governance_ids == ("RC-SP-REAL",)
        assert "RC-FORGED-VIA-SEARCH-PATH" not in watermark.receipt_governance_ids
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA hostile_evil_schema CASCADE"))


# --------------------------------------------------------------------------
# E10: a real (not faked) unrelated-constraint violation must propagate,
# never be misclassified as this repository's own identity conflict.
# --------------------------------------------------------------------------


def test_e10_real_check_violation_is_not_misclassified_as_a_pk_conflict(
    clean_tables: Engine,
) -> None:
    """Calling the repository directly with a blank identity bypasses the
    Python-layer command validation, reaching PostgreSQL's real CHECK
    constraint (SQLSTATE 23514, not 23505 unique violation). The repository
    must propagate this as-is, not read it back as though a legitimate
    conflicting winner existed."""
    from empirical_platform.shared.persistence.postgres_repositories._errors import (
        unique_violation_constraint_name,
    )

    service = PostgresPersistenceService(_config())
    try:
        service.initialize()
        repository = PostgresEvaluationEvidenceWatermarkRepository(service)
        with pytest.raises(FoundationError) as excinfo:
            repository.capture(watermark_governance_id="   ")
        # The safe, redacted message deliberately carries no constraint
        # detail (defence in depth) -- what matters structurally is that
        # this is NOT recognized as the watermark's own unique-violation, so
        # `capture` re-raises it instead of attempting a winner read-back.
        assert unique_violation_constraint_name(excinfo.value) is None
    finally:
        service.close()
    # And no row was left behind by the failed attempt.
    assert _get(_config(), "   ") is None


# --------------------------------------------------------------------------
# E11: AUDIT FINDING M083-AUD-001 -- a corrupted stored set must be REFUSED on
# read, not silently converted into a valid-looking receipt identity.
#
# This is a real-database test on purpose. The unit tests in
# `tests/unit/test_postgres_evaluation_evidence_watermark_repository.py` pin
# the mapping contract with hand-built mappings; this one proves the exposure
# was real end to end: that PostgreSQL genuinely stores a NULL array element
# in this NOT NULL column (the constraint binds the array, not its members),
# that SQLAlchemy/psycopg genuinely hands it back as a Python None, and that
# the repository refuses it instead of reporting the receipt identity 'None'.
#
# The corruption is written through `ALTER TABLE ... DISABLE TRIGGER`, which
# is an explicitly NON-guaranteed path named in `current-authority.json`'s
# `structural_limitations` -- this test asserts how the read side behaves once
# that boundary has already been crossed, and claims no protection against
# crossing it.
# --------------------------------------------------------------------------


def test_e11_a_null_array_element_is_refused_on_read_not_coerced_into_an_identity(
    clean_tables: Engine,
) -> None:
    engine = clean_tables
    _seed_receipt(engine, event_gid="EV-AUD001", receipt_gid="A-real-id")
    captured = _capture(_config(), "WM-AUD001")
    assert captured.receipt_governance_ids == ("A-real-id",)

    # Cross the documented boundary: disable the row trigger and store a NULL
    # element alongside a real one. 'A-real-id' < 'None' under byte ordering,
    # so a stringified NULL would land in canonical ascending position and the
    # domain type's order check would NOT notice it.
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE public.evaluation_evidence_watermark "
                "DISABLE TRIGGER evaluation_evidence_watermark_immutable_trigger"
            )
        )
        conn.execute(
            text(
                "UPDATE public.evaluation_evidence_watermark "
                "SET receipt_governance_ids = ARRAY['A-real-id', NULL]::varchar(64)[] "
                "WHERE watermark_governance_id = 'WM-AUD001'"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE public.evaluation_evidence_watermark "
                "ENABLE TRIGGER evaluation_evidence_watermark_immutable_trigger"
            )
        )

    # The NOT NULL column really does hold a NULL member, and the driver really
    # does return None for it -- neither is assumed.
    with engine.begin() as conn:
        stored = (
            conn.execute(
                text(
                    "SELECT receipt_governance_ids FROM public.evaluation_evidence_watermark "
                    "WHERE watermark_governance_id = 'WM-AUD001'"
                )
            )
            .mappings()
            .one()["receipt_governance_ids"]
        )
    assert stored == ["A-real-id", None]
    assert stored[1] is None

    with pytest.raises(FoundationError) as excinfo:
        _get(_config(), "WM-AUD001")
    error = excinfo.value
    assert error.operation == "evaluation_evidence_watermark.row_mapping"
    assert "receipt_governance_ids[1]" in error.safe_message
    assert "NoneType" in error.safe_message
    # Refused as a type violation, not as an incidental ordering complaint.
    assert "canonical" not in error.safe_message

    # Restore the trigger state this test perturbed, so nothing leaks.
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE public.evaluation_evidence_watermark "
                "DISABLE TRIGGER evaluation_evidence_watermark_immutable_trigger"
            )
        )
        conn.execute(
            text(
                "DELETE FROM public.evaluation_evidence_watermark "
                "WHERE watermark_governance_id = 'WM-AUD001'"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE public.evaluation_evidence_watermark "
                "ENABLE TRIGGER evaluation_evidence_watermark_immutable_trigger"
            )
        )


def test_e12_a_well_formed_row_still_reads_back_unchanged_after_the_strict_mapping(
    clean_tables: Engine,
) -> None:
    """Fail-closed must not mean fail-often: the ordinary capture/read round
    trip through real PostgreSQL is unaffected by the strict mapping."""
    engine = clean_tables
    _seed_receipt(engine, event_gid="EV-AUD002-A", receipt_gid="RC-AUD002-A")
    _seed_receipt(engine, event_gid="EV-AUD002-B", receipt_gid="RC-AUD002-B")
    captured = _capture(_config(), "WM-AUD002")
    read_back = _get(_config(), "WM-AUD002")
    assert read_back is not None
    assert read_back.receipt_governance_ids == ("RC-AUD002-A", "RC-AUD002-B")
    assert read_back == captured
    assert read_back.captured_receipt_count == 2

    # And the empty-set case, which exercises the array branch with zero
    # elements (the loop body never runs -- it must not fail closed there).
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE operator_event_receipt CASCADE"))
    empty = _capture(_config(), "WM-AUD002-EMPTY")
    assert empty.receipt_governance_ids == ()
    assert _get(_config(), "WM-AUD002-EMPTY") == empty


# --------------------------------------------------------------------------
# E13: AUDIT FINDING M083-AUD-004 -- the explicit COLLATE "C" was not pinned
# by anything executable.
#
# Found by the anti-vacuity mutation campaign: deleting `COLLATE "C"` from the
# capture query's ORDER BY was NOT detected by any test. That is not a test
# oversight so much as a property of the environment, and `hostile-review.md`'s
# design finding D03 already predicted it: this cluster's default collation is
# `C.UTF-8`, which agrees with byte order, so with the explicit COLLATE removed
# the trigger sorts by the column's collation and produces the SAME order --
# in THIS database. The guarantee the milestone actually makes is that
# canonical order does not DEPEND on that coincidence.
#
# A behavioural test cannot discriminate here (it would need a database whose
# default collation disagrees with byte order, which is not portable -- CI runs
# on windows-latest). So this pins the property structurally, against the
# function definition PostgreSQL actually installed, and separately proves the
# pin is not cosmetic by showing a real non-C collation in this very cluster
# orders the same identifiers differently.
# --------------------------------------------------------------------------


def test_e13_the_installed_capture_function_pins_collate_c_explicitly(
    clean_tables: Engine,
) -> None:
    engine = clean_tables
    with engine.begin() as conn:
        definition = conn.execute(
            text(
                "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' "
                "AND p.proname = 'evaluation_evidence_watermark_capture_receipt_set'"
            )
        ).scalar_one()

    assert 'COLLATE "C"' in definition, (
        'the installed capture function no longer pins COLLATE "C"; canonical '
        "order would silently fall back to the database's default collation"
    )
    assert "ORDER BY" in definition
    # The COLLATE must qualify the ORDER BY key itself, not appear incidentally.
    order_by_clause = definition.split("ORDER BY", 1)[1]
    assert order_by_clause.lstrip().startswith('r.receipt_governance_id COLLATE "C"')

    # And the pin is meaningful: a real collation available in this cluster
    # orders the same identifiers differently from byte order, so "it happens to
    # match today" is a property of the deployment, not of the query.
    with engine.begin() as conn:
        byte_order = conn.execute(
            text(
                "SELECT string_agg(v, ',' ORDER BY v COLLATE \"C\") "
                "FROM (VALUES ('a-1'),('B-1'),('_z')) t(v)"
            )
        ).scalar_one()
        icu_order = conn.execute(
            text(
                "SELECT string_agg(v, ',' ORDER BY v COLLATE \"und-x-icu\") "
                "FROM (VALUES ('a-1'),('B-1'),('_z')) t(v)"
            )
        ).scalar_one()
    assert byte_order == "B-1,_z,a-1"
    assert icu_order != byte_order, (
        "expected a non-C collation to disagree with byte order, which is the "
        'whole reason the capture query pins COLLATE "C" explicitly'
    )
