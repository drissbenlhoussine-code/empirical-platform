"""MILESTONE-082 receipt attestation against real PostgreSQL.

Mandated scenarios A-M, plus the commit-gap attack, the two-connection ordering
attack, the legacy-backfill prohibition, direct M076 bypass, immutability and
the double-database proof.
"""

from __future__ import annotations

import json
import os
import threading
import time
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
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.operator_event_receipt import (
    AttestedEvidenceStatus,
    attested_known_by,
    build_attested_evidence_report,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.postgres_repositories.operator_event_receipt_repository import (  # noqa: E501
    UnknownOperatorEventError,
)
from empirical_platform.usecases.attested_evidence_io import (
    render_attested_evidence_report_json,
    render_attested_evidence_report_text,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 2, 1, tzinfo=UTC)
OPENED = OperatorPositionEventKind.OPENED


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
        pool_size=4,
        max_overflow=4,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m082-test",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not _postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    eng = sa.create_engine(_config().sqlalchemy_url(), pool_size=6, max_overflow=6)
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
    # TRUNCATE, not DELETE: the immutability trigger refuses DELETE on receipts,
    # which is exactly the guarantee under test. A row trigger does not
    # intercept the statement-level TRUNCATE.
    with upgraded_schema.begin() as conn:
        conn.execute(text("TRUNCATE operator_event_receipt, operator_position_event"))
    return upgraded_schema


def _append(
    config: PostgreSQLConfigSnapshot,
    *,
    gid: str,
    pos: str,
    symbol: str = "AAPL",
    day: int = 1,
    recorded_day: int | None = None,
) -> None:
    with postgres_repository_runtime(config) as runtime:
        runtime.operator_position_ledger.append_validated(
            OperatorAssertedPositionEvent(
                governance_id=gid,
                runtime_id=f"rt-{gid}",
                position_governance_id=pos,
                instrument_symbol=symbol,
                kind=OPENED,
                quantity=1,
                asserted_price=Decimal("100"),
                event_timestamp=_T0 + timedelta(days=day),
                recorded_at=_T0 + timedelta(days=recorded_day if recorded_day is not None else day),
                source_position_plan_governance_id=None,
                note=None,
            )
        )


def _attest(config: PostgreSQLConfigSnapshot, rid: str, gid: str, by: str = "test"):  # noqa: ANN202
    with postgres_repository_runtime(config) as runtime:
        return runtime.operator_event_receipts.attest(
            receipt_governance_id=rid, event_governance_id=gid, attested_by=by
        )


def _events(config: PostgreSQLConfigSnapshot):  # noqa: ANN202
    with postgres_repository_runtime(config) as runtime:
        return runtime.operator_position_ledger.list_all()


def _receipts(config: PostgreSQLConfigSnapshot):  # noqa: ANN202
    with postgres_repository_runtime(config) as runtime:
        return runtime.operator_event_receipts.list_all()


def _report(config: PostgreSQLConfigSnapshot, cutoff: datetime):  # noqa: ANN202
    return build_attested_evidence_report(
        events=_events(config), receipts=_receipts(config), attested_as_of=cutoff
    )


# --------------------------------------------------------------------------
# A - D: the normal attested path, and the caller's lies about recorded_at
# --------------------------------------------------------------------------


def test_scenario_a_normal_attested_event(clean_tables: Engine) -> None:
    config = _config()
    _append(config, gid="EV-A", pos="POS-A")
    before = datetime.now(UTC)
    receipt = _attest(config, "RC-A", "EV-A")
    after = datetime.now(UTC)
    assert before <= receipt.system_received_at <= after
    assert receipt.attester_version == "M082.1"

    entry = _report(config, after).entries[0]
    assert entry.status is AttestedEvidenceStatus.ATTESTED


@pytest.mark.parametrize(
    ("label", "recorded_day"),
    [("scenario_b_fake_past", -3650), ("scenario_c_future", 3650)],
)
def test_a_lying_recorded_at_cannot_influence_the_receipt(
    clean_tables: Engine, label: str, recorded_day: int
) -> None:
    """Scenarios B and C, and scenario D: the receipt stays system-controlled."""
    config = _config()
    _append(config, gid=f"EV-{label}", pos=f"POS-{label}", recorded_day=recorded_day)
    before = datetime.now(UTC)
    receipt = _attest(config, f"RC-{label}", f"EV-{label}")

    lie = _T0 + timedelta(days=recorded_day)
    assert receipt.system_received_at != lie
    assert receipt.system_received_at >= before
    # The receipt reflects system authority, not the operator's claim.
    assert abs((receipt.system_received_at - datetime.now(UTC)).total_seconds()) < 60


def test_scenario_e_legacy_event_with_no_receipt(clean_tables: Engine) -> None:
    config = _config()
    _append(config, gid="EV-LEG", pos="POS-LEG", recorded_day=-3650)
    entry = _report(config, datetime.now(UTC) + timedelta(days=1)).entries[0]
    assert entry.status is AttestedEvidenceStatus.NO_SYSTEM_RECEIPT_EVIDENCE
    assert entry.system_received_at is None


def test_scenario_f_duplicate_receipt_is_idempotent(clean_tables: Engine) -> None:
    config = _config()
    _append(config, gid="EV-DUP", pos="POS-DUP")
    first = _attest(config, "RC-DUP-1", "EV-DUP")
    second = _attest(config, "RC-DUP-2", "EV-DUP")
    assert second == first
    assert len(_receipts(config)) == 1


def test_scenario_g_retry_after_success_creates_no_second_authority(
    clean_tables: Engine,
) -> None:
    config = _config()
    _append(config, gid="EV-RETRY", pos="POS-RETRY")
    first = _attest(config, "RC-RETRY", "EV-RETRY")
    for _ in range(3):
        assert (
            _attest(config, "RC-RETRY", "EV-RETRY").system_received_at == first.system_received_at
        )
    assert len(_receipts(config)) == 1


def test_scenario_h_attesting_an_uncommitted_or_missing_event_is_refused(
    clean_tables: Engine,
) -> None:
    with pytest.raises(UnknownOperatorEventError):
        _attest(_config(), "RC-GHOST", "EV-DOES-NOT-EXIST")
    assert _receipts(_config()) == ()


def test_scenario_i_concurrent_attesters_yield_exactly_one_receipt(
    clean_tables: Engine,
) -> None:
    config = _config()
    _append(config, gid="EV-CONC", pos="POS-CONC")
    results: list[object] = []
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            results.append(_attest(config, f"RC-CONC-{n}", "EV-CONC"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len(_receipts(config)) == 1
    instants = {r.system_received_at for r in results}  # type: ignore[attr-defined]
    assert len(instants) == 1, "all callers must observe the single surviving receipt"


def test_scenario_j_direct_m076_bypass_produces_an_unattested_event(
    clean_tables: Engine,
) -> None:
    """The old writer still exists, so M082 must not claim universal coverage."""
    config = _config()
    _append(config, gid="EV-BYPASS", pos="POS-BYPASS")  # no attestation at all
    report = _report(config, datetime.now(UTC) + timedelta(days=1))
    assert report.unattested_count == 1
    assert report.attested_count == 0
    assert any(
        "does NOT claim that all events carry receipt authority" in lim
        for lim in report.limitations
    )


@pytest.mark.parametrize("offset_seconds", [-1, 0, 1])
def test_scenarios_k_l_m_cutoff_before_at_and_after_the_receipt(
    clean_tables: Engine, offset_seconds: int
) -> None:
    config = _config()
    _append(config, gid="EV-CUT", pos="POS-CUT")
    receipt = _attest(config, "RC-CUT", "EV-CUT")
    cutoff = receipt.system_received_at + timedelta(seconds=offset_seconds)
    known = attested_known_by(_events(config), _receipts(config), cutoff)
    assert (len(known) == 1) is (offset_seconds >= 0)


# --------------------------------------------------------------------------
# The mandatory attacks
# --------------------------------------------------------------------------


def test_the_commit_gap_cannot_make_an_uncommitted_event_appear_available(
    clean_tables: Engine, engine: Engine
) -> None:
    """MANDATORY section 24.

    A transaction inserts an event and PAUSES before committing. K is chosen
    during the pause, when the row is invisible to every reader. After commit
    the event is attested. The receipt instant must fall AFTER K, so the
    historical query at K excludes it.
    """
    config = _config()
    box: dict[str, object] = {}

    def slow_writer() -> None:
        with engine.connect() as conn:
            tx = conn.begin()
            conn.execute(
                text(
                    "INSERT INTO operator_position_event (runtime_id, governance_id, "
                    "position_governance_id, instrument_symbol, event_kind, quantity, "
                    "asserted_price, event_timestamp, recorded_at) VALUES "
                    "('rt-SLOW','EV-SLOW','POS-SLOW','AAPL','OPENED',1,100,:t,:t)"
                ),
                {"t": _T0},
            )
            time.sleep(2.5)
            tx.commit()
            box["commit_at"] = datetime.now(UTC)
        box["receipt"] = _attest(config, "RC-SLOW", "EV-SLOW")

    thread = threading.Thread(target=slow_writer)
    thread.start()
    time.sleep(1.2)
    cutoff = datetime.now(UTC)
    with engine.begin() as conn:
        visible = conn.execute(
            text("SELECT count(*) FROM operator_position_event WHERE governance_id='EV-SLOW'")
        ).scalar()
    thread.join()

    receipt = box["receipt"]
    assert visible == 0, "the row must genuinely be invisible at the cutoff"
    assert receipt.system_received_at > box["commit_at"]  # type: ignore[attr-defined,operator]
    assert receipt.system_received_at > cutoff  # type: ignore[attr-defined,operator]
    assert attested_known_by(_events(config), _receipts(config), cutoff) == ()


def test_concurrent_attestation_order_is_attestation_order_not_event_order(
    clean_tables: Engine,
) -> None:
    """MANDATORY section 25. M082 claims no commit-order authority."""
    config = _config()
    _append(config, gid="EV-ORD-A", pos="POS-ORD-A")
    _append(config, gid="EV-ORD-B", pos="POS-ORD-B")
    out: dict[str, object] = {}

    def attest_a() -> None:
        time.sleep(1.0)
        out["A"] = _attest(config, "RC-ORD-A", "EV-ORD-A")

    def attest_b() -> None:
        out["B"] = _attest(config, "RC-ORD-B", "EV-ORD-B")

    ta, tb = threading.Thread(target=attest_a), threading.Thread(target=attest_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()

    # B was appended second but attested first, so receipt order follows
    # attestation, never the order the events were created in.
    assert out["B"].system_received_at < out["A"].system_received_at  # type: ignore[attr-defined,operator]
    ordered = [r.event_governance_id for r in _receipts(config)]
    assert ordered == ["EV-ORD-B", "EV-ORD-A"]


def test_no_receipt_instant_is_ever_manufactured_from_a_frozen_field(
    clean_tables: Engine,
) -> None:
    """MANDATORY section 26: legacy backfill prohibition."""
    config = _config()
    lie_day = -3650
    _append(config, gid="EV-NOBACK", pos="POS-NOBACK", day=1, recorded_day=lie_day)
    report = _report(config, datetime.now(UTC) + timedelta(days=1))
    entry = report.entries[0]
    assert entry.status is AttestedEvidenceStatus.NO_SYSTEM_RECEIPT_EVIDENCE
    assert entry.system_received_at is None
    forbidden = {_T0 + timedelta(days=lie_day), _T0 + timedelta(days=1)}
    assert all(e.system_received_at not in forbidden for e in report.entries)
    # And the migration itself created the table empty.
    assert _receipts(config) == ()


# --------------------------------------------------------------------------
# Immutability, enforced by the database and not merely by the API
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE operator_event_receipt SET system_received_at = now()",
        "DELETE FROM operator_event_receipt",
    ],
)
def test_direct_sql_cannot_mutate_a_receipt(
    clean_tables: Engine, engine: Engine, statement: str
) -> None:
    config = _config()
    _append(config, gid="EV-IMM", pos="POS-IMM")
    _attest(config, "RC-IMM", "EV-IMM")
    with pytest.raises(sa.exc.ProgrammingError, match="append-only"):
        with engine.begin() as conn:
            conn.execute(text(statement))


def test_the_repository_exposes_no_update_or_delete_path() -> None:
    from empirical_platform.shared.persistence.postgres_repositories import (
        operator_event_receipt_repository as module,
    )

    source = Path(module.__file__ or "").read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]
    assert "UPDATE " not in body.upper().replace("BEFORE UPDATE", "")
    assert "DELETE " not in body.upper()


def test_a_receipt_for_a_missing_event_is_refused_by_the_foreign_key(
    clean_tables: Engine, engine: Engine
) -> None:
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO operator_event_receipt (receipt_governance_id, "
                    "event_governance_id, system_received_at, attested_by, attester_version) "
                    "VALUES ('R','NOPE', now(), 'x','M082.1')"
                )
            )


def test_deleting_an_attested_event_is_restricted_not_cascaded(
    clean_tables: Engine, engine: Engine
) -> None:
    """CLAIM: receipt evidence must never silently vanish with an event."""
    config = _config()
    _append(config, gid="EV-FK", pos="POS-FK")
    _attest(config, "RC-FK", "EV-FK")
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM operator_position_event WHERE governance_id='EV-FK'"))


# --------------------------------------------------------------------------
# Raw SQL cross-check and rendering
# --------------------------------------------------------------------------


def test_the_receipt_matches_raw_sql_independently_of_the_repository(
    clean_tables: Engine, engine: Engine
) -> None:
    config = _config()
    _append(config, gid="EV-RAW", pos="POS-RAW")
    receipt = _attest(config, "RC-RAW", "EV-RAW", by="raw-check")
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT receipt_governance_id, event_governance_id, system_received_at, "
                "attested_by, attester_version FROM operator_event_receipt"
            )
        ).one()
    assert row[0] == receipt.receipt_governance_id
    assert row[1] == "EV-RAW"
    assert row[2] == receipt.system_received_at
    assert row[3] == "raw-check"
    assert row[4] == "M082.1"


def test_the_rendered_report_states_the_one_directional_guarantee(
    clean_tables: Engine,
) -> None:
    config = _config()
    _append(config, gid="EV-RND", pos="POS-RND")
    _attest(config, "RC-RND", "EV-RND")
    report = _report(config, datetime.now(UTC) + timedelta(days=1))
    text_out = render_attested_evidence_report_text(report)
    payload = render_attested_evidence_report_json(report)
    assert "upper bound witness on commit time, NOT the commit time" in text_out
    assert "ONE DIRECTION ONLY" in payload["banner"]
    assert json.dumps(payload, sort_keys=True)


# --------------------------------------------------------------------------
# Double-database knowledge proof
# --------------------------------------------------------------------------


@pytest.fixture
def second_database(engine: Engine) -> Iterator[str]:
    name = "m082_probe"
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    previous = os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE")
    try:
        os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = name
        alembic_command.upgrade(_alembic_config(), "head")
    finally:
        if previous is None:
            os.environ.pop("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", None)
        else:
            os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = previous
    try:
        yield name
    finally:
        with engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))


def test_two_databases_with_identical_attested_prefixes_agree_exactly(
    clean_tables: Engine, second_database: str
) -> None:
    """MANDATORY section 27."""
    primary, other = _config(), _config(second_database)
    assert primary.database != other.database

    for config in (primary, other):
        _append(config, gid="EV-SAME", pos="POS-SAME")
        _attest(config, "RC-SAME", "EV-SAME")

    cutoff = datetime.now(UTC) + timedelta(seconds=1)

    # Radically different tails: unattested events, and an attestation that
    # lands only AFTER the cutoff.
    time.sleep(1.2)
    _append(primary, gid="EV-TAIL-1", pos="POS-TAIL-1")
    _append(other, gid="EV-TAIL-2", pos="POS-TAIL-2", symbol="ZZZZ", recorded_day=-999)
    _attest(other, "RC-TAIL-2", "EV-TAIL-2")

    left = _report(primary, cutoff)
    right = _report(other, cutoff)

    # What the double-database proof actually asserts: given identical attested
    # EVIDENCE up to the cutoff, the two databases agree on WHICH events are
    # attested there, however radically their later tails differ.
    #
    # It does NOT assert identical receipt INSTANTS: the two databases were
    # attested at genuinely different moments, so their instants differ by
    # design. My first version compared whole entries and failed on exactly
    # that -- the assertion was wrong, not the code.
    assert left.attested_count == right.attested_count == 1
    eligible_left = [
        (e.event_governance_id, e.position_governance_id, e.instrument_symbol, e.status)
        for e in left.entries
        if e.status is AttestedEvidenceStatus.ATTESTED
    ]
    eligible_right = [
        (e.event_governance_id, e.position_governance_id, e.instrument_symbol, e.status)
        for e in right.entries
        if e.status is AttestedEvidenceStatus.ATTESTED
    ]
    assert (
        eligible_left
        == eligible_right
        == [("EV-SAME", "POS-SAME", "AAPL", AttestedEvidenceStatus.ATTESTED)]
    )

    # The differing tails are excluded on both sides, including the one that was
    # attested only AFTER the cutoff.
    assert [
        e.governance_id for e in attested_known_by(_events(primary), _receipts(primary), cutoff)
    ] == ["EV-SAME"]
    assert [
        e.governance_id for e in attested_known_by(_events(other), _receipts(other), cutoff)
    ] == ["EV-SAME"]
    assert any(e.status is AttestedEvidenceStatus.ATTESTED_AFTER_CUTOFF for e in right.entries)
    assert any(e.status is AttestedEvidenceStatus.NO_SYSTEM_RECEIPT_EVIDENCE for e in left.entries)
