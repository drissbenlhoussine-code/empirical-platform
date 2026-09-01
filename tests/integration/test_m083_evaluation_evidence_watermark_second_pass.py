"""MILESTONE-083 fresh second verification pass.

Same agent, so NOT an independent review. A genuinely new database created
empty and migrated from scratch, with deliberately different inputs from
`test_m083_evaluation_evidence_watermark_lifecycle.py`: different watermark
and receipt identities, a different capture ordering, concurrent capture, and
a re-verification that an earlier watermark stays byte-identical after later
activity.
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

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.evaluation_evidence_watermark_io import (
    render_evaluation_evidence_watermark_json,
    render_evaluation_evidence_watermark_text,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATABASE = "m083_second_pass"
_T0 = datetime(2027, 9, 1, tzinfo=UTC)


def _config(database: str) -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=database,
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=6,
        max_overflow=6,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m083-second-pass",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="module")
def fresh_database() -> Iterator[str]:
    if os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    admin = sa.create_engine(
        _config(
            os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform")
        ).sqlalchemy_url()
    )
    try:
        with admin.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_DATABASE}"'))
            conn.execute(text(f'CREATE DATABASE "{_DATABASE}"'))
        previous = os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE")
        try:
            os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = _DATABASE
            alembic_command.upgrade(_alembic_config(), "head")
        finally:
            if previous is None:
                os.environ.pop("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", None)
            else:
                os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = previous
        yield _DATABASE
    finally:
        with admin.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_DATABASE}"'))
        admin.dispose()


def _seed_receipt(config: PostgreSQLConfigSnapshot, *, event_gid: str, receipt_gid: str) -> None:
    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO operator_position_event (runtime_id, governance_id, "
                    "position_governance_id, instrument_symbol, event_kind, quantity, "
                    "asserted_price, event_timestamp, recorded_at) VALUES "
                    "(:rt, :gid, :pos, 'MSFT', 'OPENED', 3, 250, :t, :t)"
                ),
                {
                    "rt": f"sp-rt-{event_gid}",
                    "gid": event_gid,
                    "pos": f"SP-POS-{event_gid}",
                    "t": _T0,
                },
            )
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO operator_event_receipt (receipt_governance_id, "
                    "event_governance_id, system_received_at, attested_by, attester_version) "
                    "VALUES (:rid, :gid, now(), 'second-pass', 'test.1')"
                ),
                {"rid": receipt_gid, "gid": event_gid},
            )
    finally:
        engine.dispose()


def _capture(config: PostgreSQLConfigSnapshot, watermark_gid: str) -> EvaluationEvidenceWatermark:
    with postgres_repository_runtime(config) as runtime:
        return runtime.evaluation_evidence_watermarks.capture(watermark_governance_id=watermark_gid)


def _get(
    config: PostgreSQLConfigSnapshot, watermark_gid: str
) -> EvaluationEvidenceWatermark | None:
    with postgres_repository_runtime(config) as runtime:
        return runtime.evaluation_evidence_watermarks.get(watermark_gid)


def test_a_fresh_empty_database_captures_an_explicit_empty_watermark(
    fresh_database: str,
) -> None:
    config = _config(fresh_database)
    watermark = _capture(config, "SP-WM-EMPTY")
    assert watermark.receipt_governance_ids == ()
    assert watermark.captured_receipt_count == 0


def test_reverse_alphabetical_seeding_still_sorts_canonically(fresh_database: str) -> None:
    config = _config(fresh_database)
    for n, rid in enumerate(["SP-RC-YANKEE", "SP-RC-KILO", "SP-RC-BRAVO", "SP-RC-XRAY"]):
        _seed_receipt(config, event_gid=f"SP-EV-{n}", receipt_gid=rid)
    watermark = _capture(config, "SP-WM-ORDER")
    assert watermark.receipt_governance_ids == (
        "SP-RC-BRAVO",
        "SP-RC-KILO",
        "SP-RC-XRAY",
        "SP-RC-YANKEE",
    )


def test_concurrent_capture_of_the_same_identity_yields_one_winner(fresh_database: str) -> None:
    config = _config(fresh_database)
    _seed_receipt(config, event_gid="SP-EV-RACE", receipt_gid="SP-RC-RACE")
    results: list[EvaluationEvidenceWatermark] = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            results.append(_capture(config, "SP-WM-RACE"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len({w.receipt_governance_ids for w in results}) == 1
    # Every later retry observes the same immutable winner.
    assert (
        _capture(config, "SP-WM-RACE").receipt_governance_ids == results[0].receipt_governance_ids
    )


def test_an_earlier_watermark_stays_byte_identical_after_a_later_capture(
    fresh_database: str,
) -> None:
    config = _config(fresh_database)
    _seed_receipt(config, event_gid="SP-EV-FIRST", receipt_gid="SP-RC-FIRST")
    first = _capture(config, "SP-WM-FIRST")
    rendered_before = render_evaluation_evidence_watermark_text(first)
    json_before = render_evaluation_evidence_watermark_json(first)

    _seed_receipt(config, event_gid="SP-EV-SECOND", receipt_gid="SP-RC-SECOND")
    _capture(config, "SP-WM-SECOND")

    reread = _get(config, "SP-WM-FIRST")
    assert reread == first
    assert render_evaluation_evidence_watermark_text(reread) == rendered_before
    assert render_evaluation_evidence_watermark_json(reread) == json_before


def test_update_and_delete_remain_refused_on_a_fresh_database(fresh_database: str) -> None:
    config = _config(fresh_database)
    _capture(config, "SP-WM-IMMUTABLE")
    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with pytest.raises(Exception, match="append-only"):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE evaluation_evidence_watermark SET watermark_governance_id='X' "
                        "WHERE watermark_governance_id='SP-WM-IMMUTABLE'"
                    )
                )
        with pytest.raises(Exception, match="append-only"):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "DELETE FROM evaluation_evidence_watermark "
                        "WHERE watermark_governance_id='SP-WM-IMMUTABLE'"
                    )
                )
    finally:
        engine.dispose()
