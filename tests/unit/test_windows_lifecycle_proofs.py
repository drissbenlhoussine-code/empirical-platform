"""PROOFS of the Windows autostart / single-instance guarantees (RELEASE v1, M100).

How each guarantee is proven, and where it actually executes:

* WRAPPER BEHAVIOUR (class `TestWrapperExecution`, Windows only). The REAL
  `deploy/windows/run-v1-console.ps1` is copied into a sandbox repo layout under `tmp_path`
  and executed by `pwsh` and by Windows PowerShell 5.1 (each one that is installed). A stub
  `python.cmd` earlier on PATH records every launch (and whether `--recovery-mode` was passed)
  and exits with the next code from a queue, so each scenario scripts the console's exit codes.
  LOCALAPPDATA points at the sandbox, so the maintenance-hold file lives there. Backoff sleeps
  are shortened only through the documented test seam EMPIRICAL_WRAPPER_TEST_SLEEP_SCALE; a
  static test (runs everywhere) pins the production limits and proves the seam can only
  shorten sleeps. These tests are skipped on non-Windows platforms and are executed by the
  `verify` job of .github/workflows/ci.yml on `windows-latest`.
* LOCK + PORT. Real separate OS processes contend for the PAPER lock (cross-platform; the
  Windows `msvcrt.locking` path runs on the Windows runner) and the real console entrypoint
  is launched as a second process and must exit 73 without touching the state directory.
  Real sockets prove the loopback port cannot be double-bound through the production
  `ThreadingWSGIServer.server_bind` (Windows asserts WinError 10013/10048; POSIX asserts a
  refusal). The platform decision itself is unit-tested on every platform.
* DEPLOYMENT STOP vs AUTOSTART (cross-platform). The deploy tool's real step 5 is driven with
  fakes: the hold exists before the stop signal and survives to step 14, and the wrapper, the
  console gate and the deploy tool all resolve the SAME hold path.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest
from tools import personal_paper_deploy as deploy

from empirical_platform.entrypoints import _operator_console_web as web
from empirical_platform.shared import console_lifecycle
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.console_lifecycle import (
    ConsoleAlreadyRunningError,
    ConsoleInstanceLock,
)
from empirical_platform.shared.persistence import database_safety

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "deploy" / "windows" / "run-v1-console.ps1"
HOLD_RELATIVE = ("EmpiricalPlatform", "safety", "console-control", "maintenance-hold.json")
SCALE_ENV = "EMPIRICAL_WRAPPER_TEST_SLEEP_SCALE"

# ---------------------------------------------------------------------------------------
# Static: production limits unchanged, test seam can only shorten sleeps
# ---------------------------------------------------------------------------------------


def test_wrapper_production_defaults_are_unchanged_and_the_seam_only_shortens() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    for line in (
        "$MaxRestartsPerWindow = 5",
        "$RestartWindowSeconds = 600",
        "$InitialBackoffSeconds = 10",
        "$MaxBackoffSeconds = 300",
        "$SleepScale = 1.0",
        "$NoRestartExitCodes = @(0, 2, 64, 73, 74)",
    ):
        assert line in text, f"production default changed or missing: {line}"
    assert text.count(SCALE_ENV) == 2  # the explanatory comment and the single read
    assert "$parsedScale -gt 0 -and $parsedScale -le 1" in text  # can only shorten
    sleeps = re.findall(r"^\s*Start-Sleep .*$", text, flags=re.MULTILINE)
    assert len(sleeps) == 1 and "$SleepScale" in sleeps[0] and "$backoff" in sleeps[0], sleeps
    # the doubling/cap arithmetic must not involve the scale
    assert "$backoff = [Math]::Min($backoff * 2, $MaxBackoffSeconds)" in text


# ---------------------------------------------------------------------------------------
# 1. Wrapper behaviour: the real script, executed (Windows only)
# ---------------------------------------------------------------------------------------

_STUB_PY = """\
import json, os, sys, time
d = os.environ["WRAPPER_STUB_DIR"]
with open(os.path.join(d, "launches.log"), "a", encoding="utf-8") as log:
    log.write(json.dumps({"recovery": "--recovery-mode" in sys.argv,
                          "args": sys.argv[1:]}) + "\\n")
q = os.path.join(d, "codes.json")
with open(q, encoding="utf-8") as f:
    codes = json.load(f)
code = codes.pop(0) if len(codes) > 1 else codes[0]  # the last entry repeats forever
with open(q, "w", encoding="utf-8") as f:
    json.dump(codes, f)
sys.exit(code)
"""


def _shells() -> list[str]:
    return [name for name in ("pwsh", "powershell") if shutil.which(name)]


class _Sandbox:
    def __init__(self, root: Path, shell: str) -> None:
        self.shell = shell
        script_dir = root / "repo" / "deploy" / "windows"
        script_dir.mkdir(parents=True)
        self.script = script_dir / WRAPPER.name
        shutil.copyfile(WRAPPER, self.script)
        activate = root / "repo" / ".venv" / "Scripts"
        activate.mkdir(parents=True)
        (activate / "Activate.ps1").write_text("# no-op stub\n", encoding="ascii")
        self.stub_dir = root / "stub"
        self.stub_dir.mkdir()
        (self.stub_dir / "stub_python.py").write_text(_STUB_PY, encoding="ascii")
        (self.stub_dir / "python.cmd").write_text(
            f'@"{sys.executable}" "%~dp0stub_python.py" %*\r\n@exit /b %ERRORLEVEL%\r\n',
            encoding="ascii",
        )
        self.local_app_data = root / "localappdata"
        self.hold = self.local_app_data.joinpath(*HOLD_RELATIVE)
        self.hold.parent.mkdir(parents=True)

    def set_codes(self, codes: list[int]) -> None:
        (self.stub_dir / "codes.json").write_text(json.dumps(codes), encoding="ascii")

    def launches(self) -> list[dict[str, object]]:
        log = self.stub_dir / "launches.log"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="ascii").splitlines() if line]

    def create_hold(self) -> None:
        self.hold.write_text('{"reason": "test"}', encoding="ascii")

    def start(self, scale: str = "0.001") -> subprocess.Popen[str]:
        env = dict(os.environ)
        env["LOCALAPPDATA"] = str(self.local_app_data)
        env["WRAPPER_STUB_DIR"] = str(self.stub_dir)
        env["PATH"] = str(self.stub_dir) + os.pathsep + env.get("PATH", "")
        env[SCALE_ENV] = scale
        env.pop("PYTHONPATH", None)
        return subprocess.Popen(  # noqa: S603
            [
                self.shell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.script),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        subprocess.run(  # noqa: S603
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],  # noqa: S607
            capture_output=True,
            check=False,
            timeout=30,
        )
        proc.kill()


@pytest.fixture(params=_shells() or ["no-powershell"])
def box(request: pytest.FixtureRequest, tmp_path: Path) -> _Sandbox:
    if sys.platform != "win32":
        pytest.skip("the autostart wrapper only runs on Windows (executed in CI windows-latest)")
    if request.param == "no-powershell":
        pytest.fail("neither pwsh nor powershell is on PATH on this Windows host")
    return _Sandbox(tmp_path, request.param)


def _run_to_exit(box: _Sandbox, *, timeout: float = 25.0) -> tuple[int, str]:
    proc = box.start()
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        out, _ = proc.communicate()
        pytest.fail(
            f"wrapper did not exit within {timeout}s via {box.shell}; launches="
            f"{len(box.launches())}; output:\n{out}"
        )
    finally:
        _kill_tree(proc)
    return proc.returncode, out


@pytest.mark.skipif(
    sys.platform != "win32", reason="runs the real .ps1 wrapper; executed on windows-latest in CI"
)
class TestWrapperExecution:
    @pytest.mark.parametrize("code", [64, 0, 2, 73, 74])
    def test_do_not_restart_codes_launch_exactly_once_and_exit_zero(
        self, box: _Sandbox, code: int
    ) -> None:
        box.set_codes([code, 1])  # a second launch would return a crash code and show up
        rc, out = _run_to_exit(box)
        launches = box.launches()
        assert len(launches) == 1, f"code {code}: expected ONE launch, got {launches}\n{out}"
        assert rc == 0, f"wrapper exit code {rc} (must be 0 for intentional stops)\n{out}"
        assert f"exited with code {code}" in out, out
        assert launches[0]["recovery"] is False  # the wrapper launches FULL mode

    def test_a_crash_is_relaunched_then_a_deliberate_stop_ends_it(self, box: _Sandbox) -> None:
        box.set_codes([1, 137, 64])
        rc, out = _run_to_exit(box)
        assert len(box.launches()) == 3, f"crash codes must relaunch\n{out}"
        assert rc == 0, out
        assert "exit code 1)" in out and "exit code 137)" in out, out

    def test_circuit_breaker_stops_after_more_than_five_crashes(self, box: _Sandbox) -> None:
        box.set_codes([1])  # always crashes
        rc, out = _run_to_exit(box)
        launches = box.launches()
        # more than 5 restarts inside the window: the 6th recorded crash trips it
        assert len(launches) == 6, (
            f"expected 6 launches before the breaker, got {len(launches)}\n{out}"
        )
        assert rc == 0, f"breaker must exit 0 (no Task Scheduler relaunch), got {rc}\n{out}"
        assert "circuit breaker" in out and "giving up" in out, out

    def test_hold_present_before_start_means_zero_launches(self, box: _Sandbox) -> None:
        box.create_hold()
        box.set_codes([1])
        rc, out = _run_to_exit(box)
        assert box.launches() == [], f"launched despite the hold\n{out}"
        assert rc == 0, out
        assert "maintenance hold present" in out, out

    def test_hold_created_during_backoff_prevents_the_next_launch(self, box: _Sandbox) -> None:
        box.set_codes([1])  # crash -> backoff 10 s * 0.5 = a 5 s window to create the hold
        proc = box.start(scale="0.5")
        try:
            deadline = time.monotonic() + 20
            while not box.launches():
                assert proc.poll() is None, "wrapper exited before its first launch"
                assert time.monotonic() < deadline, "first launch never happened"
                time.sleep(0.05)
            assert proc.poll() is None, "wrapper must be sleeping in backoff, not finished"
            box.create_hold()
            try:
                out, _ = proc.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                _kill_tree(proc)
                out, _ = proc.communicate()
                pytest.fail(f"wrapper still running after the hold appeared\n{out}")
        finally:
            _kill_tree(proc)
        assert len(box.launches()) == 1, f"relaunched despite the hold\n{out}"
        assert proc.returncode == 0, out
        assert "console crashed" in out and "maintenance hold present" in out, out


# ---------------------------------------------------------------------------------------
# 2a. Lock: real separate processes (cross-platform; msvcrt on the Windows runner)
# ---------------------------------------------------------------------------------------

_HOLDER = (
    "import sys;from pathlib import Path;"
    "from empirical_platform.shared.console_lifecycle import ConsoleInstanceLock;"
    "lock=ConsoleInstanceLock(Path(sys.argv[1]));lock.acquire();print('held',flush=True);"
    "sys.stdin.read()"
)
_PROBE = (
    "import sys;from pathlib import Path;"
    "from empirical_platform.shared.console_lifecycle import ("
    "ConsoleInstanceLock, ConsoleAlreadyRunningError)\n"
    "try:\n ConsoleInstanceLock(Path(sys.argv[1])).acquire()\n"
    "except ConsoleAlreadyRunningError as e:\n print('REFUSED', e);sys.exit(73)\n"
    "print('ACQUIRED');sys.exit(0)"
)


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("EMPIRICAL_PLATFORM")}
    env["PYTHONPATH"] = str(REPO / "src")
    return env


@pytest.fixture
def lock_holder(tmp_path: Path) -> Iterator[Path]:
    holder = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", _HOLDER, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env=_child_env(),
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held", "holder process failed to take the lock"
        yield tmp_path
    finally:
        holder.kill()
        holder.wait()


def test_a_second_os_process_cannot_take_the_lock_a_first_process_holds(
    lock_holder: Path,
) -> None:
    second = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _PROBE, str(lock_holder)],
        capture_output=True,
        text=True,
        env=_child_env(),
        timeout=60,
        check=False,
    )
    assert second.returncode == 73, (sys.platform, second.stdout, second.stderr)
    assert "REFUSED" in second.stdout
    with pytest.raises(ConsoleAlreadyRunningError):  # the in-process API agrees
        ConsoleInstanceLock(lock_holder).acquire()


def test_the_real_console_entrypoint_exits_73_without_touching_state(lock_holder: Path) -> None:
    before = sorted(p.name for p in lock_holder.rglob("*"))
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.operator_console",
            "--capability",
            "paper-exit",
            "--safety-directory",
            str(lock_holder),
            "--no-browser",
        ],
        capture_output=True,
        text=True,
        env=_child_env(),
        timeout=90,
        check=False,
    )
    assert result.returncode == console_lifecycle.EXIT_ALREADY_RUNNING == 73, (
        result.returncode,
        result.stdout,
        result.stderr,
    )
    assert "already holds" in result.stderr
    assert sorted(p.name for p in lock_holder.rglob("*")) == before  # no token/state created


# ---------------------------------------------------------------------------------------
# 2b. Port exclusivity
# ---------------------------------------------------------------------------------------


class _Handler(web.WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def _assert_refused(error: OSError) -> None:
    if sys.platform == "win32":
        assert getattr(error, "winerror", None) in (10013, 10048), error


def test_a_second_bind_cannot_take_the_port_of_a_live_server() -> None:
    first = web.ThreadingWSGIServer(("127.0.0.1", 0), _Handler)  # real server_bind logic
    try:
        port = first.server_port
        with pytest.raises(OSError) as refused:
            web.ThreadingWSGIServer(("127.0.0.1", port), _Handler)
        _assert_refused(refused.value)
        # a raw socket with SO_REUSEADDR (the Windows hijack vector) is refused too
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with pytest.raises(OSError) as hijack:
                raw.bind(("127.0.0.1", port))
            _assert_refused(hijack.value)
        finally:
            raw.close()
    finally:
        first.server_close()


@pytest.mark.skipif(sys.platform != "win32", reason="SO_EXCLUSIVEADDRUSE exists only on Windows")
def test_windows_exclusive_addr_use_is_set_on_the_live_listener() -> None:
    server = web.ThreadingWSGIServer(("127.0.0.1", 0), _Handler)
    try:
        option = socket.SO_EXCLUSIVEADDRUSE  # type: ignore[attr-defined]
        assert server.socket.getsockopt(socket.SOL_SOCKET, option) != 0
        assert server.allow_reuse_address is False
    finally:
        server.server_close()


@pytest.mark.parametrize(("platform", "expect_exclusive"), [("win32", True), ("linux", False)])
def test_server_bind_picks_exclusive_use_only_on_windows_and_never_reuseaddr_there(
    monkeypatch: pytest.MonkeyPatch, platform: str, expect_exclusive: bool
) -> None:
    calls: list[tuple[int, int, int]] = []

    class FakeSocket:
        def setsockopt(self, level: int, option: int, value: int) -> None:
            calls.append((level, option, value))

    monkeypatch.setattr(web.socket, "SO_EXCLUSIVEADDRUSE", -5, raising=False)
    monkeypatch.setattr(web, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(web.WSGIServer, "server_bind", lambda self: None)
    server = web.ThreadingWSGIServer.__new__(web.ThreadingWSGIServer)
    server.socket = FakeSocket()  # type: ignore[assignment]
    server.server_bind()
    assert calls == ([(socket.SOL_SOCKET, -5, 1)] if expect_exclusive else [])
    assert all(option != socket.SO_REUSEADDR for _level, option, _value in calls)
    assert web.reuse_address_allowed(platform) is (not expect_exclusive)


# ---------------------------------------------------------------------------------------
# 3. Deployment stop vs autostart: hold ordering and one shared hold path
# ---------------------------------------------------------------------------------------

_FLAT = deploy.BrokerSnapshot(
    account_status="ACTIVE",
    trading_blocked=False,
    position_count=0,
    open_order_count=0,
    unknown_order_count=0,
)
_STEP_FUNCTIONS = (
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


def _config(tmp_path: Path) -> deploy.DeployConfig:
    placeholder = PostgreSQLConfigSnapshot(
        host="localhost", port=55555, database="placeholder_test", user="empirical"
    )
    return deploy.DeployConfig(
        repo_path=Path(),
        expected_release_head="deadbeef",
        manifest_path=tmp_path / "safety" / "personal-paper.json",
        backup_root=tmp_path,
        pg_bin=Path(),
        store_b_config=placeholder,
        store_c_config=placeholder,
        migration_sql_path=Path("migration.sql"),
        console_host="127.0.0.1",
        console_port=8189,
        console_pid=4242,
        shutdown_timeout_seconds=1.0,
        startup_timeout_seconds=1.0,
    )


def test_the_hold_exists_before_any_stop_signal_and_through_step_14(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(tmp_path)
    hold = console_lifecycle.hold_path(cfg.manifest_path.parent)
    events: list[tuple[str, bool]] = []  # (event, hold exists at that instant)
    real_create = console_lifecycle.create_maintenance_hold

    def spy_create(*args: object, **kwargs: object) -> bool:
        created = real_create(*args, **kwargs)  # type: ignore[arg-type]
        events.append(("hold-created" if created else "hold-kept", hold.exists()))
        return created

    monkeypatch.setattr(console_lifecycle, "create_maintenance_hold", spy_create)
    running = {4242: True}

    class Process:
        def is_running(self, pid: int) -> bool:
            return running.get(pid, False)

        def graceful_stop(self, pid: int, **_kwargs: object) -> None:
            events.append(("STOP-SIGNAL", hold.exists()))
            running[pid] = False

    class Network:
        def port_is_free(self, host: str, port: int) -> bool:
            del host, port
            return not running[4242]

        def owning_pid(self, host: str, port: int) -> int | None:
            del host, port
            return 4242 if running[4242] else None

    class Broker:
        def account_snapshot(self) -> deploy.BrokerSnapshot:
            return _FLAT

    ports = deploy.Ports(broker=Broker(), process=Process(), network=Network())  # type: ignore[arg-type]

    def make(step_name: str) -> Callable[..., object]:
        def fn(*_args: object, **_kwargs: object) -> object:
            events.append((f"start:{step_name}", hold.exists()))
            if step_name == deploy.STEP_4_BACKUP:
                return ("ok", tmp_path)
            if step_name == deploy.STEP_12_RECOVERY_START:
                return ("ok", 1234)
            return "ok"

        return fn

    for step, fn_name in zip(deploy.STEP_ORDER, _STEP_FUNCTIONS, strict=True):
        if fn_name != "step5_shutdown":  # step 5 stays REAL
            monkeypatch.setattr(deploy, fn_name, make(step))

    journal_path = tmp_path / "journal.json"
    launch = deploy.RecoveryConsoleLaunch(executable=("x",), env={}, log_path=journal_path)
    journal = deploy.run_deployment(
        cfg, ports, deploy.DeploymentJournal.load_or_new(journal_path), journal_path, launch=launch
    )
    assert deploy.STEP_14_STOP_BEFORE_ACTIVE in journal.completed_steps()

    names = [name for name, _present in events]
    assert names.count("STOP-SIGNAL") == 1, events
    stop_at = names.index("STOP-SIGNAL")
    assert "hold-created" in names[:stop_at], f"hold must be created before the stop: {events}"
    assert events[stop_at][1] is True, f"hold absent at the stop signal: {events}"
    started = [event for event in events if event[0].startswith("start:")]
    assert len(started) == 13  # every step but the real step 5
    later = started[4:]  # steps 6..14 run after the stop
    assert len(later) == 9 and all(present for _name, present in later), events
    assert hold.exists()


def _powershell_hold_parts() -> tuple[str, ...]:
    text = WRAPPER.read_text(encoding="utf-8")
    match = re.search(
        r'^\$HoldFile = Join-Path \$LocalAppData "([^"]+)"\s*$', text, flags=re.MULTILINE
    )
    assert match is not None, "wrapper no longer defines $HoldFile from $LocalAppData"
    assert "$LocalAppData = $Env:LOCALAPPDATA" in text
    return PureWindowsPath(match.group(1)).parts


def test_wrapper_console_and_deploy_tool_resolve_the_same_hold_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "AppData" / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    manifest = database_safety.manifest_path()  # the default both the console and deploy use
    # console gate: `arguments.safety_directory or manifest_path().parent`
    console_hold = console_lifecycle.hold_path(manifest.parent)
    # deploy tool: creates the hold beside the configured manifest (default = the same file)
    created = deploy._ensure_maintenance_hold(SimpleNamespace(manifest_path=manifest))  # type: ignore[arg-type]  # noqa: SLF001
    assert created is True and console_hold.is_file()
    assert console_lifecycle.maintenance_hold_active(manifest.parent)
    # the PowerShell wrapper's literal, relative to %LOCALAPPDATA%
    assert _powershell_hold_parts() == HOLD_RELATIVE
    assert console_hold.relative_to(local).parts == HOLD_RELATIVE
    # deploy's production default manifest lives in the same safety directory
    assert deploy._REAL_MANIFEST_PATH.parent.parts[-2:] == HOLD_RELATIVE[:2]  # noqa: SLF001
