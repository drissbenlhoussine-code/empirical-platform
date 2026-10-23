"""PR #40/#41 deployment procedure (tools/personal_paper_deploy.py) against REAL, disposable
PostgreSQL databases and a real, harmless dummy console subprocess.

Store B and Store C are each rebuilt from the real migration chains in `migrations/` and
`migrations_paper_exit/` (never hand-fabricated), exactly like the existing M085/M089 suites.
No real Alpaca broker call is made anywhere in this file -- broker-flat verification is
exercised at the unit level against a fake (see tests/unit/test_v1_personal_paper_deploy.py);
here the focus is everything this script does to Postgres, the manifest and a real OS process.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import config, postgres_enabled
from tests.integration._m089_support import store_c_config
from tools import personal_paper_deploy as deploy

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
_PG_BIN = Path(shutil.which("pg_dump") or "").parent if shutil.which("pg_dump") else Path(".")

# `tests/conftest.py::pytest_configure` installs `install_test_connection_guard()` for the
# WHOLE session the moment EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1 is set -- unconditionally,
# before any fixture in any file runs. That guard refuses EVERY connection to a TEST-shaped
# database unless its identity COMMENT is the exact literal `EMPIRICAL:TEST`, for the entire
# process lifetime. There is therefore no way, anywhere in this suite, to make a real
# database's comment say anything `PERSONAL_PAPER:{B,C}:...`-shaped (which is exactly what a
# real production Store B/C carries, and what `read_manifest` requires a manifest's own
# `identity` field to start with). The tests below resolve this by faking ONLY the identity
# half of `deploy._identity_and_head`'s return value (see `_patch_identity_seam`) -- the HEAD
# half, and everything else these tests do, still runs against the real schema on a real,
# disposable Postgres database.


def _alembic_config_b() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def _alembic_config_c() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic_paper_exit.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations_paper_exit"))
    return cfg


def _rebuild_schema(engine: Engine, alembic_cfg: Config, revision: str) -> None:
    """The schema-building migration itself still requires the EMPIRICAL:TEST identity --
    `env.py`'s own `require_migration_connection` enforces that unconditionally for any
    online migration, independent of the optional global guard this file avoids."""
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(alembic_cfg, revision)


def _teardown_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture
def store_b(tmp_path: Path) -> Iterator[Engine]:
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    engine = sa.create_engine(config().sqlalchemy_url())
    _rebuild_schema(engine, _alembic_config_b(), deploy.MIGRATION_PRE_HEAD)
    try:
        yield engine
    finally:
        _teardown_schema(engine)


@pytest.fixture
def store_c(tmp_path: Path) -> Iterator[Engine]:
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    engine = sa.create_engine(store_c_config().sqlalchemy_url())
    _rebuild_schema(engine, _alembic_config_c(), "head")
    try:
        yield engine
    finally:
        _teardown_schema(engine)


def _fake_identity_b() -> str:
    return f"PERSONAL_PAPER:B:{uuid4().hex[:16]}"


def _fake_identity_c() -> str:
    return f"PERSONAL_PAPER:C:{uuid4().hex[:16]}"


def _patch_identity_seam(
    monkeypatch: pytest.MonkeyPatch, *, identity_b: str, identity_c: str
) -> None:
    """Fake only the identity half of `_identity_and_head`'s result; the head half is still
    fetched for real (see the module docstring note above for why)."""
    real = deploy._identity_and_head
    store_b_database = config().database

    def _fake(db_config: object) -> tuple[str, str | None]:
        _, head = real(db_config)  # type: ignore[arg-type]
        identity = identity_b if db_config.database == store_b_database else identity_c  # type: ignore[attr-defined]
        return identity, head

    monkeypatch.setattr(deploy, "_identity_and_head", _fake)


_ATTEMPT_B_INSERT_SQL = (
    "INSERT INTO public.paper_execution_attempt "
    "(attempt_id, intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, state, claimed_at, terminal_at) "
    "VALUES (:id, :id, :id, :client_order_id, "
    "'0000000000000000000000000000000000000000000000000000000000000000', "
    ":state, now(), {terminal_at})"
)
_ATTEMPT_C_INSERT_SQL = (
    "INSERT INTO public.position_exit_attempt "
    "(attempt_id, entry_intent_governance_id, authorization_id, client_order_id, "
    "request_fingerprint, symbol, quantity, state, claimed_at, terminal_at) "
    "VALUES (:id, :id, :id, :client_order_id, "
    "'0000000000000000000000000000000000000000000000000000000000000000', "
    "'AAPL', 1, :state, now(), {terminal_at})"
)


def _seed_paper_execution_attempt(
    engine: Engine, *, attempt_id: str, state: str = "FILLED"
) -> None:
    """Disables this table's own insert-time triggers for the seed only -- this suite is
    testing the DEPLOY SCRIPT's row-count/state queries, not M085's attempt/authorization
    FK-by-trigger chain, and re-creating a full, FK-satisfying preview/authorization/attempt
    chain through the real M085 write path for every seeded row would test M085 again, not
    this script."""
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE public.paper_execution_attempt DISABLE TRIGGER ALL"))
        terminal_at = "now()" if state in {"FILLED", "REJECTED", "CANCELED"} else "NULL"
        # `terminal_at` above is always one of exactly two fixed literals, never external input.
        statement = _ATTEMPT_B_INSERT_SQL.format(terminal_at=terminal_at)  # noqa: S608
        connection.execute(
            text(statement),
            {"id": attempt_id, "client_order_id": f"m085-{attempt_id}", "state": state},
        )
        connection.execute(text("ALTER TABLE public.paper_execution_attempt ENABLE TRIGGER ALL"))


def _seed_position_exit_attempt(engine: Engine, *, attempt_id: str, state: str = "FILLED") -> None:
    """See `_seed_paper_execution_attempt`'s docstring: same reasoning, Store C's table."""
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE public.position_exit_attempt DISABLE TRIGGER ALL"))
        terminal_at = "now()" if state in {"FILLED", "REJECTED", "CANCELED"} else "NULL"
        # `terminal_at` above is always one of exactly two fixed literals, never external input.
        statement = _ATTEMPT_C_INSERT_SQL.format(terminal_at=terminal_at)  # noqa: S608
        connection.execute(
            text(statement),
            {"id": attempt_id, "client_order_id": f"m087-{attempt_id}", "state": state},
        )
        connection.execute(text("ALTER TABLE public.position_exit_attempt ENABLE TRIGGER ALL"))


def _write_manifest(
    path: Path, *, identity_b: str, identity_c: str, head_b: str, attempts_b: int, attempts_c: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": "PERSONAL_PAPER",
        "version": 1,
        "state": "INITIALIZED",
        "host": config().host,
        "port": config().port,
        "stores": {
            "B": {
                "database": config().database,
                "identity": identity_b,
                "head": head_b,
                "minimum_attempts": attempts_b,
            },
            "C": {
                "database": store_c_config().database,
                "identity": identity_c,
                "head": deploy.STORE_C_HEAD,
                "minimum_attempts": attempts_c,
            },
        },
    }
    path.write_text(json.dumps(manifest))


def _deploy_config(tmp_path: Path, manifest_path: Path) -> deploy.DeployConfig:
    return deploy.DeployConfig(
        repo_path=REPO_ROOT,
        expected_release_head="unused-in-these-tests",
        manifest_path=manifest_path,
        backup_root=tmp_path / "backups",
        pg_bin=_PG_BIN,
        store_b_config=config(),
        store_c_config=store_c_config(),
        migration_sql_path=REPO_ROOT / "tools" / deploy.MIGRATION_SQL_FILENAME,
        console_host="127.0.0.1",
        console_port=18189,
        console_pid=None,
    )


# ---------------------------------------------------------------------------------------
# Steps 2, 7, 8, 9, 10 end-to-end on real, disposable Store B/C.
# ---------------------------------------------------------------------------------------


def test_full_migration_and_manifest_update_pipeline(
    store_b: Engine, store_c: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity_b, identity_c = _fake_identity_b(), _fake_identity_c()
    _patch_identity_seam(monkeypatch, identity_b=identity_b, identity_c=identity_c)
    _seed_paper_execution_attempt(store_b, attempt_id="ATT-1")
    _seed_paper_execution_attempt(store_b, attempt_id="ATT-2")
    _seed_position_exit_attempt(store_c, attempt_id="XAT-1")

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        identity_b=identity_b,
        identity_c=identity_c,
        head_b=deploy.MIGRATION_PRE_HEAD,
        attempts_b=2,
        attempts_c=1,
    )
    cfg = _deploy_config(tmp_path, manifest_path)

    assert "no non-terminal" in deploy.step2_no_inflight(cfg)

    detail = deploy.step7_migrate(cfg)
    assert "applied via psql" in detail
    identity, head = deploy._identity_and_head(cfg.store_b_config)
    assert identity == identity_b
    assert head == deploy.MIGRATION_POST_HEAD

    assert "4 columns + 2 constraints + guard clause" in deploy.step8_verify_schema(cfg)
    assert "both unchanged vs. the backup baseline" in deploy.step9_verify_unchanged(cfg)

    manifest_detail = deploy.step10_manifest_update(
        cfg,
        release_head="deadbeef",
        backup_location=tmp_path / "backups" / "fake-set",
        migration_sql_sha256=deploy.MIGRATION_SQL_SHA256,
        now=datetime(2026, 10, 21, tzinfo=UTC),
    )
    assert "pre-change copy preserved" in manifest_detail
    updated = json.loads(manifest_path.read_text())
    assert updated["stores"]["B"]["head"] == deploy.MIGRATION_POST_HEAD
    assert updated["last_migration"]["revision"] == deploy.MIGRATION_POST_HEAD

    # Store C was never touched by any of this.
    _, store_c_head = deploy._identity_and_head(cfg.store_c_config)
    assert store_c_head == deploy.STORE_C_HEAD


def test_step7_is_idempotent_when_already_migrated(
    store_b: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity_b = _fake_identity_b()
    _patch_identity_seam(monkeypatch, identity_b=identity_b, identity_c=_fake_identity_c())
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        identity_b=identity_b,
        identity_c="PERSONAL_PAPER:C:x",
        head_b=deploy.MIGRATION_PRE_HEAD,
        attempts_b=0,
        attempts_c=0,
    )
    cfg = _deploy_config(tmp_path, manifest_path)

    deploy.step7_migrate(cfg)
    second_detail = deploy.step7_migrate(cfg)
    assert "idempotent" in second_detail


def test_step7_refuses_on_wrong_database_identity(
    store_b: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The REAL identity the deploy script will observe (faked at the seam, see module
    # docstring) is "the-real-one"; the manifest below claims a DIFFERENT identity entirely.
    _patch_identity_seam(
        monkeypatch, identity_b="PERSONAL_PAPER:B:the-real-one", identity_c=_fake_identity_c()
    )
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        identity_b="PERSONAL_PAPER:B:this-does-not-match-the-real-database",
        identity_c="PERSONAL_PAPER:C:x",
        head_b=deploy.MIGRATION_PRE_HEAD,
        attempts_b=0,
        attempts_c=0,
    )
    cfg = _deploy_config(tmp_path, manifest_path)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step7_migrate(cfg)
    assert excinfo.value.step == deploy.STEP_7_MIGRATE
    assert "identity mismatch" in excinfo.value.reason
    _, head = deploy._identity_and_head(cfg.store_b_config)
    assert head == deploy.MIGRATION_PRE_HEAD  # refused BEFORE touching anything


def test_step2_detects_a_non_terminal_execution_attempt(
    store_b: Engine, store_c: Engine, tmp_path: Path
) -> None:
    _seed_paper_execution_attempt(store_b, attempt_id="ATT-STUCK", state="PAPER_SUBMITTED")
    cfg = _deploy_config(tmp_path, tmp_path / "manifest.json")
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step2_no_inflight(cfg)
    assert excinfo.value.step == deploy.STEP_2_NO_INFLIGHT
    assert "ATT-STUCK" in excinfo.value.reason


def test_step9_detects_a_historical_row_that_appeared_after_the_backup_baseline(
    store_b: Engine, store_c: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity_b, identity_c = _fake_identity_b(), _fake_identity_c()
    _patch_identity_seam(monkeypatch, identity_b=identity_b, identity_c=identity_c)
    _seed_paper_execution_attempt(store_b, attempt_id="ATT-1")
    manifest_path = tmp_path / "manifest.json"
    # Baseline claims only 0 attempts existed at backup time -- but 1 already does, simulating
    # a write that slipped through between the backup and the migration.
    _write_manifest(
        manifest_path,
        identity_b=identity_b,
        identity_c=identity_c,
        head_b=deploy.MIGRATION_PRE_HEAD,
        attempts_b=0,
        attempts_c=0,
    )
    cfg = _deploy_config(tmp_path, manifest_path)
    deploy.step7_migrate(cfg)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step9_verify_unchanged(cfg)
    assert excinfo.value.step == deploy.STEP_9_VERIFY_UNCHANGED
    assert "changed" in excinfo.value.reason


def test_resume_after_a_simulated_crash_between_migration_and_manifest_update(
    store_b: Engine, store_c: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact 'after migration but before manifest update' Phase 3 boundary: migration
    (7-9) completed in one simulated process; a FRESH call for step 10 alone -- as a real
    resumed run would make, re-deriving the backup location from disk -- must succeed."""
    identity_b, identity_c = _fake_identity_b(), _fake_identity_c()
    _patch_identity_seam(monkeypatch, identity_b=identity_b, identity_c=identity_c)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        identity_b=identity_b,
        identity_c=identity_c,
        head_b=deploy.MIGRATION_PRE_HEAD,
        attempts_b=0,
        attempts_c=0,
    )
    cfg = _deploy_config(tmp_path, manifest_path)

    deploy.step7_migrate(cfg)
    deploy.step8_verify_schema(cfg)
    deploy.step9_verify_unchanged(cfg)
    # "Crash" here: nothing in this process's memory survives. A fresh backup root with a
    # fabricated complete backup directory stands in for what step 4 would have left behind.
    backup_dir = cfg.backup_root / "20261021T120000000000Z-resumetest"
    backup_dir.mkdir(parents=True)
    (backup_dir / "complete.json").write_text("{}")

    rederived = deploy._latest_complete_backup(cfg.backup_root)
    assert rederived == backup_dir

    detail = deploy.step10_manifest_update(
        cfg,
        release_head="resumed-head",
        backup_location=rederived,
        migration_sql_sha256=deploy.MIGRATION_SQL_SHA256,
        now=datetime(2026, 10, 21, tzinfo=UTC),
    )
    assert "pre-change copy preserved" in detail
    updated = json.loads(manifest_path.read_text())
    assert updated["last_migration"]["backup_location"] == str(backup_dir)


# ---------------------------------------------------------------------------------------
# Step 11: the code-vs-schema safety gate, against the REAL migrations/ directory, both
# matching and deliberately mismatched.
# ---------------------------------------------------------------------------------------


def test_find_chain_head_on_the_real_migrations_directory_matches_the_pinned_constant() -> None:
    assert (
        deploy._find_chain_head(REPO_ROOT / "migrations" / "versions") == deploy.MIGRATION_POST_HEAD
    )
    assert (
        deploy._find_chain_head(REPO_ROOT / "migrations_paper_exit" / "versions")
        == deploy.STORE_C_HEAD
    )


def test_step11_refuses_when_worktree_chain_head_is_behind_the_live_schema(
    store_b: Engine, store_c: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates OLD code (checked out before the migration) against an ALREADY-migrated
    live schema -- the exact hazard step 11 exists to catch."""
    identity_b, identity_c = _fake_identity_b(), _fake_identity_c()
    _patch_identity_seam(monkeypatch, identity_b=identity_b, identity_c=identity_c)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        identity_b=identity_b,
        identity_c=identity_c,
        head_b=deploy.MIGRATION_PRE_HEAD,
        attempts_b=0,
        attempts_c=0,
    )
    cfg_for_migration = _deploy_config(tmp_path, manifest_path)
    deploy.step7_migrate(cfg_for_migration)  # live schema is now at the POST head

    old_repo = tmp_path / "old-worktree"
    shutil.copytree(REPO_ROOT / "migrations", old_repo / "migrations")
    shutil.copytree(REPO_ROOT / "migrations_paper_exit", old_repo / "migrations_paper_exit")
    (
        old_repo
        / "migrations"
        / "versions"
        / (deploy.MIGRATION_POST_HEAD + "_add_v1_approved_plan_trigger_evidence.py")
    ).unlink()

    def _git_test_setup(*args: str) -> str:
        result = subprocess.run(  # noqa: S603 - fixed executable, explicit vector
            ["git", "-C", str(old_repo), *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    subprocess.run(  # noqa: S603 - fixed executable, explicit vector
        ["git", "init", "-q", str(old_repo)],  # noqa: S607
        check=True,
    )
    _git_test_setup("config", "user.email", "t@example.com")
    _git_test_setup("config", "user.name", "t")
    _git_test_setup("add", ".")
    _git_test_setup("commit", "-q", "-m", "old")
    _git_test_setup("checkout", "-q", "-b", "release/v1-personal-paper")
    # A self-remote: step 11 always fetches+ff-merges "origin" before comparing schema
    # heads. There is nothing to actually pull (this IS the tip), so this makes that step a
    # trivial no-op and lets the test reach the schema-head comparison it's actually about.
    _git_test_setup("remote", "add", "origin", str(old_repo))
    head = _git_test_setup("rev-parse", "HEAD")

    cfg = deploy.DeployConfig(
        repo_path=old_repo,
        expected_release_head=head,
        manifest_path=manifest_path,
        backup_root=tmp_path / "backups",
        pg_bin=_PG_BIN,
        store_b_config=config(),
        store_c_config=store_c_config(),
        migration_sql_path=REPO_ROOT / "tools" / deploy.MIGRATION_SQL_FILENAME,
        console_host="127.0.0.1",
        console_port=18189,
        console_pid=None,
    )
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step11_fast_forward(cfg)
    assert excinfo.value.step == deploy.STEP_11_FAST_FORWARD
    assert "mismatched schema" in excinfo.value.reason


# ---------------------------------------------------------------------------------------
# Steps 5/6/12/13: real OS process + real TCP port mechanics, against a tiny, harmless
# dummy "console" this test fully controls -- never the real operator console.
# ---------------------------------------------------------------------------------------

_DUMMY_CONSOLE_SCRIPT = """
import http.server, signal, sys, socketserver

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<p>dummy console OK</p>"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

def _graceful_exit(signum, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, _graceful_exit)
if hasattr(signal, "SIGBREAK"):
    signal.signal(signal.SIGBREAK, _graceful_exit)

class _Server(socketserver.TCPServer):
    allow_reuse_address = True

with _Server(("127.0.0.1", int(sys.argv[1])), Handler) as server:
    server.serve_forever(poll_interval=0.1)
"""


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_real_shutdown_then_real_recovery_start_against_a_dummy_console(tmp_path: Path) -> None:
    """Pure OS process/TCP port mechanics -- deliberately needs no Postgres opt-in at all,
    so this test runs in the repository-wide `pytest` too, not just this file's own isolated
    Postgres job. The Store B/C configs below are never connected to; they are placeholders
    `DeployConfig` requires but this test's steps (5/6/12) never read."""
    script_path = tmp_path / "dummy_console.py"
    script_path.write_text(_DUMMY_CONSOLE_SCRIPT)
    port = _free_tcp_port()

    process_port = deploy.RealProcessPort()
    network_port = deploy.RealNetworkPort()
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(  # noqa: S603 - fixed interpreter, fixed script this test wrote
        [sys.executable, str(script_path), str(port)], creationflags=creationflags
    )
    # This test IS the dummy console's real OS parent, which real production is not (the
    # deploy script discovers an already-running console's PID; it never forks it). On POSIX,
    # an exited-but-unreaped child is a zombie that still answers `kill(pid, 0)` successfully
    # until its parent calls wait() -- which would make `is_running()` see it as running
    # forever. A background reaper thread, not a `RealProcessPort` change, is the right fix:
    # it's this TEST's parent/child relationship causing the artifact, not the port's logic.
    threading.Thread(target=process.wait, daemon=True).start()
    placeholder_db_config = PostgreSQLConfigSnapshot(
        host="localhost", port=55555, database="placeholder_test", user="empirical"
    )
    cfg = deploy.DeployConfig(
        repo_path=REPO_ROOT,
        expected_release_head="unused",
        manifest_path=tmp_path / "manifest.json",
        backup_root=tmp_path,
        pg_bin=_PG_BIN,
        store_b_config=placeholder_db_config,
        store_c_config=placeholder_db_config,
        migration_sql_path=REPO_ROOT / "tools" / deploy.MIGRATION_SQL_FILENAME,
        console_host="127.0.0.1",
        console_port=port,
        console_pid=process.pid,
        shutdown_timeout_seconds=10.0,
        startup_timeout_seconds=10.0,
    )
    ports = deploy.Ports(broker=None, process=process_port, network=network_port)  # type: ignore[arg-type]

    deploy.wait_until(
        lambda: not network_port.port_is_free(cfg.console_host, port), timeout_seconds=5.0
    )
    status, body = network_port.http_get(f"http://127.0.0.1:{port}/", timeout=5.0)
    assert status == 200 and "dummy console OK" in body

    shutdown_detail = deploy.step5_shutdown(cfg, ports)
    assert "exited gracefully" in shutdown_detail
    verify_detail = deploy.step6_verify_stopped(cfg, ports)
    assert "free" in verify_detail
    assert network_port.port_is_free(cfg.console_host, port)

    launch_detail, pid = deploy.step12_recovery_start(
        cfg,
        ports,
        executable=(sys.executable, str(script_path), str(port)),
        env=dict(os.environ),
        log_path=tmp_path / "recovery-console.log",
    )
    assert "listening" in launch_detail
    try:
        status, body = network_port.http_get(f"http://127.0.0.1:{port}/", timeout=5.0)
        assert status == 200
    finally:
        process_port.graceful_stop(pid)
        deploy.wait_until(lambda: not process_port.is_running(pid), timeout_seconds=5.0)
