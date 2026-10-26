"""Unit coverage for the PR #40/#41 deployment procedure (tools/personal_paper_deploy.py).

Everything here runs against fakes or disposable tmp_path fixtures -- no real broker, no real
console process, no real Postgres. Real-Postgres coverage of the migration-apply/schema/
manifest/row-preservation steps lives in
tests/integration/test_v1_personal_paper_deploy_postgres.py.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tools import personal_paper_deploy as deploy

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.database_safety import DatabaseSafetyError

# ---------------------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------------------


class _FakeBroker:
    def __init__(self, snapshot: deploy.BrokerSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    def account_snapshot(self) -> deploy.BrokerSnapshot:
        self.calls += 1
        return self.snapshot


_FLAT_SNAPSHOT = deploy.BrokerSnapshot(
    account_status="ACTIVE",
    trading_blocked=False,
    position_count=0,
    open_order_count=0,
    unknown_order_count=0,
)


class _FakeProcess:
    def __init__(self) -> None:
        self.running: dict[int, bool] = {}
        self.graceful_stop_calls: list[int] = []
        self.started: list[tuple[tuple[str, ...], Path]] = []
        self.next_pid = 999

    def is_running(self, pid: int) -> bool:
        return self.running.get(pid, False)

    def graceful_stop(self, pid: int, *, host: str, port: int, safety_directory: Path) -> None:
        del host, port, safety_directory
        self.graceful_stop_calls.append(pid)
        self.running[pid] = False

    def start_recovery_console(
        self, *, executable: tuple[str, ...], env: dict[str, str], log_path: Path
    ) -> int:
        del env
        self.started.append((tuple(executable), log_path))
        pid = self.next_pid
        self.running[pid] = True
        return pid


class _FakeNetwork:
    def __init__(self) -> None:
        self.free_ports: set[int] = set()
        self.owners: dict[int, int] = {}  # port -> the PID "really" listening on it
        self.owning_pid_errors: dict[int, str] = {}  # port -> error message to raise instead
        # MILESTONE-098: a per-port queue of successive `owning_pid` answers, consumed one
        # call at a time, for tests that need `step5_shutdown`'s discovery call and its later
        # re-confirmation call to disagree (a PID/port race). Falls back to `owners` once
        # exhausted (or if never set), so every pre-existing test is unaffected.
        self.owning_pid_sequence: dict[int, list[int | None]] = {}
        # M098-R: a port that refuses connections normally has no listener at all; a test can
        # plant one here to model a listener the connect probe misses (step 6 must refuse it).
        self.stale_listeners: dict[int, int] = {}
        self.responses: dict[str, tuple[int, str]] = {}
        self.http_calls: list[str] = []

    def port_is_free(self, host: str, port: int) -> bool:
        del host
        return port in self.free_ports

    def owning_pid(self, host: str, port: int) -> int | None:
        del host
        if port in self.owning_pid_errors:
            raise RuntimeError(self.owning_pid_errors[port])
        sequence = self.owning_pid_sequence.get(port)
        if sequence:
            return sequence.pop(0)
        if port in self.free_ports:
            return self.stale_listeners.get(port)
        return self.owners.get(port)

    def http_get(self, url: str, *, timeout: float) -> tuple[int, str]:
        del timeout
        self.http_calls.append(url)
        return self.responses.get(url, (404, ""))


def _ports(broker: _FakeBroker, process: _FakeProcess, network: _FakeNetwork) -> deploy.Ports:
    return deploy.Ports(broker=broker, process=process, network=network)


# ---------------------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------------------


def test_journal_round_trips_through_json(tmp_path: Path) -> None:
    journal = deploy.DeploymentJournal()
    now = datetime(2026, 10, 21, tzinfo=UTC)
    journal.append(deploy.STEP_1_BROKER_VERIFY, "started", "", now=now)
    journal.append(deploy.STEP_1_BROKER_VERIFY, "completed", "flat", now=now)
    path = tmp_path / "journal.json"
    journal.save(path)

    reloaded = deploy.DeploymentJournal.load_or_new(path)
    assert reloaded.completed_steps() == {deploy.STEP_1_BROKER_VERIFY}
    assert reloaded.last() == deploy.StepRecord(
        deploy.STEP_1_BROKER_VERIFY, "completed", now.isoformat(), "flat"
    )


def test_journal_load_or_new_returns_empty_for_missing_file(tmp_path: Path) -> None:
    journal = deploy.DeploymentJournal.load_or_new(tmp_path / "missing.json")
    assert journal.records == []
    assert journal.completed_steps() == set()


def test_journal_save_is_atomic_no_tmp_file_left_behind(tmp_path: Path) -> None:
    path = tmp_path / "journal.json"
    journal = deploy.DeploymentJournal()
    journal.append(deploy.STEP_1_BROKER_VERIFY, "completed", "ok", now=datetime.now(UTC))
    journal.save(path)
    assert path.exists()
    assert not path.with_name(path.name + ".tmp").exists()


# ---------------------------------------------------------------------------------------
# Recovery instructions: every step has accurate, non-generic guidance; migration-related
# steps explicitly warn against downgrade/restore without separate Owner authorization.
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("step", deploy.STEP_ORDER)
def test_every_step_has_specific_recovery_guidance(step: str) -> None:
    message = deploy.recovery_instructions_for(step, "some concrete reason")
    assert step in message
    assert "some concrete reason" in message
    assert message != deploy.recovery_instructions_for("NOT_A_REAL_STEP", "some concrete reason")


@pytest.mark.parametrize(
    "step",
    [deploy.STEP_7_MIGRATE, deploy.STEP_8_VERIFY_SCHEMA, deploy.STEP_9_VERIFY_UNCHANGED],
)
def test_migration_steps_warn_against_unauthorized_rollback(step: str) -> None:
    """Steps where the SCHEMA state itself could be in doubt must never suggest an
    unauthorized downgrade/restore. Step 10 (bookkeeping only, schema already migrated
    successfully by the time it runs) legitimately has different, less drastic guidance."""
    message = deploy.recovery_instructions_for(step, "reason")
    assert "Owner authorization" in message or "Owner-authorized" in message
    assert "NOT" in message  # "do NOT downgrade" / "do NOT restore" / "do NOT update"


def test_deployment_blocked_error_message_matches_recovery_instructions() -> None:
    error = deploy.DeploymentBlockedError(deploy.STEP_1_BROKER_VERIFY, "broker not flat")
    assert str(error) == deploy.recovery_instructions_for(
        deploy.STEP_1_BROKER_VERIFY, "broker not flat"
    )
    assert error.step == deploy.STEP_1_BROKER_VERIFY
    assert error.reason == "broker not flat"


# ---------------------------------------------------------------------------------------
# Step 1: broker verification. Read-only by construction -- BrokerPort has exactly one
# method and it is a GET-shaped snapshot, never an order action.
# ---------------------------------------------------------------------------------------


def test_step1_passes_when_broker_is_flat() -> None:
    broker = _FakeBroker(_FLAT_SNAPSHOT)
    ports = _ports(broker, _FakeProcess(), _FakeNetwork())
    detail = deploy.step1_broker_verify(deploy_config_stub(), ports)
    assert "positions=0" in detail
    assert broker.calls == 1


@pytest.mark.parametrize(
    "snapshot",
    [
        deploy.BrokerSnapshot(
            "ACTIVE", False, position_count=1, open_order_count=0, unknown_order_count=0
        ),
        deploy.BrokerSnapshot(
            "ACTIVE", False, position_count=0, open_order_count=1, unknown_order_count=0
        ),
        deploy.BrokerSnapshot(
            "ACTIVE", False, position_count=0, open_order_count=0, unknown_order_count=1
        ),
        deploy.BrokerSnapshot(
            "ACTIVE", True, position_count=0, open_order_count=0, unknown_order_count=0
        ),
        deploy.BrokerSnapshot(
            "ACCOUNT_RESTRICTED", False, position_count=0, open_order_count=0, unknown_order_count=0
        ),
    ],
)
def test_step1_refuses_any_non_flat_or_blocked_account(snapshot: deploy.BrokerSnapshot) -> None:
    ports = _ports(_FakeBroker(snapshot), _FakeProcess(), _FakeNetwork())
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step1_broker_verify(deploy_config_stub(), ports)
    assert excinfo.value.step == deploy.STEP_1_BROKER_VERIFY


def test_broker_port_has_no_order_submitting_method() -> None:
    """Structural guarantee: nothing on BrokerPort can place, close or cancel an order."""
    methods = {name for name in dir(deploy.BrokerPort) if not name.startswith("_")}
    assert methods == {"account_snapshot"}
    for forbidden in ("submit", "cancel", "close", "buy", "sell"):
        assert forbidden not in " ".join(methods).lower()


# ---------------------------------------------------------------------------------------
# Step 3: release head / clean worktree, against a real disposable git repo.
# ---------------------------------------------------------------------------------------


def _init_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True)  # noqa: S603, S607
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@example.com"], check=True)  # noqa: S603, S607
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)  # noqa: S603, S607
    (path / "f.txt").write_text("hello")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)  # noqa: S603, S607
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)  # noqa: S603, S607
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(path), "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_step3_passes_on_clean_worktree_at_expected_head(tmp_path: Path) -> None:
    head = _init_repo(tmp_path)
    cfg = deploy_config_stub(repo_path=tmp_path, expected_release_head=head)
    detail = deploy.step3_release_head(cfg)
    assert head in detail


def test_step3_refuses_dirty_worktree(tmp_path: Path) -> None:
    head = _init_repo(tmp_path)
    (tmp_path / "f.txt").write_text("modified, uncommitted")
    cfg = deploy_config_stub(repo_path=tmp_path, expected_release_head=head)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step3_release_head(cfg)
    assert excinfo.value.step == deploy.STEP_3_RELEASE_HEAD


def test_step3_refuses_wrong_head(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    cfg = deploy_config_stub(repo_path=tmp_path, expected_release_head="0" * 40)
    with pytest.raises(deploy.DeploymentBlockedError):
        deploy.step3_release_head(cfg)


# ---------------------------------------------------------------------------------------
# Steps 5/6: graceful shutdown + verification, against fakes.
# ---------------------------------------------------------------------------------------


def test_step5_and_6_succeed_when_owning_pid_matches_and_process_stops(tmp_path: Path) -> None:
    process = _FakeProcess()
    process.running[4242] = True
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=4242, backup_root=tmp_path, shutdown_timeout_seconds=1.0)
    network.owners[cfg.console_port] = 4242
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)

    detail = deploy.step5_shutdown(cfg, ports)
    assert 4242 in process.graceful_stop_calls
    assert "exited gracefully" in detail

    network.free_ports.add(cfg.console_port)
    detail = deploy.step6_verify_stopped(cfg, ports)
    assert "free" in detail


def test_step5_times_out_if_process_never_stops(tmp_path: Path) -> None:
    class _StubbornProcess(_FakeProcess):
        def graceful_stop(self, pid: int, *, host: str, port: int, safety_directory: Path) -> None:
            pass  # deliberately never actually stops

    process = _StubbornProcess()
    process.running[4242] = True
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=4242, backup_root=tmp_path, shutdown_timeout_seconds=0.3)
    network.owners[cfg.console_port] = 4242
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN


def test_step5_is_idempotent_when_port_already_free(tmp_path: Path) -> None:
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path)
    network = _FakeNetwork()
    network.free_ports.add(cfg.console_port)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), network)
    detail = deploy.step5_shutdown(cfg, ports)
    assert "already free" in detail


def test_step5_refuses_when_given_pid_is_running_but_port_is_free(tmp_path: Path) -> None:
    """A stale/incorrect `--console-pid`: the port is free (nothing of ours is listening)
    but the given PID happens to still be running something else. Refuses rather than
    silently treating this as "nothing to stop"."""
    process = _FakeProcess()
    process.running[4242] = True
    cfg = deploy_config_stub(console_pid=4242, backup_root=tmp_path)
    network = _FakeNetwork()
    network.free_ports.add(cfg.console_port)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert not process.graceful_stop_calls


def test_step5_refuses_when_owning_pid_cannot_be_determined(tmp_path: Path) -> None:
    """The port is occupied but the OS-level query could not identify who owns it. This
    must never be treated the same as "confirmed free"."""
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), _FakeNetwork())
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "could not be determined" in excinfo.value.reason


def test_step5_propagates_an_owning_pid_query_failure(tmp_path: Path) -> None:
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path)
    network = _FakeNetwork()
    network.owning_pid_errors[cfg.console_port] = "netstat failed"
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), network)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "netstat failed" in excinfo.value.reason


def test_step5_refuses_when_console_pid_does_not_match_the_actual_owner(tmp_path: Path) -> None:
    """Rejects PID reuse / an incorrect `--console-pid`: the process actually listening on
    the port is a DIFFERENT PID than the one given. Nothing is signalled."""
    process = _FakeProcess()
    process.running[4242] = True
    process.running[9999] = True
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=4242, backup_root=tmp_path)
    network.owners[cfg.console_port] = 9999  # the REAL owner is a different PID
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "does not match" in excinfo.value.reason
    assert not process.graceful_stop_calls


def test_step5_auto_discovers_the_pid_when_console_pid_is_not_given(tmp_path: Path) -> None:
    process = _FakeProcess()
    process.running[4242] = True
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path, shutdown_timeout_seconds=1.0)
    network.owners[cfg.console_port] = 4242
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)
    detail = deploy.step5_shutdown(cfg, ports)
    assert process.graceful_stop_calls == [4242]
    assert "4242" in detail


def test_step5_wraps_a_console_shutdown_error_as_deployment_blocked(tmp_path: Path) -> None:
    class _RefusingProcess(_FakeProcess):
        def graceful_stop(self, pid: int, *, host: str, port: int, safety_directory: Path) -> None:
            del host, port, safety_directory
            raise deploy.ConsoleShutdownError("control token capability mismatch")

    process = _RefusingProcess()
    process.running[4242] = True
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=4242, backup_root=tmp_path)
    network.owners[cfg.console_port] = 4242
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "control token capability mismatch" in excinfo.value.reason


def test_step5_detects_a_pid_port_race_between_discovery_and_shutdown(tmp_path: Path) -> None:
    """MILESTONE-098 SECURITY HARDENING: the owning PID is re-confirmed immediately before
    acting, not trusted from discovery alone. If the OS reused the port for a different
    process in between (simulated here via a two-answer sequence), this refuses rather than
    signal either process."""
    process = _FakeProcess()
    process.running[4242] = True
    process.running[9999] = True
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path)
    network.owning_pid_sequence[cfg.console_port] = [4242, 9999]
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "race" in excinfo.value.reason
    assert not process.graceful_stop_calls


def test_step5_propagates_a_query_failure_during_the_race_reconfirmation(tmp_path: Path) -> None:
    """The second (reconfirmation) `owning_pid` query can itself fail at the OS level, just
    as the first can -- this must be treated the same way, never as a silent "unchanged"."""
    process = _FakeProcess()
    process.running[4242] = True
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path)
    network.owners[cfg.console_port] = 4242
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)

    real_owning_pid = network.owning_pid
    calls = {"count": 0}

    def _flaky_owning_pid(host: str, port: int) -> int | None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("netstat failed on reconfirmation")
        return real_owning_pid(host, port)

    network.owning_pid = _flaky_owning_pid  # type: ignore[method-assign]
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "netstat failed on reconfirmation" in excinfo.value.reason
    assert not process.graceful_stop_calls


def test_step6_refuses_if_backup_lock_still_held(tmp_path: Path) -> None:
    (tmp_path / ".backup.lock").write_text("")
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path)
    network.free_ports.add(cfg.console_port)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), network)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step6_verify_stopped(cfg, ports)
    assert excinfo.value.step == deploy.STEP_6_VERIFY_STOPPED


def test_step6_refuses_if_port_still_occupied(tmp_path: Path) -> None:
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), _FakeNetwork())  # no free ports
    with pytest.raises(deploy.DeploymentBlockedError):
        deploy.step6_verify_stopped(cfg, ports)


def test_step6_refuses_a_listener_the_connect_probe_missed(tmp_path: Path) -> None:
    """M098-R: a refused connection is not proof the console released its port; the OS
    listener table must show nobody listening before migrations may run."""
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path)
    network.free_ports.add(cfg.console_port)
    network.stale_listeners[cfg.console_port] = 4242
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), network)
    with pytest.raises(
        deploy.DeploymentBlockedError, match="PID 4242 is still listening"
    ) as excinfo:
        deploy.step6_verify_stopped(cfg, ports)
    assert excinfo.value.step == deploy.STEP_6_VERIFY_STOPPED


def test_step6_refuses_when_the_listener_table_cannot_be_read(tmp_path: Path) -> None:
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=None, backup_root=tmp_path)
    network.free_ports.add(cfg.console_port)
    network.owning_pid_errors[cfg.console_port] = "listener table unavailable"
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), network)
    with pytest.raises(deploy.DeploymentBlockedError, match="could not confirm port"):
        deploy.step6_verify_stopped(cfg, ports)


def test_an_unverified_shutdown_never_reaches_migration_manifest_fast_forward_or_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M098-R: the REAL step 5 and step 6 run (against fakes); the console is reported
    stopped, but a listener is still on its port. Step 6 must block, and nothing after it --
    migration, schema checks, manifest update, fast-forward, recovery start -- may run."""
    for fn_name in _STEP_FUNCTION_NAMES[:4]:
        step_name = deploy.STEP_ORDER[_STEP_FUNCTION_NAMES.index(fn_name)]
        result: object = ("ok", tmp_path) if step_name == deploy.STEP_4_BACKUP else "ok"
        monkeypatch.setattr(deploy, fn_name, lambda *_a, _r=result, **_k: _r)
    reached: list[str] = []
    for fn_name in _STEP_FUNCTION_NAMES[6:]:
        monkeypatch.setattr(deploy, fn_name, lambda *_a, _n=fn_name, **_k: reached.append(_n))
    process = _FakeProcess()
    process.running[4242] = True
    network = _FakeNetwork()
    cfg = deploy_config_stub(console_pid=4242, backup_root=tmp_path, shutdown_timeout_seconds=1.0)
    network.owners[cfg.console_port] = 4242
    original_stop = process.graceful_stop

    def _stop_but_leave_a_listener(pid: int, **kwargs: object) -> None:
        original_stop(pid, **kwargs)  # type: ignore[arg-type]
        network.free_ports.add(cfg.console_port)
        network.stale_listeners[cfg.console_port] = 5151

    process.graceful_stop = _stop_but_leave_a_listener  # type: ignore[method-assign]
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)
    journal_path = tmp_path / "journal.json"
    launch = deploy.RecoveryConsoleLaunch(executable=("x",), env={}, log_path=journal_path)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.run_deployment(
            cfg,
            ports,
            deploy.DeploymentJournal.load_or_new(journal_path),
            journal_path,
            launch=launch,
        )
    assert excinfo.value.step == deploy.STEP_6_VERIFY_STOPPED
    assert reached == []
    reloaded = deploy.DeploymentJournal.load_or_new(journal_path)
    assert deploy.STEP_5_SHUTDOWN in reloaded.completed_steps()
    assert reloaded.last().step == deploy.STEP_6_VERIFY_STOPPED  # type: ignore[union-attr]
    assert reloaded.last().status == "failed"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------------------
# Steps 12/13: recovery-mode startup + verification, against fakes.
# ---------------------------------------------------------------------------------------


_RECOVERY_SAFETY_BODY = (
    "<section><h2>Automatic position manager</h2><p>NOT RUNNING: recovery mode</p></section>"
)
_ACTIVE_SAFETY_BODY = (
    "<p class='muted'>running: 5654 tick(s) completed, most recently 1s ago</p>"
    "<strong>HEALTHY</strong>"
)
_FLAT_HEALTH_BODY = "<dl><dt>Current position (shares)</dt><dd>0</dd></dl>"
_NONFLAT_HEALTH_BODY = "<dl><dt>Current position (shares)</dt><dd>1</dd></dl>"


def test_step12_starts_console_and_waits_for_port(tmp_path: Path) -> None:
    process = _FakeProcess()
    network = _FakeNetwork()
    cfg = deploy_config_stub(backup_root=tmp_path, startup_timeout_seconds=1.0)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)
    launch = deploy.RecoveryConsoleLaunch(
        executable=("python", "-m", "fake"), env={}, log_path=tmp_path / "log.txt"
    )

    network.free_ports.add(cfg.console_port)
    # Flip "occupied" only after start is requested, simulating a real startup delay.
    original_start = process.start_recovery_console

    def _start_and_occupy(**kwargs: object) -> int:
        pid = original_start(**kwargs)  # type: ignore[arg-type]
        network.free_ports.discard(cfg.console_port)
        return pid

    process.start_recovery_console = _start_and_occupy  # type: ignore[method-assign]
    detail, pid = deploy.step12_recovery_start(
        cfg, ports, executable=launch.executable, env=launch.env, log_path=launch.log_path
    )
    assert pid == 999
    assert process.started[0][0] == ("python", "-m", "fake")
    assert "listening" in detail


def test_step12_refuses_if_port_already_occupied_before_start(tmp_path: Path) -> None:
    cfg = deploy_config_stub(backup_root=tmp_path)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), _FakeNetwork())  # no free ports
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step12_recovery_start(
            cfg, ports, executable=("x",), env={}, log_path=tmp_path / "log.txt"
        )
    assert excinfo.value.step == deploy.STEP_12_RECOVERY_START


def test_step12_times_out_if_port_never_opens(tmp_path: Path) -> None:
    process = _FakeProcess()
    network = _FakeNetwork()
    network.free_ports.add(8189)
    cfg = deploy_config_stub(backup_root=tmp_path, startup_timeout_seconds=0.3)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), process, network)
    with pytest.raises(deploy.DeploymentBlockedError):
        deploy.step12_recovery_start(
            cfg, ports, executable=("x",), env={}, log_path=tmp_path / "log.txt"
        )


def test_step13_passes_when_recovery_mode_and_flat_and_matching_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = deploy_config_stub(backup_root=tmp_path, manifest_path=tmp_path / "manifest.json")
    network = _FakeNetwork()
    base = f"http://{cfg.console_host}:{cfg.console_port}"
    network.responses[f"{base}/safety"] = (200, _RECOVERY_SAFETY_BODY)
    network.responses[f"{base}/health"] = (200, _FLAT_HEALTH_BODY)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), network)
    _write_manifest(cfg.manifest_path, head="f3a7c9e2b164")
    monkeypatch.setattr(
        deploy, "_identity_and_head", lambda config: ("PERSONAL_PAPER:B:tok", "f3a7c9e2b164")
    )
    detail = deploy.step13_verify_startup(cfg, ports)
    assert "recovery-mode console verified" in detail


def test_step13_refuses_if_automatic_manager_is_running(tmp_path: Path) -> None:
    cfg = deploy_config_stub(backup_root=tmp_path)
    network = _FakeNetwork()
    base = f"http://{cfg.console_host}:{cfg.console_port}"
    network.responses[f"{base}/safety"] = (200, _ACTIVE_SAFETY_BODY)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), network)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step13_verify_startup(cfg, ports)
    assert excinfo.value.step == deploy.STEP_13_VERIFY_STARTUP
    assert "recovery mode" in excinfo.value.reason


def test_step13_refuses_if_broker_not_flat(tmp_path: Path) -> None:
    cfg = deploy_config_stub(backup_root=tmp_path)
    network = _FakeNetwork()
    base = f"http://{cfg.console_host}:{cfg.console_port}"
    network.responses[f"{base}/safety"] = (200, _RECOVERY_SAFETY_BODY)
    network.responses[f"{base}/health"] = (200, _NONFLAT_HEALTH_BODY)
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), network)
    with pytest.raises(deploy.DeploymentBlockedError):
        deploy.step13_verify_startup(cfg, ports)


# ---------------------------------------------------------------------------------------
# Step 10: manifest atomic update, against a real disposable manifest file.
# ---------------------------------------------------------------------------------------


def _write_manifest(path: Path, *, head: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": "PERSONAL_PAPER",
        "version": 1,
        "state": "INITIALIZED",
        "host": "localhost",
        "port": 55433,
        "stores": {
            "B": {
                "database": "empirical_platform_paper",
                "identity": "PERSONAL_PAPER:B:tok",
                "head": head,
                "minimum_attempts": 3,
            },
            "C": {
                "database": "empirical_platform_paper_exit",
                "identity": "PERSONAL_PAPER:C:tok",
                "head": "d4e9c2a7f183",
                "minimum_attempts": 1,
            },
        },
    }
    path.write_text(json.dumps(manifest))


def test_step10_updates_head_and_preserves_verbatim_pre_change_copy(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, head=deploy.MIGRATION_PRE_HEAD)
    original_bytes = manifest_path.read_bytes()
    cfg = deploy_config_stub(manifest_path=manifest_path)

    detail = deploy.step10_manifest_update(
        cfg,
        release_head="deadbeef",
        backup_location=tmp_path / "backups" / "set1",
        migration_sql_sha256="abc123",
        now=datetime(2026, 10, 21, tzinfo=UTC),
    )
    assert "pre-change copy preserved" in detail

    updated = json.loads(manifest_path.read_text())
    assert updated["stores"]["B"]["head"] == deploy.MIGRATION_POST_HEAD
    assert updated["last_migration"]["release_head"] == "deadbeef"
    assert updated["last_migration"]["migration_sql_sha256"] == "abc123"
    assert updated["last_migration"]["pre_head"] == deploy.MIGRATION_PRE_HEAD
    assert updated["last_migration"]["post_head"] == deploy.MIGRATION_POST_HEAD

    backups = list(tmp_path.glob("manifest.pre-migration-*.bak.json"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original_bytes


def test_step10_is_idempotent_on_rerun(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, head=deploy.MIGRATION_PRE_HEAD)
    cfg = deploy_config_stub(manifest_path=manifest_path)
    now = datetime(2026, 10, 21, tzinfo=UTC)
    deploy.step10_manifest_update(
        cfg, release_head="h", backup_location=tmp_path, migration_sql_sha256="s", now=now
    )
    detail = deploy.step10_manifest_update(
        cfg, release_head="h", backup_location=tmp_path, migration_sql_sha256="s", now=now
    )
    assert "idempotent" in detail
    assert len(list(tmp_path.glob("manifest.pre-migration-*.bak.json"))) == 1


def test_step10_refuses_if_manifest_already_divergent(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, head="some-other-unexpected-head")
    cfg = deploy_config_stub(manifest_path=manifest_path)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step10_manifest_update(
            cfg,
            release_head="h",
            backup_location=tmp_path,
            migration_sql_sha256="s",
            now=datetime(2026, 10, 21, tzinfo=UTC),
        )
    assert excinfo.value.step == deploy.STEP_10_MANIFEST_UPDATE


# ---------------------------------------------------------------------------------------
# Migration chain head detection, including this repo's split-hex-literal revision style.
# ---------------------------------------------------------------------------------------


def test_find_chain_head_detects_the_single_tip(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "aaa.py").write_text('revision: str = "aaa"\ndown_revision: str | None = None\n')
    (versions / "bbb.py").write_text('revision: str = "bbb"\ndown_revision: str | None = "aaa"\n')
    assert deploy._find_chain_head(versions) == "bbb"


def test_find_chain_head_handles_split_hex_literal_style(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "aaa.py").write_text(
        'revision: str = "aa" + "a"\ndown_revision: str | None = None\n'
    )
    (versions / "bbb.py").write_text(
        'revision: str = "bb" + "b"\ndown_revision: str | None = "aa" + "a"\n'
    )
    assert deploy._find_chain_head(versions) == "bbb"


def test_find_chain_head_refuses_ambiguous_multi_head_chain(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "aaa.py").write_text('revision: str = "aaa"\ndown_revision: str | None = None\n')
    (versions / "bbb.py").write_text('revision: str = "bbb"\ndown_revision: str | None = None\n')
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy._find_chain_head(versions)
    assert excinfo.value.step == deploy.STEP_11_FAST_FORWARD


# ---------------------------------------------------------------------------------------
# Migration SQL integrity pin.
# ---------------------------------------------------------------------------------------


def test_pinned_migration_sql_file_matches_its_pinned_hash() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    sql_path = repo_root / "tools" / deploy.MIGRATION_SQL_FILENAME
    import hashlib

    actual = hashlib.sha256(sql_path.read_bytes()).hexdigest()
    assert actual == deploy.MIGRATION_SQL_SHA256


def test_step7_refuses_if_sql_file_hash_does_not_match_pin(tmp_path: Path) -> None:
    tampered = tmp_path / "tampered.sql"
    tampered.write_text("DROP TABLE approved_plan;")
    cfg = deploy_config_stub(migration_sql_path=tampered)
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step7_migrate(cfg)
    assert excinfo.value.step == deploy.STEP_7_MIGRATE
    assert "hash mismatch" in excinfo.value.reason


# ---------------------------------------------------------------------------------------
# Full orchestration with every step faked: resume-from-crash and halt-on-failure, for
# every one of the 14 boundaries generically (Phase 3's "every critical boundary").
# ---------------------------------------------------------------------------------------


def _patch_all_steps_to_succeed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    for step, fn_name in zip(deploy.STEP_ORDER, _STEP_FUNCTION_NAMES, strict=True):

        def make(step_name: str) -> object:
            def _fn(*args: object, **_kwargs: object) -> object:
                calls.append(step_name)
                if step_name == deploy.STEP_4_BACKUP:
                    cfg = args[0]
                    assert isinstance(cfg, deploy.DeployConfig)
                    backup_dir = cfg.backup_root / "20261021T000000000000Z-fakebackup"
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    (backup_dir / "complete.json").write_text("{}")
                    return ("ok", backup_dir)
                if step_name == deploy.STEP_12_RECOVERY_START:
                    return ("ok", 1234)
                return "ok"

            return _fn

        monkeypatch.setattr(deploy, fn_name, make(step))
    return calls


_STEP_FUNCTION_NAMES = (
    "step1_broker_verify",
    "step2_no_inflight",
    "step3_release_head",
    "step4_backup",
    "step5_shutdown",
    "step6_verify_stopped",
    "step7_migrate",
    "step8_verify_schema",
    "step9_verify_unchanged",
    "step10_manifest_update",
    "step11_fast_forward",
    "step12_recovery_start",
    "step13_verify_startup",
    "step14_stop_before_active",
)


def _run(cfg: deploy.DeployConfig, journal_path: Path) -> deploy.DeploymentJournal:
    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), _FakeNetwork())
    launch = deploy.RecoveryConsoleLaunch(executable=("x",), env={}, log_path=journal_path)
    journal = deploy.DeploymentJournal.load_or_new(journal_path)
    return deploy.run_deployment(cfg, ports, journal, journal_path, launch=launch)


def test_full_pipeline_runs_all_14_steps_in_order_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_all_steps_to_succeed(monkeypatch)
    cfg = deploy_config_stub(backup_root=tmp_path)
    journal = _run(cfg, tmp_path / "journal.json")
    assert calls == list(deploy.STEP_ORDER)
    assert journal.completed_steps() == set(deploy.STEP_ORDER)
    assert journal.last() is not None
    assert journal.last().step == deploy.STEP_14_STOP_BEFORE_ACTIVE  # type: ignore[union-attr]


@pytest.mark.parametrize("failing_step", deploy.STEP_ORDER)
def test_failure_at_every_boundary_halts_exactly_there_and_journal_is_accurate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_step: str
) -> None:
    calls = _patch_all_steps_to_succeed(monkeypatch)
    fn_name = _STEP_FUNCTION_NAMES[deploy.STEP_ORDER.index(failing_step)]

    def _fail(*_args: object, **_kwargs: object) -> object:
        calls.append(failing_step)
        raise deploy.DeploymentBlockedError(failing_step, "simulated interruption")

    monkeypatch.setattr(deploy, fn_name, _fail)
    cfg = deploy_config_stub(backup_root=tmp_path)
    journal_path = tmp_path / "journal.json"

    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        _run(cfg, journal_path)
    assert excinfo.value.step == failing_step

    expected_index = deploy.STEP_ORDER.index(failing_step)
    assert calls == list(deploy.STEP_ORDER[: expected_index + 1])

    # The journal, reloaded fresh from disk (as a human or a re-run would see it), shows
    # exactly where things stopped and nothing beyond it.
    reloaded = deploy.DeploymentJournal.load_or_new(journal_path)
    assert reloaded.last() is not None
    assert reloaded.last().step == failing_step  # type: ignore[union-attr]
    assert reloaded.last().status == "failed"  # type: ignore[union-attr]
    assert "simulated interruption" in reloaded.last().detail  # type: ignore[union-attr]
    assert failing_step not in reloaded.completed_steps()
    for later_step in deploy.STEP_ORDER[expected_index + 1 :]:
        assert later_step not in reloaded.completed_steps()


def test_resuming_after_a_crash_skips_already_completed_steps_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_all_steps_to_succeed(monkeypatch)
    cfg = deploy_config_stub(backup_root=tmp_path)
    journal_path = tmp_path / "journal.json"

    # First "crash": only let steps 1-6 run, by failing exactly at step 7.
    fail_point = deploy.STEP_7_MIGRATE

    def _fail_step7(*_a: object, **_k: object) -> str:
        calls.append(fail_point)
        raise deploy.DeploymentBlockedError(fail_point, "simulated crash")

    monkeypatch.setattr(deploy, "step7_migrate", _fail_step7)
    with pytest.raises(deploy.DeploymentBlockedError):
        _run(cfg, journal_path)
    assert calls == list(deploy.STEP_ORDER[:7])  # steps 1-6 completed, 7 attempted+failed

    # "Resume": step 7 now succeeds, and a fresh run must NOT re-execute steps 1-6.
    calls.clear()

    def _fixed_step7(*_a: object, **_k: object) -> str:
        calls.append(fail_point)
        return "fixed now"

    monkeypatch.setattr(deploy, "step7_migrate", _fixed_step7)
    _run(cfg, journal_path)
    assert calls == list(deploy.STEP_ORDER[6:])  # only step 7 onward re-ran


def test_resume_false_re_runs_every_step_even_if_previously_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_all_steps_to_succeed(monkeypatch)
    cfg = deploy_config_stub(backup_root=tmp_path)
    journal_path = tmp_path / "journal.json"
    _run(cfg, journal_path)
    calls.clear()

    ports = _ports(_FakeBroker(_FLAT_SNAPSHOT), _FakeProcess(), _FakeNetwork())
    launch = deploy.RecoveryConsoleLaunch(executable=("x",), env={}, log_path=journal_path)
    journal = deploy.DeploymentJournal.load_or_new(journal_path)
    deploy.run_deployment(cfg, ports, journal, journal_path, launch=launch, resume=False)
    assert calls == list(deploy.STEP_ORDER)


# ---------------------------------------------------------------------------------------
# main()'s production-targeting guard. Regression coverage for the adversarial-review
# finding: the guard must key off the ACTUAL resolved Store B/C database names (via the
# same `PERSONAL_DATABASES` frozenset database_safety.py itself uses), not only off
# --manifest-path -- a decoy manifest path with the ambient environment still pointed at
# a real protected database must still be refused without --confirm-production.
# ---------------------------------------------------------------------------------------


def _main_args(tmp_path: Path, manifest_path: Path, *, confirm_production: bool) -> list[str]:
    args = [
        "--repo-path",
        str(tmp_path),
        "--expected-release-head",
        "deadbeef",
        "--manifest-path",
        str(manifest_path),
        "--backup-root",
        str(tmp_path / "backups"),
        "--pg-bin",
        str(tmp_path),
        "--journal-path",
        str(tmp_path / "journal.json"),
    ]
    if confirm_production:
        args.append("--confirm-production")
    return args


def test_main_refuses_a_decoy_manifest_path_when_the_real_database_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact bug an independent review found: a non-production --manifest-path must
    NOT be enough to bypass --confirm-production if the ambient environment's Store B/C
    database names are the real, protected ones."""
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform_paper")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", "x")
    monkeypatch.setenv(
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE", "empirical_platform_paper_exit"
    )
    monkeypatch.setenv("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_PASSWORD", "x")
    decoy_manifest = tmp_path / "decoy-manifest.json"
    exit_code = deploy.main(_main_args(tmp_path, decoy_manifest, confirm_production=False))
    assert exit_code == 2


def test_main_accepts_the_real_database_once_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With --confirm-production given, the same real-database environment is accepted by
    the guard (and only fails later, at the unrelated Alpaca-credential check)."""
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform_paper")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", "x")
    monkeypatch.setenv(
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE", "empirical_platform_paper_exit"
    )
    monkeypatch.setenv("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_PASSWORD", "x")
    monkeypatch.delenv("EMPIRICAL_ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("EMPIRICAL_ALPACA_PAPER_SECRET_KEY", raising=False)
    decoy_manifest = tmp_path / "decoy-manifest.json"
    exit_code = deploy.main(_main_args(tmp_path, decoy_manifest, confirm_production=True))
    assert exit_code == 2  # past the production guard; refused only for missing Alpaca creds


def test_main_refuses_confirm_production_against_a_genuinely_disposable_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "some_disposable_test_db")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", "x")
    monkeypatch.setenv(
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE", "some_other_disposable_test_db"
    )
    monkeypatch.setenv("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_PASSWORD", "x")
    decoy_manifest = tmp_path / "decoy-manifest.json"
    exit_code = deploy.main(_main_args(tmp_path, decoy_manifest, confirm_production=True))
    assert exit_code == 2


def test_main_refuses_disposable_targets_silently_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fully disposable target (not the real manifest path, not a real database name)
    needs no --confirm-production at all, and proceeds past the guard."""
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "some_disposable_test_db")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", "x")
    monkeypatch.setenv(
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE", "some_other_disposable_test_db"
    )
    monkeypatch.setenv("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_PASSWORD", "x")
    monkeypatch.delenv("EMPIRICAL_ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("EMPIRICAL_ALPACA_PAPER_SECRET_KEY", raising=False)
    decoy_manifest = tmp_path / "decoy-manifest.json"
    exit_code = deploy.main(_main_args(tmp_path, decoy_manifest, confirm_production=False))
    assert exit_code == 2  # past the production guard; refused only for missing Alpaca creds


# ---------------------------------------------------------------------------------------
# Config stub helper
# ---------------------------------------------------------------------------------------


def deploy_config_stub(
    *,
    repo_path: Path = Path("."),
    expected_release_head: str = "deadbeef",
    manifest_path: Path | None = None,
    backup_root: Path | None = None,
    console_pid: int | None = 4242,
    shutdown_timeout_seconds: float = 5.0,
    startup_timeout_seconds: float = 5.0,
    migration_sql_path: Path | None = None,
) -> deploy.DeployConfig:
    placeholder = PostgreSQLConfigSnapshot(
        host="localhost", port=55555, database="placeholder_test", user="empirical"
    )
    return deploy.DeployConfig(
        repo_path=repo_path,
        expected_release_head=expected_release_head,
        manifest_path=manifest_path or Path("manifest.json"),
        backup_root=backup_root or Path("."),
        pg_bin=Path("."),
        store_b_config=placeholder,
        store_c_config=placeholder,
        migration_sql_path=migration_sql_path or Path("migration.sql"),
        console_host="127.0.0.1",
        console_port=8189,
        console_pid=console_pid,
        shutdown_timeout_seconds=shutdown_timeout_seconds,
        startup_timeout_seconds=startup_timeout_seconds,
    )


# ---------------------------------------------------------------------------------------
# M096: Store C connectivity must match the real console entrypoint's resolution
# (`_paper_position_exit_composition.resolve_paper_exit_postgres_config`) -- one real
# Postgres server, two databases, Store C reusing Store B's host/port/user/password. The
# real environment never sets EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST/_PORT/_USER/
# _PASSWORD; an earlier version of `_store_c_config` always required them, which crashed
# with an unhandled KeyError against the real environment (found during the 2026-10-22
# read-only preflight, before any step of a real deployment ever ran).
# ---------------------------------------------------------------------------------------

_REAL_STORE_B_CONFIG = PostgreSQLConfigSnapshot(
    host="localhost", port=55433, database="empirical_platform_paper", user="empirical"
)


def test_store_c_config_falls_back_to_store_b_connection_when_host_is_not_set() -> None:
    """The real shape today: no EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_* at all."""
    resolved = deploy._store_c_config(_REAL_STORE_B_CONFIG, {})
    assert resolved.host == _REAL_STORE_B_CONFIG.host
    assert resolved.port == _REAL_STORE_B_CONFIG.port
    assert resolved.user == _REAL_STORE_B_CONFIG.user
    assert resolved.password == _REAL_STORE_B_CONFIG.password
    assert resolved.database == "empirical_platform_paper_exit"


def test_store_c_config_fallback_preserves_store_bs_real_port_55433() -> None:
    """The exact bug this fix closes: the old code defaulted an unset Store C port to
    5432, silently wrong for the real server at 55433."""
    resolved = deploy._store_c_config(_REAL_STORE_B_CONFIG, {})
    assert resolved.port == 55433
    assert resolved.port != 5432


def test_store_c_config_fallback_honors_an_explicit_database_name_override() -> None:
    """EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE alone (no _HOST) still only swaps
    the database name -- matching the real console entrypoint's own precedence."""
    resolved = deploy._store_c_config(
        _REAL_STORE_B_CONFIG, {"EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE": "custom_db"}
    )
    assert resolved.database == "custom_db"
    assert resolved.host == _REAL_STORE_B_CONFIG.host
    assert resolved.port == _REAL_STORE_B_CONFIG.port


def test_store_c_config_uses_independent_settings_when_host_is_explicitly_set() -> None:
    """A future split-server topology: EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST set
    switches to the fully independent form, never mixing in Store B's values."""
    environ = {
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST": "other-server",
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_PORT": "6543",
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE": "empirical_platform_paper_exit",
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_USER": "other_user",
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_PASSWORD": "x",
    }
    resolved = deploy._store_c_config(_REAL_STORE_B_CONFIG, environ)
    assert resolved.host == "other-server"
    assert resolved.port == 6543
    assert resolved.user == "other_user"
    assert resolved.password is not None
    assert resolved.password.get_secret_value() == "x"


def test_store_c_config_independent_mode_still_requires_database_and_password() -> None:
    """Independent mode is the ORIGINAL, always-fully-specified form -- setting _HOST
    without _DATABASE/_PASSWORD must still refuse, not silently fall back."""
    environ = {"EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST": "other-server"}
    with pytest.raises(KeyError):
        deploy._store_c_config(_REAL_STORE_B_CONFIG, environ)


@pytest.mark.parametrize("partial_field", ["PORT", "USER", "PASSWORD"])
def test_store_c_config_refuses_partial_override_without_host(partial_field: str) -> None:
    """_PORT/_USER/_PASSWORD without _HOST is ambiguous -- refused before touching
    anything, never silently mixed with Store B's values."""
    environ = {f"EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_{partial_field}": "something"}
    with pytest.raises(DatabaseSafetyError):
        deploy._store_c_config(_REAL_STORE_B_CONFIG, environ)


def test_store_c_fallback_constants_match_the_real_console_entrypoint() -> None:
    """Drift guard: if the real console entrypoint's env var name or default database
    name ever changes, this test fails loudly instead of the two silently diverging."""
    from empirical_platform.entrypoints import _paper_position_exit_composition as real

    assert deploy._PAPER_EXIT_DATABASE_VARIABLE == real.PAPER_EXIT_DATABASE_VARIABLE
    assert deploy._DEFAULT_STORE_C_DATABASE == real._DEFAULT_STORE_C_DATABASE


def test_shutdown_capability_constant_matches_the_real_console_entrypoint() -> None:
    """MILESTONE-098 drift guard: `read_control_token`'s `expected_capability` must name
    the exact same capability the console itself writes into its control token."""
    from empirical_platform.entrypoints import operator_console as real

    assert deploy._SHUTDOWN_CONTROL_CAPABILITY == real.SHUTDOWN_CONTROL_CAPABILITY


def test_main_refuses_cleanly_before_touching_anything_when_store_c_is_partially_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-safe BEFORE any step runs: an ambiguous Store C override must refuse cleanly
    (exit 2, no traceback) and never create the journal file -- proof nothing ran."""
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "some_disposable_test_db")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", "x")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_USER", "someone")
    monkeypatch.delenv("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST", raising=False)
    journal_path = tmp_path / "journal.json"
    args = _main_args(tmp_path, tmp_path / "decoy-manifest.json", confirm_production=False)
    exit_code = deploy.main(args)
    assert exit_code == 2
    assert not journal_path.exists()


def test_main_uses_store_c_fallback_against_a_disposable_target_without_independent_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() itself, end to end through the config-resolution fix: a disposable Store B
    target with NO independent Store C env vars at all must still pass the config-
    resolution step cleanly (refused only later, at the unrelated Alpaca-credential
    check) -- proving main() no longer hard-requires EMPIRICAL_PLATFORM_PAPER_EXIT_
    POSTGRES_DATABASE/_PASSWORD."""
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "some_disposable_test_db")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", "x")
    for suffix in ("HOST", "PORT", "DATABASE", "USER", "PASSWORD"):
        monkeypatch.delenv(f"EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_{suffix}", raising=False)
    monkeypatch.delenv("EMPIRICAL_ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("EMPIRICAL_ALPACA_PAPER_SECRET_KEY", raising=False)
    args = _main_args(tmp_path, tmp_path / "decoy-manifest.json", confirm_production=False)
    exit_code = deploy.main(args)
    assert exit_code == 2  # past Store B/C config resolution; refused only for Alpaca creds


def test_main_triggers_production_guard_via_store_c_fallback_database_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Database-identity check, through the fallback path: Store B is fully disposable,
    Store C has no independent _HOST, but its fallback-resolved database name alone
    equals a real, protected database -- --confirm-production must still be required."""
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "some_disposable_test_db")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", "x")
    monkeypatch.setenv(
        "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE", "empirical_platform_paper_exit"
    )
    monkeypatch.delenv("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST", raising=False)
    decoy_manifest = tmp_path / "decoy-manifest.json"
    exit_code = deploy.main(_main_args(tmp_path, decoy_manifest, confirm_production=False))
    assert exit_code == 2


# ---------------------------------------------------------------------------------------
# M098-R: how the shutdown token travels, and the native Windows process/port queries.
# ---------------------------------------------------------------------------------------


class _RecordingHandler:
    """Builds a tiny HTTP server class that records what it received and answers as told."""

    @staticmethod
    def server(
        status: int, extra_headers: dict[str, str], body: bytes
    ) -> tuple[object, list[dict[str, str]]]:
        import http.server
        import threading

        seen: list[dict[str, str]] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib naming
                seen.append({k.lower(): v for k, v in self.headers.items()})
                self.send_response(status)
                for key, value in extra_headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST  # noqa: N815

            def log_message(self, *_args: object) -> None:
                return

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, seen


def test_the_shutdown_token_never_goes_through_a_proxy_or_follows_a_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M098-R: `urllib.request.urlopen` honoured HTTP_PROXY (Python bypasses a proxy for
    loopback only if NO_PROXY says so) and followed redirects, either of which would hand the
    token header to a third party. The request must go straight to the console and stop
    there."""
    trap, trap_seen = _RecordingHandler.server(200, {}, b"trap")
    proxy, proxy_seen = _RecordingHandler.server(200, {}, b"proxy")
    console, console_seen = _RecordingHandler.server(
        307,
        {"Location": f"http://127.0.0.1:{trap.server_address[1]}/stolen"},
        b"",  # type: ignore[attr-defined]
    )
    try:
        for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(name, f"http://127.0.0.1:{proxy.server_address[1]}")  # type: ignore[attr-defined]
        for name in ("NO_PROXY", "no_proxy"):
            monkeypatch.delenv(name, raising=False)
        status, _body = deploy._post_loopback_shutdown(  # noqa: SLF001
            "127.0.0.1",
            console.server_address[1],
            "secret-token-value",  # type: ignore[attr-defined]
        )
        assert status == 307
        assert (
            console_seen and console_seen[0]["x-empirical-shutdown-token"] == "secret-token-value"
        )
        assert proxy_seen == []
        assert trap_seen == []
    finally:
        for server in (trap, proxy, console):
            server.shutdown()  # type: ignore[attr-defined]


def test_a_refused_connection_names_no_token(tmp_path: Path) -> None:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    with pytest.raises(deploy.ConsoleShutdownError) as excinfo:
        deploy._post_loopback_shutdown("127.0.0.1", free_port, "secret-token-value")  # noqa: SLF001
    assert "secret-token-value" not in str(excinfo.value)
    del tmp_path


_WINDOWS_ONLY = pytest.mark.skipif(
    deploy.os.name != "nt", reason="Windows process and port queries"
)


@_WINDOWS_ONLY
@pytest.mark.parametrize("host", ["192.0.2.10", "localhost", "example.invalid", "0.0.0.0"])  # noqa: S104
def test_graceful_stop_refuses_a_non_loopback_host_before_reading_the_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    def _must_not_read(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the token must not even be read for a non-loopback host")

    monkeypatch.setattr(deploy.console_control, "read_control_token", _must_not_read)
    with pytest.raises(deploy.ConsoleShutdownError, match="loopback"):
        deploy.RealProcessPort().graceful_stop(
            deploy.os.getpid(), host=host, port=8189, safety_directory=tmp_path
        )


@_WINDOWS_ONLY
def test_graceful_stop_refuses_a_pid_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(deploy.ConsoleShutdownError, match="could not confirm the identity"):
        deploy.RealProcessPort().graceful_stop(
            2**30 - 1, host="127.0.0.1", port=8189, safety_directory=tmp_path
        )


@_WINDOWS_ONLY
def test_real_is_running_is_native_and_never_reports_an_unknown_answer_as_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbidden(*args: object, **_kwargs: object) -> None:
        raise AssertionError(f"is_running must not shell out: {args!r}")

    monkeypatch.setattr(deploy.subprocess, "run", _forbidden)
    process = deploy.RealProcessPort()
    assert process.is_running(deploy.os.getpid()) is True
    assert process.is_running(2**30 - 1) is False


@_WINDOWS_ONLY
def test_real_owning_pid_reads_the_native_listener_table_for_the_exact_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    def _forbidden(*args: object, **_kwargs: object) -> None:
        raise AssertionError(
            f"owning_pid must not shell out (netstat output is localized): {args!r}"
        )

    monkeypatch.setattr(deploy.subprocess, "run", _forbidden)
    network = deploy.RealNetworkPort()
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as v6:
        v6.bind(("::1", 0))
        v6.listen(1)
        port = v6.getsockname()[1]
        assert network.owning_pid("::1", port) == deploy.os.getpid()
        # A listener on a different address of the same port is not what 127.0.0.1 reaches.
        assert network.owning_pid("127.0.0.1", port) is None
    assert network.owning_pid("::1", port) is None


def test_owning_pid_refuses_two_different_listeners(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deploy.os, "name", "nt")
    monkeypatch.setattr(
        deploy.console_control,
        "windows_tcp_listeners",
        lambda port: [("127.0.0.1", 11), ("0.0.0.0", 22)],  # noqa: S104
    )
    with pytest.raises(RuntimeError, match="more than one process"):
        deploy.RealNetworkPort().owning_pid("127.0.0.1", 8189)
