"""MILESTONE-082 fresh second verification pass.

Same agent, so NOT an independent review. A genuinely new database created
empty and migrated from scratch, with deliberately different inputs: different
event ids, different instruments, different effective timestamps, deliberately
false `recorded_at` values, concurrent attestation, retry, and a bypassed legacy
event that is never attested.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text

from empirical_platform.decision_candidate.operator_event_receipt import (
    build_attested_evidence_report,
    events_with_receipt_labelled_by,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATABASE = "m082_second_pass"
_T0 = datetime(2027, 6, 1, tzinfo=UTC)


def _config(database: str) -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=database,
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=4,
        max_overflow=4,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m082-second-pass",
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
            # Scoped to the alembic call ONLY: leaving it set across the yield
            # would make later comparisons compare a database with itself.
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


def _append(
    config: PostgreSQLConfigSnapshot,
    *,
    gid: str,
    pos: str,
    symbol: str,
    day: int,
    recorded_day: int,
) -> None:
    with postgres_repository_runtime(config) as runtime:
        runtime.operator_position_ledger.append_validated(
            OperatorAssertedPositionEvent(
                governance_id=gid,
                runtime_id=f"rt-{gid}",
                position_governance_id=pos,
                instrument_symbol=symbol,
                kind=OperatorPositionEventKind.OPENED,
                quantity=2,
                asserted_price=Decimal("77.5"),
                event_timestamp=_T0 + timedelta(days=day),
                recorded_at=_T0 + timedelta(days=recorded_day),
                source_position_plan_governance_id=None,
                note=None,
            )
        )


def _attest(config: PostgreSQLConfigSnapshot, rid: str, gid: str):  # noqa: ANN202
    with postgres_repository_runtime(config) as runtime:
        return runtime.operator_event_receipts.attest(
            receipt_governance_id=rid, event_governance_id=gid, attested_by="second-pass"
        )


def _state(config: PostgreSQLConfigSnapshot, cutoff: datetime):  # noqa: ANN202
    with postgres_repository_runtime(config) as runtime:
        events = runtime.operator_position_ledger.list_all()
        receipts = runtime.operator_event_receipts.list_all()
    return (
        build_attested_evidence_report(
            events=events, receipts=receipts, receipt_label_cutoff=cutoff
        ),
        events,
        receipts,
    )


def test_a_deliberately_false_recorded_at_never_reaches_the_receipt(
    fresh_database: str,
) -> None:
    """PLTR: the operator claims the event was recorded five years early."""
    config = _config(fresh_database)
    _append(config, gid="SP-PLTR", pos="SP-P1", symbol="PLTR", day=10, recorded_day=-1825)
    before = datetime.now(UTC)
    receipt = _attest(config, "SP-RC-PLTR", "SP-PLTR")

    lie = _T0 + timedelta(days=-1825)
    assert receipt.system_received_at >= before
    assert receipt.system_received_at != lie
    assert receipt.system_received_at != _T0 + timedelta(days=10)


def test_a_bypassed_legacy_event_is_never_attested(fresh_database: str) -> None:
    config = _config(fresh_database)
    _append(config, gid="SP-COIN", pos="SP-P2", symbol="COIN", day=11, recorded_day=-900)
    report, _, _ = _state(config, datetime.now(UTC) + timedelta(days=1))
    # Absence, not a placeholder: the bypassed event is not listed at all.
    assert all(e.event_governance_id != "SP-COIN" for e in report.entries)


def test_concurrent_attestation_and_retry_yield_one_authority(fresh_database: str) -> None:
    config = _config(fresh_database)
    _append(config, gid="SP-ARM", pos="SP-P3", symbol="ARM", day=12, recorded_day=12)
    seen: list[object] = []
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            seen.append(_attest(config, f"SP-RC-ARM-{n}", "SP-ARM"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors

    # Every caller, and every later retry, observes the same single receipt.
    instants = {r.system_received_at for r in seen}  # type: ignore[attr-defined]
    assert len(instants) == 1
    assert _attest(config, "SP-RC-ARM-retry", "SP-ARM").system_received_at == instants.pop()

    with postgres_repository_runtime(config) as runtime:
        arm = [
            r
            for r in runtime.operator_event_receipts.list_all()
            if r.event_governance_id == "SP-ARM"
        ]
    assert len(arm) == 1


def test_the_cutoff_boundary_holds_on_a_fresh_database(fresh_database: str) -> None:
    config = _config(fresh_database)
    _append(config, gid="SP-SMCI", pos="SP-P4", symbol="SMCI", day=13, recorded_day=13)
    receipt = _attest(config, "SP-RC-SMCI", "SP-SMCI")

    before = receipt.system_received_at - timedelta(microseconds=1)
    exact = receipt.system_received_at
    _, events, receipts = _state(config, exact)

    ids_before = {
        e.governance_id for e in events_with_receipt_labelled_by(events, receipts, before)
    }
    ids_exact = {e.governance_id for e in events_with_receipt_labelled_by(events, receipts, exact)}
    assert "SP-SMCI" not in ids_before
    assert "SP-SMCI" in ids_exact
