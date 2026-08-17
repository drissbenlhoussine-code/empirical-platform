"""MILESTONE-082 receipt attestation against real PostgreSQL.

Mandated scenarios A-M, plus the commit-gap attack, the two-connection ordering
attack, the legacy-backfill prohibition, direct M076 bypass, immutability and
the double-database proof.

CORRECTED AFTER OWNER REVIEW. Finding 1 added the future-receipt and
future-event non-interference attacks and rewrote the double-database proof to
demand FULL output identity. Finding 2 added the backward-clock attack, which
required the attestation clock to become injectable, and withdrew every
assertion that the label bounds the commit time.
"""

from __future__ import annotations

import json
import os
import secrets
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
    build_attested_evidence_report,
    events_with_receipt_labelled_by,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.operator_event_receipt_repository import (  # noqa: E501
    PostgresOperatorEventReceiptRepository,
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


def _attest_at(  # noqa: ANN202
    config: PostgreSQLConfigSnapshot, rid: str, gid: str, at: datetime, by: str = "test"
):
    """Attest with a PINNED label, so two databases can hold identical evidence.

    The clock injection exists for the Owner-mandated backward-clock attack. It
    is also what makes the double-database proof able to demand FULL output
    identity: with two wall clocks the two receipts differ for a reason that has
    nothing to do with the leak under test, which is exactly the flaw that made
    the first version of that proof compare only a projection.
    """
    service = PostgresPersistenceService(config)
    try:
        service.initialize()
        repository = PostgresOperatorEventReceiptRepository(service, clock=lambda: at)
        return repository.attest(receipt_governance_id=rid, event_governance_id=gid, attested_by=by)
    finally:
        service.close()


def _events(config: PostgreSQLConfigSnapshot):  # noqa: ANN202
    with postgres_repository_runtime(config) as runtime:
        return runtime.operator_position_ledger.list_all()


def _receipts(config: PostgreSQLConfigSnapshot):  # noqa: ANN202
    with postgres_repository_runtime(config) as runtime:
        return runtime.operator_event_receipts.list_all()


def _report(config: PostgreSQLConfigSnapshot, cutoff: datetime):  # noqa: ANN202
    return build_attested_evidence_report(
        events=_events(config), receipts=_receipts(config), receipt_label_cutoff=cutoff
    )


def _rendered(report) -> tuple[str, str]:  # noqa: ANN001
    return (
        render_attested_evidence_report_text(report),
        json.dumps(render_attested_evidence_report_json(report), sort_keys=True),
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
    assert entry.event_governance_id == "EV-A"
    assert entry.system_received_at == receipt.system_received_at


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
    report = _report(config, datetime.now(UTC) + timedelta(days=1))
    # Absence is the representation: an unreceipted event is not listed at all,
    # so there is no placeholder anyone could later fill in.
    assert report.entries == ()
    assert report.attested_count == 0
    assert "EV-LEG" not in _rendered(report)[0]


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
    assert report.entries == ()
    assert report.attested_count == 0
    assert "EV-BYPASS" not in _rendered(report)[0]
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
    labelled = events_with_receipt_labelled_by(_events(config), _receipts(config), cutoff)
    assert (len(labelled) == 1) is (offset_seconds >= 0)
    assert (len(_report(config, cutoff).entries) == 1) is (offset_seconds >= 0)


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
    assert events_with_receipt_labelled_by(_events(config), _receipts(config), cutoff) == ()
    assert _report(config, cutoff).entries == ()


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
    assert report.entries == ()
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


def test_the_rendered_report_states_the_causal_claim_and_the_retraction(
    clean_tables: Engine,
) -> None:
    config = _config()
    _append(config, gid="EV-RND", pos="POS-RND")
    _attest(config, "RC-RND", "EV-RND")
    report = _report(config, datetime.now(UTC) + timedelta(days=1))
    text_out = render_attested_evidence_report_text(report)
    payload = render_attested_evidence_report_json(report)
    assert "system-assigned label, NOT a bound on commit time" in text_out
    assert "cannot say how many events it excluded" in text_out
    assert "re-evaluating this same cutoff later can return MORE" in text_out
    assert "RETRACTED" in payload["banner"]
    assert "does NOT replace M079's recorded_at firewall" in payload["banner"]
    # The withdrawn claims must be gone from BOTH renderings.
    for withdrawn in ("upper bound witness", "ONE DIRECTION ONLY", "can never OVERSTATE"):
        assert withdrawn not in text_out, withdrawn
        assert withdrawn not in json.dumps(payload), withdrawn


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
    """MANDATORY section 27, STRENGTHENED by Owner review finding 1.

    The first version compared only a PROJECTION of the entries, because the two
    databases were attested at genuinely different wall-clock moments and their
    instants therefore differed. That weakness is what let the future-receipt
    leak survive it. With the label pinned, the two databases hold GENUINELY
    IDENTICAL evidence at the cutoff, so the proof can now demand what it should
    always have demanded: the FULL report object, the FULL text and the FULL
    JSON are identical.
    """
    primary, other = _config(), _config(second_database)
    assert primary.database != other.database

    pinned = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    for config in (primary, other):
        _append(config, gid="EV-SAME", pos="POS-SAME")
        _attest_at(config, "RC-SAME", "EV-SAME", pinned)

    cutoff = pinned + timedelta(seconds=1)

    # Radically different tails: an unattested event on one side, and on the
    # other an event attested only AFTER the cutoff.
    _append(primary, gid="EV-TAIL-1", pos="POS-TAIL-1")
    _append(other, gid="EV-TAIL-2", pos="POS-TAIL-2", symbol="ZZZZ", recorded_day=-999)
    _attest_at(other, "RC-TAIL-2", "EV-TAIL-2", cutoff + timedelta(minutes=5))

    left, right = _report(primary, cutoff), _report(other, cutoff)

    assert left == right
    assert _rendered(left) == _rendered(right)
    assert left.attested_count == 1
    assert [e.event_governance_id for e in left.entries] == ["EV-SAME"]

    # Neither tail leaks any identity into either rendering.
    for leak in ("EV-TAIL-1", "POS-TAIL-1", "EV-TAIL-2", "POS-TAIL-2", "ZZZZ"):
        for rendering in (*_rendered(left), *_rendered(right)):
            assert leak not in rendering, leak

    for config in (primary, other):
        assert [
            e.governance_id
            for e in events_with_receipt_labelled_by(_events(config), _receipts(config), cutoff)
        ] == ["EV-SAME"]


# --------------------------------------------------------------------------
# OWNER REVIEW FINDING 1 - historical non-interference
# --------------------------------------------------------------------------


def test_a_receipt_created_after_the_cutoff_changes_nothing(
    clean_tables: Engine, second_database: str
) -> None:
    """OWNER MANDATORY ATTACK A - future receipt non-interference.

    Reproduced against the PRE-CORRECTION code, where DB-A reported
    ATTESTED_AFTER_CUTOFF and DB-B reported NO_SYSTEM_RECEIPT_EVIDENCE, with
    `attested_after_cutoff_count` differing 1 vs 0. Both databases must now be
    indistinguishable at the cutoff.
    """
    db_a, db_b = _config(), _config(second_database)
    pinned = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    for config in (db_a, db_b):
        _append(config, gid="EV-N1", pos="POS-N1")
        _attest_at(config, "RC-N1", "EV-N1", pinned)
        _append(config, gid="EV-N2", pos="POS-N2")

    cutoff = pinned + timedelta(seconds=1)
    # DB-A alone attests EV-N2, AFTER the cutoff.
    _attest_at(db_a, "RC-N2", "EV-N2", cutoff + timedelta(hours=1))

    left, right = _report(db_a, cutoff), _report(db_b, cutoff)
    assert left == right
    assert _rendered(left) == _rendered(right)
    assert left.attested_count == right.attested_count == 1
    assert all(e.event_governance_id != "EV-N2" for e in left.entries)
    assert "EV-N2" not in _rendered(left)[0]
    assert "EV-N2" not in _rendered(left)[1]


def test_an_event_created_after_the_cutoff_changes_nothing(
    clean_tables: Engine, second_database: str
) -> None:
    """OWNER MANDATORY ATTACK B - future event existence non-interference.

    Reproduced against the PRE-CORRECTION code, which listed the future event
    and leaked its id, position and instrument symbol into the historical text.
    """
    db_a, db_b = _config(), _config(second_database)
    pinned = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    for config in (db_a, db_b):
        _append(config, gid="EV-P1", pos="POS-P1")
        _attest_at(config, "RC-P1", "EV-P1", pinned)

    cutoff = pinned + timedelta(seconds=1)
    # DB-A alone gains an entirely new, never-attested event.
    _append(db_a, gid="EV-FUTURE", pos="POS-FUTURE", symbol="ZZZZ", recorded_day=-999)

    left, right = _report(db_a, cutoff), _report(db_b, cutoff)
    assert left == right
    assert _rendered(left) == _rendered(right)
    assert len(left.entries) == len(right.entries) == 1
    for leak in ("EV-FUTURE", "POS-FUTURE", "ZZZZ"):
        for rendering in _rendered(left):
            assert leak not in rendering, leak


def test_no_count_in_the_artifact_is_aware_of_anything_after_the_cutoff(
    clean_tables: Engine,
) -> None:
    """OWNER: no future-tail counts, and no replacement count of hidden rows."""
    config = _config()
    pinned = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    _append(config, gid="EV-C1", pos="POS-C1")
    _attest_at(config, "RC-C1", "EV-C1", pinned)
    cutoff = pinned + timedelta(seconds=1)

    before = _report(config, cutoff)
    for n in range(2, 6):
        _append(config, gid=f"EV-C{n}", pos=f"POS-C{n}")
        _attest_at(config, f"RC-C{n}", f"EV-C{n}", cutoff + timedelta(minutes=n))
    after = _report(config, cutoff)

    assert before == after
    assert _rendered(before) == _rendered(after)
    payload = render_attested_evidence_report_json(after)
    assert set(payload) == {
        "banner",
        "receipt_label_cutoff",
        "attested_count",
        "entries",
        "limitations",
    }
    assert payload["attested_count"] == 1


# --------------------------------------------------------------------------
# OWNER REVIEW FINDING 2 - the backward clock
# --------------------------------------------------------------------------


def test_a_backward_clock_breaks_the_wall_clock_implication(clean_tables: Engine) -> None:
    """OWNER MANDATORY BACKWARD-CLOCK ATTACK.

    The event commits for real. The read-back succeeds. The host clock then
    returns an instant TEN MINUTES EARLIER. A cutoff W chosen between the label
    and the real commit selects the event, although at real wall-clock W the
    event had not committed.

    This is executed, not argued, and it is why the claim

        system_received_at <= W  IMPLIES  durably committed by W

    is RETRACTED. The CAUSAL claim -- the read-back preceded the receipt --
    survives untouched, because it never depended on the clock.
    """
    config = _config()
    _append(config, gid="EV-CLK", pos="POS-CLK")
    real_commit = datetime.now(UTC)

    backward = real_commit - timedelta(minutes=10)
    receipt = _attest_at(config, "RC-CLK", "EV-CLK", backward, by="clock-attack")
    assert receipt.system_received_at == backward
    assert receipt.system_received_at < real_commit

    cutoff = backward + timedelta(minutes=5)
    assert cutoff < real_commit

    report = _report(config, cutoff)
    assert [e.event_governance_id for e in report.entries] == ["EV-CLK"]
    assert [
        e.governance_id
        for e in events_with_receipt_labelled_by(_events(config), _receipts(config), cutoff)
    ] == ["EV-CLK"]

    # The artifact must therefore make NO wall-clock claim about W.
    #
    # PROBE ERROR, recorded rather than hidden: the first version of this
    # assertion searched for the bare substring "upper bound" and failed on the
    # artifact's own RETRACTION of that very claim -- the same mistake as M081's
    # currency search, which flagged the sentence denying currency. The check
    # below distinguishes an ACTIVE claim from a retraction by requiring every
    # surviving mention to sit in a retracting sentence.
    text_out, payload = _rendered(report)
    for withdrawn in ("upper bound witness", "can never OVERSTATE", "ONE DIRECTION ONLY"):
        assert withdrawn not in text_out, withdrawn
    for line in text_out.splitlines():
        if "upper bound" in line.lower():
            assert "RETRACTED" in line or "retract" in line.lower(), line
    assert "DOES NOT prove the event was durably committed by that cutoff" in text_out
    assert "moved BACKWARD" in payload


def test_the_causal_claim_survives_the_backward_clock(clean_tables: Engine) -> None:
    """What M082 still proves: attestation cannot precede the event's commit.

    A receipt is impossible for an event that is not readable, whatever the
    clock says -- the read-back, not the label, is the gate.
    """
    config = _config()
    with pytest.raises(UnknownOperatorEventError):
        _attest_at(config, "RC-GHOST", "EV-NOT-COMMITTED", datetime(1999, 1, 1, tzinfo=UTC))
    assert _receipts(config) == ()

    # And once committed, a receipt labelled in 1999 is still only created after
    # the read-back succeeded; the label is a label, not a licence.
    _append(config, gid="EV-CAUSAL", pos="POS-CAUSAL")
    receipt = _attest_at(config, "RC-CAUSAL", "EV-CAUSAL", datetime(1999, 1, 1, tzinfo=UTC))
    assert receipt.system_received_at.year == 1999
    assert len(_receipts(config)) == 1


def test_a_clock_returning_a_naive_datetime_is_refused(clean_tables: Engine) -> None:
    """A label with no offset names no instant, so it may not be stored."""
    config = _config()
    _append(config, gid="EV-NAIVE", pos="POS-NAIVE")
    service = PostgresPersistenceService(config)
    try:
        service.initialize()
        repository = PostgresOperatorEventReceiptRepository(
            service, clock=lambda: datetime(2026, 5, 1, 12, 0)
        )
        with pytest.raises(ValueError, match="naive datetime"):
            repository.attest(
                receipt_governance_id="RC-NAIVE",
                event_governance_id="EV-NAIVE",
                attested_by="naive",
            )
    finally:
        service.close()
    assert _receipts(config) == ()


def test_production_wiring_uses_the_host_clock_and_takes_no_caller_instant() -> None:
    """The injection is for tests only; nothing reaches it from the CLI."""
    import inspect

    from empirical_platform.entrypoints import get_attested_evidence_report as cli

    source = inspect.getsource(cli)
    assert "clock" not in source
    assert "PostgresOperatorEventReceiptRepository" not in source
    signature = inspect.signature(PostgresOperatorEventReceiptRepository.__init__)
    assert signature.parameters["clock"].default is None


# --------------------------------------------------------------------------
# OWNER REVIEW FINDING 4 - the persisted row must itself prove the causal claim
# --------------------------------------------------------------------------


_RAW_EVENT_SQL = text(
    "INSERT INTO operator_position_event (runtime_id, governance_id, "
    "position_governance_id, instrument_symbol, event_kind, quantity, "
    "asserted_price, event_timestamp, recorded_at) "
    "VALUES (:rt, :gid, :pos, 'FAKE', 'OPENED', 1, 100, :t, :t)"
)

_RAW_RECEIPT_SQL = text(
    "INSERT INTO operator_event_receipt (receipt_governance_id, "
    "event_governance_id, system_received_at, attested_by, attester_version) "
    "VALUES (:rid, :gid, :ts, :by, :ver)"
)


def _raw_event(gid: str, pos: str) -> dict[str, object]:
    return {"rt": f"rt-{gid}", "gid": gid, "pos": pos, "t": _T0}


def _raw_receipt(
    rid: str, gid: str, ts: datetime, by: str = "forged", ver: str = "M082.1"
) -> dict[str, object]:
    return {"rid": rid, "gid": gid, "ts": ts, "by": by, "ver": ver}


def test_a_same_transaction_event_and_receipt_is_refused_by_the_database(
    clean_tables: Engine, engine: Engine
) -> None:
    """OWNER MANDATORY ATTACK, finding 4.

    Reproduced against the PRE-TRIGGER head: the insert succeeded and the M082
    report listed the row as authoritative with a forged 2020 label and a forged
    attester. The foreign key was satisfied because the event was visible to the
    very transaction that wrote it, so the persisted row proved nothing.

    A BEFORE INSERT trigger now refuses it. The causal claim therefore holds for
    every persisted row, not only for rows produced through `attest()`.
    """
    config = _config()
    with pytest.raises(sa.exc.ProgrammingError, match="PRIOR COMMITTED event"):
        with engine.begin() as conn:
            conn.execute(_RAW_EVENT_SQL, _raw_event("EV-SAMETX", "POS-SAMETX"))
            conn.execute(
                _RAW_RECEIPT_SQL,
                _raw_receipt("RC-SAMETX", "EV-SAMETX", datetime(2020, 1, 1, tzinfo=UTC)),
            )
    assert _receipts(config) == ()
    assert _report(config, datetime.now(UTC) + timedelta(days=1)).entries == ()


@pytest.mark.parametrize("depth", [1, 2])
def test_a_savepoint_wrapped_same_transaction_insert_is_also_refused(
    clean_tables: Engine, engine: Engine, depth: int
) -> None:
    """A subtransaction gets its OWN, HIGHER xid.

    A naive `xmin = pg_current_xact_id()::xid` check would MISS this, which is
    why the trigger tests whether the writing transaction is still IN PROGRESS
    instead. Measured directly on PostgreSQL 16.13 before choosing the
    mechanism: same-txn `equal=true`, savepoint `equal=false`.
    """
    config = _config()
    gid = f"EV-SAVE{depth}"
    with pytest.raises(sa.exc.ProgrammingError, match="PRIOR COMMITTED event"):
        with engine.connect() as conn:
            tx = conn.begin()
            for n in range(depth):
                conn.execute(text(f"SAVEPOINT s{n}"))
            conn.execute(_RAW_EVENT_SQL, _raw_event(gid, f"POS-SAVE{depth}"))
            for n in reversed(range(depth)):
                conn.execute(text(f"RELEASE SAVEPOINT s{n}"))
            conn.execute(
                _RAW_RECEIPT_SQL,
                _raw_receipt(f"RC-SAVE{depth}", gid, datetime(2020, 1, 1, tzinfo=UTC)),
            )
            tx.commit()
    assert _receipts(config) == ()


def test_rollback_to_savepoint_then_reinsert_is_still_refused(
    clean_tables: Engine, engine: Engine
) -> None:
    config = _config()
    with pytest.raises(sa.exc.ProgrammingError, match="PRIOR COMMITTED event"):
        with engine.connect() as conn:
            tx = conn.begin()
            conn.execute(text("SAVEPOINT r"))
            conn.execute(_RAW_EVENT_SQL, _raw_event("EV-RB", "POS-RB"))
            conn.execute(text("ROLLBACK TO SAVEPOINT r"))
            conn.execute(_RAW_EVENT_SQL, _raw_event("EV-RB", "POS-RB"))
            conn.execute(
                _RAW_RECEIPT_SQL,
                _raw_receipt("RC-RB", "EV-RB", datetime(2020, 1, 1, tzinfo=UTC)),
            )
            tx.commit()
    assert _receipts(config) == ()


def test_a_concurrent_committed_writer_with_a_higher_xid_is_not_falsely_refused(
    clean_tables: Engine, engine: Engine
) -> None:
    """The false-REJECTION attack on the trigger itself.

    A transaction that starts LATER can hold a HIGHER xid and still commit
    first. A plain xid ordering comparison would refuse a perfectly legitimate
    receipt here. Measured: reader xid 140579, concurrent row xmin 140580,
    status `committed`. The attestation must succeed.
    """
    config = _config()
    with engine.connect() as reader:
        reader_tx = reader.begin()
        reader.execute(text("SELECT pg_current_xact_id()"))  # force an xid now
        # A different, LATER transaction writes and commits.
        _append(config, gid="EV-CONCX", pos="POS-CONCX")
        reader_tx.commit()

    receipt = _attest(config, "RC-CONCX", "EV-CONCX")
    assert receipt.event_governance_id == "EV-CONCX"
    assert len(_receipts(config)) == 1


def test_the_repository_attest_path_still_works_under_the_trigger(
    clean_tables: Engine,
) -> None:
    """The enforcement must not break the only legitimate pathway."""
    config = _config()
    _append(config, gid="EV-OK", pos="POS-OK")
    receipt = _attest(config, "RC-OK", "EV-OK")
    assert receipt.attester_version == "M082.1"
    assert [e.event_governance_id for e in _report(config, datetime.now(UTC)).entries] == ["EV-OK"]


def test_a_direct_insert_for_an_already_committed_event_is_still_accepted(
    clean_tables: Engine, engine: Engine
) -> None:
    """THE RESIDUAL LIMITATION, asserted rather than hidden.

    The trigger closes the same-transaction hole. It does NOT authenticate the
    label, the attester name or the attester version. A direct SQL caller with
    write access can still forge all three for an ALREADY COMMITTED event, and
    the view cannot tell it apart from one `attest()` produced.

    This test EXISTS TO PIN THAT DOWN. If it ever starts failing, the artifact's
    limitation text has become too weak, not too strong.
    """
    config = _config()
    _append(config, gid="EV-FORGE", pos="POS-FORGE")
    with engine.begin() as conn:
        conn.execute(
            _RAW_RECEIPT_SQL,
            _raw_receipt(
                "RC-FORGE",
                "EV-FORGE",
                datetime(1999, 1, 1, tzinfo=UTC),
                by="not-the-attester",
                ver="M999-FORGED",
            ),
        )
    entries = _report(config, datetime.now(UTC) + timedelta(days=1)).entries
    forged = next(e for e in entries if e.event_governance_id == "EV-FORGE")
    assert forged.system_received_at.year == 1999
    assert forged.attested_by == "not-the-attester"

    report = _report(config, datetime.now(UTC) + timedelta(days=1))
    joined = " ".join(report.limitations)
    assert "UNAUTHENTICATED LABELS" in joined
    assert "cannot distinguish" in joined


def test_immutability_is_row_level_update_delete_only(clean_tables: Engine, engine: Engine) -> None:
    """The wording must match exactly what is enforced.

    TRUNCATE is a statement-level operation a row trigger does not intercept.
    The test asserts that, so the artifact cannot claim absolute immutability.
    """
    config = _config()
    _append(config, gid="EV-TRUNC", pos="POS-TRUNC")
    _attest(config, "RC-TRUNC", "EV-TRUNC")
    assert len(_receipts(config)) == 1

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE operator_event_receipt"))
    assert _receipts(config) == (), "TRUNCATE is NOT blocked, and the limitations say so"

    joined = " ".join(_report(config, datetime.now(UTC)).limitations)
    assert "ROW-LEVEL UPDATE/DELETE ONLY" in joined
    assert "NOT absolute database immutability" in joined


# --------------------------------------------------------------------------
# OWNER REVIEW FINDING 5 - the label cutoff is not a stable snapshot
# --------------------------------------------------------------------------


def test_a_later_backdated_receipt_changes_the_same_cutoff(clean_tables: Engine) -> None:
    """OWNER MANDATORY BACKDATED-LABEL ATTACK.

    This output SHOULD change, and the artifact must say so rather than claim
    point-in-time stability it cannot deliver.
    """
    config = _config()
    cutoff = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    _append(config, gid="EV-B1", pos="POS-B1")
    _attest_at(config, "RC-B1", "EV-B1", cutoff - timedelta(hours=1))

    before = _report(config, cutoff)
    before_rendered = _rendered(before)
    assert [e.event_governance_id for e in before.entries] == ["EV-B1"]

    # A LATER attestation, through the REAL path, with a backward clock.
    _append(config, gid="EV-B2", pos="POS-B2")
    _attest_at(config, "RC-B2", "EV-B2", cutoff - timedelta(minutes=10))

    after = _report(config, cutoff)
    assert after != before
    assert _rendered(after) != before_rendered
    assert [e.event_governance_id for e in after.entries] == ["EV-B1", "EV-B2"]

    text_out, payload = _rendered(after)
    assert "REPEATED EVALUATION AT THE SAME CUTOFF CAN CHANGE" in payload
    assert "re-evaluating this same cutoff later can return MORE" in text_out
    assert "NOT a historical snapshot" in payload


def test_a_later_forward_labelled_receipt_does_not_change_the_same_cutoff(
    clean_tables: Engine,
) -> None:
    """The control. Only BACKDATED labels destabilise the cutoff."""
    config = _config()
    cutoff = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    _append(config, gid="EV-F1", pos="POS-F1")
    _attest_at(config, "RC-F1", "EV-F1", cutoff - timedelta(hours=1))
    before = _report(config, cutoff)

    _append(config, gid="EV-F2", pos="POS-F2")
    _attest_at(config, "RC-F2", "EV-F2", cutoff + timedelta(hours=1))

    after = _report(config, cutoff)
    assert after == before
    assert _rendered(after) == _rendered(before)


# --------------------------------------------------------------------------
# OWNER REVIEW FINDING 6 - the enforcement must FAIL CLOSED
# --------------------------------------------------------------------------


# Generated per run rather than hardcoded: a literal here is both a lint finding
# and a bad habit to leave in a repository, even for a throwaway role.
_PROBE_ROLE_PASSWORD = secrets.token_urlsafe(18)

_DROP_PROBE_ROLE = text(
    """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'm082_failclosed_probe') THEN
        -- DROP ROLE refuses while the role still holds grants, and DROP OWNED BY
        -- has no IF EXISTS, so both need this guard. Found by executing the
        -- cleanup, not by reading documentation.
        DROP OWNED BY m082_failclosed_probe CASCADE;
        DROP ROLE m082_failclosed_probe;
    END IF;
END $$
"""
)


def test_an_unexpected_checker_error_fails_closed(clean_tables: Engine, engine: Engine) -> None:
    """OWNER MANDATORY ATTACK 8, and the point of finding 6.

    An earlier version wrapped the status call in `EXCEPTION WHEN OTHERS` and
    treated ANY failure as an unknown status, which was then ACCEPTED. That made
    the invariant FAIL OPEN: an unexpected error in the checker became
    permission to insert.

    This drives a real error through the enforcement path by revoking EXECUTE on
    `pg_xact_status` from the inserting role. The event here is genuinely
    PRIOR-COMMITTED, so without the error the INSERT would be accepted -- which
    is exactly what makes the control at the end meaningful rather than
    decorative.
    """
    config = _config()
    _append(config, gid="EV-FAILCLOSED", pos="POS-FAILCLOSED")

    with engine.begin() as conn:
        conn.execute(_DROP_PROBE_ROLE)
        conn.execute(
            text("CREATE ROLE m082_failclosed_probe LOGIN PASSWORD :pw").bindparams(
                pw=_PROBE_ROLE_PASSWORD
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO m082_failclosed_probe"))
        conn.execute(
            text("GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO m082_failclosed_probe")
        )

    probe_engine = sa.create_engine(
        _config()
        .sqlalchemy_url()
        .set(username="m082_failclosed_probe", password=_PROBE_ROLE_PASSWORD)
    )
    try:
        with engine.begin() as conn:
            conn.execute(text("REVOKE EXECUTE ON FUNCTION pg_xact_status(xid8) FROM PUBLIC"))
        try:
            with pytest.raises(sa.exc.ProgrammingError, match="permission denied for function"):
                with probe_engine.begin() as conn:
                    conn.execute(
                        _RAW_RECEIPT_SQL,
                        _raw_receipt(
                            "RC-FAILCLOSED", "EV-FAILCLOSED", datetime(2026, 2, 1, tzinfo=UTC)
                        ),
                    )
            assert _receipts(config) == (), "the enforcement must FAIL CLOSED, not fail open"
        finally:
            with engine.begin() as conn:
                conn.execute(text("GRANT EXECUTE ON FUNCTION pg_xact_status(xid8) TO PUBLIC"))

        # CONTROL: the identical INSERT succeeds once the checker can run, which
        # proves the refusal above came from the checker error and nothing else.
        with probe_engine.begin() as conn:
            conn.execute(
                _RAW_RECEIPT_SQL,
                _raw_receipt("RC-FAILCLOSED", "EV-FAILCLOSED", datetime(2026, 2, 1, tzinfo=UTC)),
            )
        assert len(_receipts(config)) == 1
    finally:
        probe_engine.dispose()
        with engine.begin() as conn:
            conn.execute(_DROP_PROBE_ROLE)


def test_the_trigger_body_contains_no_broad_exception_handler(
    clean_tables: Engine, engine: Engine
) -> None:
    """A grep is not enough on its own, but the INSTALLED body is worth asserting.

    The behavioural proof is the test above. This reads what PostgreSQL actually
    stored, so a future edit cannot reintroduce the swallow silently.
    """
    with engine.begin() as conn:
        body = conn.execute(
            text(
                "SELECT prosrc FROM pg_proc "
                "WHERE proname = 'operator_event_receipt_requires_prior_commit'"
            )
        ).scalar_one()
    executable = "\n".join(line for line in body.splitlines() if not line.strip().startswith("--"))
    upper = executable.upper()
    # `RAISE EXCEPTION` is the refusal itself and must stay. What must NOT exist
    # is an exception HANDLER around the status call.
    assert "WHEN OTHERS" not in upper
    assert "EXCEPTION WHEN" not in upper
    assert "pg_xact_status" in executable
    assert "RAISE EXCEPTION" in upper, "the refusal must still be raised"


def test_a_frozen_event_row_is_still_accepted(clean_tables: Engine, engine: Engine) -> None:
    """OWNER ATTACK 6. VACUUM FREEZE must not turn a valid event into a refusal."""
    config = _config()
    _append(config, gid="EV-FROZEN", pos="POS-FROZEN")
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("VACUUM FREEZE operator_position_event"))
    receipt = _attest(config, "RC-FROZEN", "EV-FROZEN")
    assert receipt.event_governance_id == "EV-FROZEN"
    assert len(_receipts(config)) == 1


def test_an_aborted_writers_event_is_never_visible_so_cannot_be_attested(
    clean_tables: Engine, engine: Engine
) -> None:
    """OWNER ATTACK 7 - define the aborted case honestly rather than assume it.

    Measured: an aborted writer's row is visible to NOBODY, so the trigger can
    never see one and `aborted` is unreachable for a visible row. The trigger
    refuses on `aborted` anyway, because an aborted writer's event never
    committed -- accepting it would be the wrong direction for an invariant.
    """
    config = _config()
    with engine.connect() as conn:
        tx = conn.begin()
        conn.execute(_RAW_EVENT_SQL, _raw_event("EV-ABORTED", "POS-ABORTED"))
        tx.rollback()

    with engine.begin() as conn:
        visible = conn.execute(
            text("SELECT count(*) FROM operator_position_event WHERE governance_id='EV-ABORTED'")
        ).scalar_one()
    assert visible == 0, "an aborted writer's row must be visible to nobody"

    # And the foreign key, not the status check, is what speaks for a row that
    # does not exist at all.
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                _RAW_RECEIPT_SQL,
                _raw_receipt("RC-ABORTED", "EV-ABORTED", datetime(2026, 2, 1, tzinfo=UTC)),
            )
    assert _receipts(config) == ()
