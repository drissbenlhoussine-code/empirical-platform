"""MILESTONE-070 real-PostgreSQL daily research session acceptance
tests.

Covers the full one-command orchestration -> persist -> retrieve
lifecycle against real PostgreSQL using the deterministic, offline
`FakeMarketDataSource` (mirroring the established M069
`EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS` gating pattern -- the real,
network-capable CLI subprocess run is a separate, additionally-gated
test), raw-SQL cross-verification, the mandatory as-of firewall attack
(future-data attack), the partial-failure attack (completed-stage
evidence preservation, no downstream fabrication), the source-tamper
attack, and duplicate-session-id handling.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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

from empirical_platform.decision_candidate.market_data_acquisition import FakeMarketDataSource
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists
from empirical_platform.usecases.get_daily_research_session import (
    GetDailyResearchSessionHandler,
    GetDailyResearchSessionQuery,
)
from empirical_platform.usecases.run_daily_research_session import (
    RunDailyResearchSessionHandler,
    build_run_daily_research_session_command,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 1, 1, tzinfo=UTC)

_ALL_TABLES = [
    "research_session_decision",
    "research_session_stage",
    "research_session",
    "historical_backtest_trade",
    "historical_backtest_run",
    "position_plan",
    "trade_plan",
    "trading_opportunity_scan_evaluation",
    "trading_opportunity_scan",
    "decision_candidate",
    "dataset_snapshot_source_file",
    "dataset_snapshot",
    "instrument_master",
    "evidence_package_transition",
    "evidence_package_artifact_reference",
    "evidence_package_criterion_result",
    "evidence_package",
    "run_transition",
    "run_manifest",
    "run",
    "campaign_transition",
    "campaign",
]


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _network_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS") == "1"


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=2,
        max_overflow=0,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m070-test",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


def _reset_public_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not _postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    eng = sa.create_engine(_config().sqlalchemy_url())
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(scope="module")
def upgraded_schema(engine: Engine) -> Iterator[Engine]:
    _reset_public_schema(engine)
    alembic_command.upgrade(_alembic_config(), "head")
    yield engine
    _reset_public_schema(engine)


@pytest.fixture
def clean_tables(upgraded_schema: Engine) -> Engine:
    with upgraded_schema.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))  # noqa: S608
    return upgraded_schema


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _breakout_csv(base_price: Decimal, breakout_pct: Decimal, breakout_vol: int) -> bytes:
    lines = ["timestamp,open,high,low,close,volume"]
    for i in range(10):
        ts = (_T0 + timedelta(days=i)).isoformat()
        lines.append(
            f"{ts},{base_price:.4f},{base_price * Decimal('1.001'):.4f},"
            f"{base_price * Decimal('0.999'):.4f},{base_price:.4f},50000"
        )
    breakout_close = base_price * (Decimal("1") + breakout_pct)
    for j in range(6):
        ts = (_T0 + timedelta(days=10 + j)).isoformat()
        c = breakout_close * (Decimal("1") + Decimal("0.01") * j)
        high = c * Decimal("1.01")
        low = c * Decimal("0.99")
        lines.append(f"{ts},{c:.4f},{high:.4f},{low:.4f},{c:.4f},{breakout_vol}")
    return ("\n".join(lines) + "\n").encode()


_FIXTURES = {
    "AAPL": _breakout_csv(Decimal("100"), Decimal("0.10"), 500000),
    "MSFT": _breakout_csv(Decimal("400"), Decimal("0.08"), 400000),
    "GOOG": _breakout_csv(Decimal("150"), Decimal("0.001"), 10000),
}
_AS_OF = _T0 + timedelta(days=10)


def _run_session(
    *,
    session_governance_id: str,
    artifact_path: Path,
    config: PostgreSQLConfigSnapshot,
    universe: tuple[str, ...] = ("AAPL", "MSFT", "GOOG"),
    fixtures: dict[str, bytes] | None = None,
    as_of: datetime = _AS_OF,
    lookback_days: int = 20,
    reference_window_size: int = 10,
) -> object:
    clock = _FixedClock(as_of)
    source = FakeMarketDataSource(fixtures if fixtures is not None else _FIXTURES, clock=clock)
    from empirical_platform.shared.identifiers import UuidRuntimeIdentifierGenerator

    generator = UuidRuntimeIdentifierGenerator()
    with postgres_repository_runtime(config) as runtime:
        handler = RunDailyResearchSessionHandler(
            campaign_repository=runtime.campaigns,
            run_repository=runtime.runs,
            evidence_package_repository=runtime.evidence_packages,
            dataset_snapshot_repository=runtime.dataset_snapshots,
            instrument_master_repository=runtime.instrument_masters,
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            historical_backtest_repository=runtime.historical_backtests,
            research_session_repository=runtime.research_sessions,
            clock=clock,
            runtime_identifier_generator=generator,
        )
        return handler.handle(
            build_run_daily_research_session_command(
                session_governance_id=session_governance_id,
                as_of=as_of,
                universe=universe,
                lookback_days=lookback_days,
                artifact_path=str(artifact_path),
                account_equity=Decimal("100000"),
                risk_percent=Decimal("0.01"),
                source=source,
                runtime_identifier_generator=generator,
                reference_window_size=reference_window_size,
            )
        )


def test_full_offline_lifecycle_and_raw_sql_verification(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    session = _run_session(
        session_governance_id="RESEARCH-6800",
        artifact_path=tmp_path / "artifact.json",
        config=config,
    )
    assert session.status.value == "COMPLETED"  # type: ignore[attr-defined]
    assert session.candidate_count == 2  # type: ignore[attr-defined]  # AAPL + MSFT breakouts
    assert session.backtest_run_governance_id is not None  # type: ignore[attr-defined]

    with postgres_repository_runtime(config) as runtime:
        handler = GetDailyResearchSessionHandler(repository=runtime.research_sessions)
        retrieved = handler.handle(GetDailyResearchSessionQuery(identity=session.identity))  # type: ignore[attr-defined]
    assert retrieved == session

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            session_row = (
                conn.execute(
                    text(
                        "SELECT status, candidate_count, dataset_id, dataset_version, "
                        "campaign_governance_id, run_governance_id, "
                        "evidence_package_governance_id "
                        "FROM research_session WHERE governance_id = 'RESEARCH-6800'"
                    )
                )
                .mappings()
                .one()
            )
            stage_rows = (
                conn.execute(
                    text(
                        "SELECT stage_name, status FROM research_session_stage "
                        "WHERE session_runtime_id = "
                        "(SELECT runtime_id FROM research_session "
                        "WHERE governance_id = 'RESEARCH-6800') "
                        "ORDER BY stage_sequence"
                    )
                )
                .mappings()
                .all()
            )
            decision_rows = (
                conn.execute(
                    text(
                        "SELECT instrument_symbol, scan_decision FROM research_session_decision "
                        "WHERE session_runtime_id = "
                        "(SELECT runtime_id FROM research_session "
                        "WHERE governance_id = 'RESEARCH-6800') "
                        "ORDER BY decision_sequence"
                    )
                )
                .mappings()
                .all()
            )
            campaign_count = conn.execute(
                text("SELECT count(*) FROM campaign WHERE governance_id = :g"),
                {"g": session_row["campaign_governance_id"]},
            ).scalar_one()
    finally:
        engine.dispose()

    assert session_row["status"] == "COMPLETED"
    assert session_row["candidate_count"] == 2
    assert [r["stage_name"] for r in stage_rows] == [
        "GOVERNANCE_SETUP",
        "DATA_ACQUISITION",
        "DATASET_INTEGRITY_CHECK",
        "CANDIDATE_SCAN",
        "TRADE_PLANNING",
        "POSITION_SIZING",
        "BACKTEST_EVIDENCE",
    ]
    assert all(r["status"] == "COMPLETED" for r in stage_rows)
    assert {r["instrument_symbol"] for r in decision_rows} == {"AAPL", "MSFT", "GOOG"}
    assert campaign_count == 1


def test_multi_instrument_session_exercises_several_instruments(
    clean_tables: Engine, tmp_path: Path
) -> None:
    session = _run_session(
        session_governance_id="RESEARCH-6801",
        artifact_path=tmp_path / "artifact.json",
        config=_config(),
    )
    assert len(session.requested_universe) == 3  # type: ignore[attr-defined]
    assert len(session.decisions) == 3  # type: ignore[attr-defined]
    assert session.candidate_count >= 1  # type: ignore[attr-defined]


def test_future_data_attack_as_of_firewall(clean_tables: Engine, tmp_path: Path) -> None:
    """Mission Phase 21: a session as-of T must not be able to consume
    data strictly after T, even when the underlying fixture happens to
    contain bars beyond T."""
    config = _config()
    cutoff_as_of = _T0 + timedelta(days=5)
    session_early = _run_session(
        session_governance_id="RESEARCH-6802",
        artifact_path=tmp_path / "early.json",
        config=config,
        fixtures={
            "AAPL": _breakout_csv(Decimal("100"), Decimal("0.10"), 500000),
            "MSFT": _breakout_csv(Decimal("400"), Decimal("0.08"), 400000),
        },
        universe=("AAPL", "MSFT"),
        as_of=cutoff_as_of,
        lookback_days=10,
        reference_window_size=4,
    )
    assert session_early.status.value == "COMPLETED"  # type: ignore[attr-defined]
    early_dataset_sha = session_early.dataset_sha256  # type: ignore[attr-defined]

    # A second session, same as_of, but the underlying vendor bytes now
    # additionally contain wildly different data strictly AFTER the
    # cutoff (added identically to every instrument so the M065 shared
    # timestamp-grid invariant still admits the fetch). The as_of-bounded
    # evaluation window must never see that future bar, so every
    # downstream decision must be unaffected by its presence.
    _future_bar = b"\n2026-01-20T00:00:00+00:00,9999,9999,9999,9999,999999999\n"
    tampered_future_fixtures = {
        "AAPL": _breakout_csv(Decimal("100"), Decimal("0.10"), 500000)[:-1] + _future_bar,
        "MSFT": _breakout_csv(Decimal("400"), Decimal("0.08"), 400000)[:-1] + _future_bar,
    }
    session_replay = _run_session(
        session_governance_id="RESEARCH-6803",
        artifact_path=tmp_path / "replay.json",
        config=config,
        fixtures=tampered_future_fixtures,
        universe=("AAPL", "MSFT"),
        as_of=cutoff_as_of,
        lookback_days=10,
        reference_window_size=4,
    )
    assert session_replay.status.value == "COMPLETED"  # type: ignore[attr-defined]
    assert session_replay.dataset_sha256 != early_dataset_sha  # type: ignore[attr-defined]

    # The mandatory proof: as_of-bounded research decisions are
    # semantically identical to the session that never saw the future bar
    # -- it was fetched but never consumed. Per-session derived governance
    # ids (decision_candidate_governance_id etc.) are identity fields tied
    # to each session's own runtime id and are not compared, per mission
    # Phase 10.
    def _semantic(decisions: object) -> list[tuple[object, ...]]:
        return [
            (d.rank, d.instrument_symbol, d.scan_decision, d.trade_plan_decision)
            for d in decisions  # type: ignore[attr-defined]
        ]

    assert _semantic(session_replay.decisions) == _semantic(session_early.decisions)  # type: ignore[attr-defined]


def test_partial_failure_attack_preserves_completed_stage_evidence(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """Mission Phase 19: force a failure and verify the session is
    FAILED, the failing stage is recorded, earlier completed-stage
    evidence is preserved, and no downstream stage is fabricated."""
    session = _run_session(
        session_governance_id="RESEARCH-6804",
        artifact_path=tmp_path / "artifact.json",
        config=_config(),
        universe=("AAPL", "ZZZZ"),  # ZZZZ has no fixture registered -> acquisition fails
    )
    assert session.status.value == "FAILED"  # type: ignore[attr-defined]
    assert session.failed_stage.value == "DATA_ACQUISITION"  # type: ignore[attr-defined]
    assert session.failure_type == "MarketDataAcquisitionError"  # type: ignore[attr-defined]
    stage_names = [s.stage_name.value for s in session.stage_manifest]  # type: ignore[attr-defined]
    assert stage_names == ["GOVERNANCE_SETUP", "DATA_ACQUISITION"]
    assert session.stage_manifest[0].status.value == "COMPLETED"  # type: ignore[attr-defined]
    assert session.stage_manifest[1].status.value == "FAILED"  # type: ignore[attr-defined]
    # No downstream fabrication.
    assert session.dataset_id is None  # type: ignore[attr-defined]
    assert session.scan_governance_id is None  # type: ignore[attr-defined]
    assert session.backtest_run_governance_id is None  # type: ignore[attr-defined]
    assert session.candidate_count == 0  # type: ignore[attr-defined]

    # Other session records are not corrupted: an unrelated, independent
    # session created afterward still succeeds normally.
    other = _run_session(
        session_governance_id="RESEARCH-6805",
        artifact_path=tmp_path / "other.json",
        config=_config(),
    )
    assert other.status.value == "COMPLETED"  # type: ignore[attr-defined]


def test_source_tamper_attack_rejected_before_downstream_stages(
    clean_tables: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mission Phase 20: tampering with the on-disk artifact between the
    orchestrator's own DATA_ACQUISITION stage and its DATASET_INTEGRITY_CHECK
    stage must be rejected -- the orchestrator must not bypass the frozen
    M065/M069 hash check. Per mission Phase 9, a caught exception never
    propagates raw out of `handle()`: it is turned into a FAILED session
    with the failure recorded, not a raised exception -- so this test
    tampers the artifact mid-flight (via a monkeypatch on the real M069
    acquisition handler, exercising the genuine on-disk mismatch the
    DATASET_INTEGRITY_CHECK stage is designed to catch) and asserts on the
    resulting FAILED session's own fields."""
    import empirical_platform.usecases.run_daily_research_session as run_module

    original_handle = run_module.AcquireMarketDataSnapshotHandler.handle

    def _tampering_handle(self: object, command: object) -> object:
        result = original_handle(self, command)  # type: ignore[arg-type]
        artifact_path = command.artifact_path  # type: ignore[attr-defined]
        tampered = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        # Tamper `volume` only (not open/high/low/close): this changes the
        # artifact's own bytes -- and therefore its hash -- without
        # violating the M065 OHLC bar invariant, so the tamper is caught
        # specifically by the hash comparison rather than upstream bar
        # parsing/validation.
        original_volume = tampered["instruments"][0]["bars"][0]["volume"]
        tampered["instruments"][0]["bars"][0]["volume"] = original_volume + 999999999
        Path(artifact_path).write_text(json.dumps(tampered), encoding="utf-8")
        return result

    monkeypatch.setattr(run_module.AcquireMarketDataSnapshotHandler, "handle", _tampering_handle)

    config = _config()
    session = _run_session(
        session_governance_id="RESEARCH-6807",
        artifact_path=tmp_path / "tamper_target.json",
        config=config,
        universe=("AAPL",),
        fixtures={"AAPL": _FIXTURES["AAPL"]},
    )
    assert session.status.value == "FAILED"  # type: ignore[attr-defined]
    assert session.failed_stage == "DATASET_INTEGRITY_CHECK"  # type: ignore[attr-defined]
    assert session.failure_message is not None  # type: ignore[attr-defined]
    assert "no longer matches its own declared dataset snapshot" in session.failure_message  # type: ignore[attr-defined]
    # DATA_ACQUISITION itself still completed (it wrote a genuine,
    # untampered artifact) -- only the integrity check that reads the
    # (now-tampered) bytes back off disk is the one that fails.
    stage_names = [stage.stage_name for stage in session.stage_manifest]  # type: ignore[attr-defined]
    assert "DATA_ACQUISITION" in stage_names
    assert "CANDIDATE_SCAN" not in stage_names


def test_duplicate_session_governance_id_is_rejected(clean_tables: Engine, tmp_path: Path) -> None:
    """Mission Phase 22: duplicate semantic requests must never
    accidentally overwrite previous evidence -- immutable new-identity
    semantics, an existing governance id raises rather than silently
    replacing the prior session."""
    config = _config()
    _run_session(
        session_governance_id="RESEARCH-6808",
        artifact_path=tmp_path / "a.json",
        config=config,
    )
    with pytest.raises(AggregateAlreadyExists):
        _run_session(
            session_governance_id="RESEARCH-6808",
            artifact_path=tmp_path / "b.json",
            config=config,
        )


def test_replay_semantics_same_inputs_produce_semantically_equivalent_evidence(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """Mission Phase 10: same as_of/instruments/policies/source bytes
    must produce semantically equivalent evidence under a fresh session
    identity -- identity fields are not required to match."""
    config = _config()
    first = _run_session(
        session_governance_id="RESEARCH-6809",
        artifact_path=tmp_path / "replay_a.json",
        config=config,
    )
    second = _run_session(
        session_governance_id="RESEARCH-6810",
        artifact_path=tmp_path / "replay_b.json",
        config=config,
    )
    assert first.identity != second.identity  # type: ignore[attr-defined]
    # The dataset artifact's own hashed bytes embed the session-derived
    # dataset_id (an identity field), so the two hashes legitimately
    # differ even though the underlying market-data bytes are identical --
    # per mission Phase 10, identity fields are not required to match on
    # replay, only the semantic research evidence is.
    assert len(first.dataset_sha256) == 64  # type: ignore[attr-defined]
    assert len(second.dataset_sha256) == 64  # type: ignore[attr-defined]
    assert first.candidate_count == second.candidate_count  # type: ignore[attr-defined]
    assert [d.scan_decision for d in first.decisions] == [  # type: ignore[attr-defined]
        d.scan_decision
        for d in second.decisions  # type: ignore[attr-defined]
    ]
    assert first.backtest_evaluated_opportunity_count == (  # type: ignore[attr-defined]
        second.backtest_evaluated_opportunity_count  # type: ignore[attr-defined]
    )


def test_real_cli_subprocess_run_and_get_with_real_network(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """The one CLI-subprocess test that exercises the real, installed
    `empirical-platform-run-daily-research`/`empirical-platform-get-daily-research`
    CLIs against the real network, gated behind
    EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS -- never required for canonical
    CI (mission Phase 16/17)."""
    if not _network_enabled():
        pytest.skip("real-network tests require explicit opt-in")
    config = _config()
    env = dict(os.environ)
    env["EMPIRICAL_PLATFORM_POSTGRES_HOST"] = config.host
    env["EMPIRICAL_PLATFORM_POSTGRES_PORT"] = str(config.port)
    env["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = config.database
    env["EMPIRICAL_PLATFORM_POSTGRES_USER"] = config.user
    env["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"] = config.password.get_secret_value()

    from datetime import date

    as_of_date = (date.today() - timedelta(days=2)).isoformat()
    artifact_path = tmp_path / "cli_artifact.json"

    run_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.run_daily_research_session",
            "RESEARCH-6811",
            as_of_date,
            "60",
            str(artifact_path),
            "100000",
            "0.01",
            "AAPL",
            "MSFT",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run_result.returncode == 0, run_result.stderr
    run_payload = json.loads(run_result.stdout)
    assert run_payload["FACT"]["completion_status"] == "COMPLETED"
    assert run_payload["FACT"]["data_source"] == "YAHOO_FINANCE_UNOFFICIAL_CHART_JSON"

    get_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.get_daily_research_session",
            "RESEARCH-6811",
            run_payload["FACT"]["session_runtime_id"],
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert get_result.returncode == 0, get_result.stderr
    get_payload = json.loads(get_result.stdout)
    assert get_payload["FACT"] == run_payload["FACT"]
    assert get_payload["DIAGNOSTIC"] == run_payload["DIAGNOSTIC"]
    assert get_payload["HISTORICAL_EVIDENCE"] == run_payload["HISTORICAL_EVIDENCE"]
