"""RELEASE v1 hardening: single-instance lock, maintenance hold, exit-code contract, Windows
port-exclusivity decision and the autostart wrapper's static contract."""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from empirical_platform.entrypoints import (
    _operator_console_web as web,
)
from empirical_platform.entrypoints import (
    operator_console,
    release_maintenance_hold,
)
from empirical_platform.shared import console_control, console_lifecycle
from empirical_platform.shared.console_lifecycle import (
    ConsoleAlreadyRunningError,
    ConsoleInstanceLock,
)

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "deploy" / "windows" / "run-v1-console.ps1"
TASK_XML = REPO / "deploy" / "windows" / "v1-console-task.xml"

# -- single-instance lock ------------------------------------------------------------------


def test_two_acquirers_conflict_and_release_frees_it(tmp_path: Path) -> None:
    first, second = ConsoleInstanceLock(tmp_path), ConsoleInstanceLock(tmp_path)
    first.acquire()
    assert first.held
    with pytest.raises(ConsoleAlreadyRunningError, match="already holds"):
        second.acquire()
    assert not second.held
    first.release()
    second.acquire()
    assert second.held
    second.release()


def test_the_conflict_message_names_the_holder(tmp_path: Path) -> None:
    with ConsoleInstanceLock(tmp_path), pytest.raises(ConsoleAlreadyRunningError, match="PID"):
        ConsoleInstanceLock(tmp_path).acquire()


def test_a_stale_lock_file_from_a_dead_process_is_acquirable(tmp_path: Path) -> None:
    child = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import sys,os;from pathlib import Path;"
            "from empirical_platform.shared.console_lifecycle import ConsoleInstanceLock;"
            "ConsoleInstanceLock(Path(sys.argv[1])).acquire();os._exit(0)",
            str(tmp_path),
        ],
        check=True,
        env={"PYTHONPATH": str(REPO / "src"), "PATH": ""},
    )
    assert child.returncode == 0
    lock_file = tmp_path / "console-control" / console_lifecycle.LOCK_FILE_NAME
    assert lock_file.exists()  # the stale file is still there ...
    with ConsoleInstanceLock(tmp_path) as lock:  # ... and the OS had already dropped the lock
        assert lock.held


def test_a_live_lock_in_another_process_blocks_us(tmp_path: Path) -> None:
    holder = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import sys;from pathlib import Path;"
            "from empirical_platform.shared.console_lifecycle import ConsoleInstanceLock;"
            "lock=ConsoleInstanceLock(Path(sys.argv[1]));lock.acquire();print('held',flush=True);"
            "sys.stdin.read()",
            str(tmp_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env={"PYTHONPATH": str(REPO / "src"), "PATH": ""},
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        with pytest.raises(ConsoleAlreadyRunningError):
            ConsoleInstanceLock(tmp_path).acquire()
    finally:
        holder.kill()
        holder.wait()
    ConsoleInstanceLock(tmp_path).acquire()  # killed holder: the OS released it


# -- maintenance hold ----------------------------------------------------------------------


def test_hold_is_created_atomically_idempotently_and_owner_only(tmp_path: Path) -> None:
    assert not console_lifecycle.maintenance_hold_active(tmp_path)
    assert console_lifecycle.create_maintenance_hold(tmp_path, reason="t") is True
    assert console_lifecycle.maintenance_hold_active(tmp_path)
    path = console_lifecycle.hold_path(tmp_path)
    original = path.read_text()
    assert json.loads(original)["reason"] == "t"
    assert console_lifecycle.create_maintenance_hold(tmp_path, reason="other") is False
    assert path.read_text() == original
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700


def test_release_removes_the_hold(tmp_path: Path) -> None:
    console_lifecycle.create_maintenance_hold(tmp_path, reason="t")
    assert console_lifecycle.release_maintenance_hold(tmp_path) is True
    assert console_lifecycle.release_maintenance_hold(tmp_path) is False
    assert not console_lifecycle.maintenance_hold_active(tmp_path)


def test_release_cli_refuses_without_evidence_or_override(tmp_path: Path) -> None:
    console_lifecycle.create_maintenance_hold(tmp_path, reason="t")
    base = ["--safety-directory", str(tmp_path)]
    assert release_maintenance_hold.main(base) == 2
    bad = tmp_path / "journal.json"
    bad.write_text(
        json.dumps({"records": [{"step": "STEP_12_RECOVERY_START", "status": "completed"}]})
    )
    assert release_maintenance_hold.main([*base, "--journal-path", str(bad)]) == 2
    assert release_maintenance_hold.main([*base, "--journal-path", str(tmp_path / "nope")]) == 2
    assert console_lifecycle.maintenance_hold_active(tmp_path)


def test_release_cli_accepts_a_complete_journal_or_the_owner_override(tmp_path: Path) -> None:
    good = tmp_path / "journal.json"
    steps = ("STEP_12_RECOVERY_START", "STEP_13_VERIFY_STARTUP", "STEP_14_STOP_BEFORE_ACTIVE")
    good.write_text(json.dumps({"records": [{"step": s, "status": "completed"} for s in steps]}))
    console_lifecycle.create_maintenance_hold(tmp_path, reason="t")
    base = ["--safety-directory", str(tmp_path)]
    assert release_maintenance_hold.main([*base, "--journal-path", str(good)]) == 0
    assert not console_lifecycle.maintenance_hold_active(tmp_path)
    console_lifecycle.create_maintenance_hold(tmp_path, reason="t")
    assert release_maintenance_hold.main([*base, "--owner-override"]) == 0
    assert not console_lifecycle.maintenance_hold_active(tmp_path)


# -- the console: gate ordering, exit codes -------------------------------------------------


class _SentinelError(Exception):
    pass


def _fake_runtime_factory(
    record: list[object],
) -> Callable[..., contextlib.AbstractContextManager[object]]:
    @contextlib.contextmanager
    def fake(*, recovery_mode: bool) -> Iterator[object]:
        # The composition (database/broker) must only be reached with the lock already held.
        with pytest.raises(ConsoleAlreadyRunningError):
            ConsoleInstanceLock(record[0]).acquire()  # type: ignore[arg-type]
        record.append(recovery_mode)
        raise _SentinelError
        yield  # pragma: no cover

    return fake


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    return ["--capability", "paper-exit", "--safety-directory", str(tmp_path), *extra]


def test_lock_is_held_before_the_composition_and_the_listener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record: list[object] = [tmp_path]
    monkeypatch.setattr(
        operator_console, "paper_operator_console_with_exit_runtime", _fake_runtime_factory(record)
    )
    monkeypatch.setattr(
        operator_console, "serve", lambda *a, **k: pytest.fail("listener must not start")
    )
    with pytest.raises(_SentinelError):
        operator_console.main(_argv(tmp_path))
    assert record[1:] == [False]
    # and the lock is released again when the process-level context unwinds
    ConsoleInstanceLock(tmp_path).acquire()


@pytest.mark.parametrize("extra", [(), ("--recovery-mode",)])
def test_second_instance_exits_73_without_touching_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: tuple[str, ...]
) -> None:
    monkeypatch.setattr(
        operator_console,
        "paper_operator_console_with_exit_runtime",
        lambda **_k: pytest.fail("state must not be opened"),
    )
    with ConsoleInstanceLock(tmp_path):
        code = operator_console.main(_argv(tmp_path, *extra))
    assert code == console_lifecycle.EXIT_ALREADY_RUNNING == 73


def test_full_mode_refuses_while_the_hold_exists_but_recovery_mode_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    console_lifecycle.create_maintenance_hold(tmp_path, reason="t")
    record: list[object] = [tmp_path]
    monkeypatch.setattr(
        operator_console, "paper_operator_console_with_exit_runtime", _fake_runtime_factory(record)
    )
    assert operator_console.main(_argv(tmp_path)) == console_lifecycle.EXIT_MAINTENANCE_HOLD == 74
    assert "maintenance hold" in capsys.readouterr().err
    assert record == [tmp_path]  # composition never reached, lock never even taken
    ConsoleInstanceLock(tmp_path).acquire()
    with pytest.raises(_SentinelError):
        operator_console.main(_argv(tmp_path, "--recovery-mode"))


def test_authenticated_shutdown_makes_the_server_loop_return_the_distinct_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    router = web.Router(web.SecuritySession())
    stop = threading.Event()

    class FakeServer:
        server_port = 8190

        def shutdown(self) -> None:
            stop.set()

        def serve_forever(self, poll_interval: float) -> None:
            record = console_control.read_control_token(
                tmp_path,
                port=8190,
                expected_capability="paper-exit",
                expected_pid=operator_console.os.getpid(),
                expected_start_fingerprint=console_control.process_start_fingerprint(
                    operator_console.os.getpid()
                ),
            )
            environ = {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/control/shutdown",
                "REMOTE_ADDR": "127.0.0.1",
                "HTTP_X_EMPIRICAL_SHUTDOWN_TOKEN": record.token,
            }
            list(router(environ, lambda *_a: None))
            assert stop.wait(5)

    @contextlib.contextmanager
    def fake_serve(app: object, *, host: str, port: int) -> Iterator[FakeServer]:
        yield FakeServer()

    monkeypatch.setattr(operator_console, "serve", fake_serve)
    code = operator_console._serve_with_reconciler(  # noqa: SLF001
        router,
        refresh=lambda: None,
        host="127.0.0.1",
        port=0,
        no_browser=True,
        reconcile_every=0,
        banner=(),
        shutdown_control=operator_console.ShutdownControl(safety_directory=tmp_path),
    )
    assert code == console_lifecycle.EXIT_DELIBERATE_SHUTDOWN == 64


def test_ctrl_c_style_stop_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeServer:
        server_port = 0

        def serve_forever(self, poll_interval: float) -> None:
            raise KeyboardInterrupt

    @contextlib.contextmanager
    def fake_serve(app: object, *, host: str, port: int) -> Iterator[FakeServer]:
        yield FakeServer()

    monkeypatch.setattr(operator_console, "serve", fake_serve)
    assert (
        operator_console._serve_with_reconciler(  # noqa: SLF001
            object(),  # type: ignore[arg-type]
            refresh=lambda: None,
            host="127.0.0.1",
            port=0,
            no_browser=True,
            reconcile_every=0,
            banner=(),
        )
        == 0
    )


# -- port exclusivity decision --------------------------------------------------------------


def test_reuse_address_is_off_on_windows_and_on_elsewhere() -> None:
    assert web.reuse_address_allowed("win32") is False
    assert web.reuse_address_allowed("linux") is True
    assert web.reuse_address_allowed("darwin") is True
    assert web.ThreadingWSGIServer.allow_reuse_address is (sys.platform != "win32")


def test_windows_sets_exclusive_addr_use_and_posix_sets_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int, int]] = []

    class FakeSocket:
        def setsockopt(self, level: int, option: int, value: int) -> None:
            calls.append((level, option, value))

    monkeypatch.setattr(web.socket, "SO_EXCLUSIVEADDRUSE", -5, raising=False)
    web.apply_exclusive_bind(FakeSocket(), "linux")
    assert calls == []
    web.apply_exclusive_bind(FakeSocket(), "win32")
    assert calls == [(web.socket.SOL_SOCKET, -5, 1)]


# -- autostart wrapper static contract -------------------------------------------------------


def test_wrapper_checks_the_hold_before_every_launch_and_handles_exit_codes() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "Set-StrictMode -Version Latest" in text
    assert '$ErrorActionPreference = "Stop"' in text
    assert "Invoke-Expression" not in text and "iex " not in text
    assert "maintenance-hold.json" in text
    loop = text[text.index("while ($true)") :]
    assert loop.index("Test-Path -LiteralPath $HoldFile") < loop.index(
        "operator_console --capability paper-exit"
    )
    assert "$LASTEXITCODE" in text
    match = re.search(r"\$NoRestartExitCodes = @\(([^)]*)\)", text)
    assert match is not None
    codes = {int(c) for c in match.group(1).split(",")}
    assert codes == set(console_lifecycle.EXIT_NO_RESTART_CODES)
    assert "$MaxRestartsPerWindow" in text and "$RestartWindowSeconds" in text
    assert "circuit breaker" in text
    assert "Start-Sleep -Seconds 10" not in text  # no fixed unconditional 10 s relaunch
    assert "ABCDEF" not in text and "API_KEY" not in text.upper()


def test_task_xml_restart_is_bounded_and_keeps_the_owner_only_header() -> None:
    text = TASK_XML.read_text(encoding="utf-8")
    assert "<Count>999</Count>" not in text
    count = int(re.search(r"<Count>(\d+)</Count>", text).group(1))  # type: ignore[union-attr]
    assert count <= 3
    assert "Owner" in text and "NOT registered" in text


def test_task_xml_is_well_formed_and_declares_its_real_encoding() -> None:
    """M100 final review (P1): the file declared UTF-16 while being ASCII and its header comment
    contained `--`, so Task Scheduler's Import Task rejected it."""
    from xml.dom import minidom

    raw = TASK_XML.read_bytes()
    assert raw.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
    minidom.parseString(raw)
