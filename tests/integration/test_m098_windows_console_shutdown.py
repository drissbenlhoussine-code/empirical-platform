"""MILESTONE-098: Windows-specific, real-process coverage for the graceful-shutdown fix.

WHY A SEPARATE, WINDOWS-ONLY FILE. The M097 deployment attempt failed specifically on
Windows (`OSError: [WinError 87]` from `os.kill(pid, signal.CTRL_BREAK_EVENT)`), and the
root cause (`CTRL_BREAK_EVENT` cannot address a process group the caller did not itself
create) is a Windows-only OS primitive limitation -- there is nothing to regress-test on
POSIX. `tests/integration/test_v1_personal_paper_deploy_postgres.py` already carries one
real-subprocess test covering the "happy path" on whichever platform CI runs it on
(windows-latest for the repository-wide suite, ubuntu-latest for the Postgres job); this
file adds the scenarios that are specifically about Windows's process/port semantics and
would be meaningless or misleading on POSIX: an INDEPENDENTLY launched console (never a
child of this tool, the exact M097 shape), PID-reuse/incorrect-identity rejection, an
unrelated process occupying the port, a shutdown that never actually completes, and the
console's own enforcement of the authentication the deployment tool relies on.

Every test here is skipped outright on a non-Windows platform. No Postgres is used or
needed; every test spawns only small, disposable dummy "console" subprocesses this file
fully controls -- never the real operator console, never a real broker.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from tools import personal_paper_deploy as deploy

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

if sys.platform != "win32":
    pytest.skip(
        "Windows-only: this file covers CTRL_BREAK_EVENT/process-group semantics "
        "and the netstat-based port-owner query that replaced it.",
        allow_module_level=True,
    )

REPO_ROOT = Path(__file__).resolve().parents[2]
_PLACEHOLDER_DB = PostgreSQLConfigSnapshot(
    host="localhost", port=55555, database="placeholder_test", user="empirical"
)

# Identical in shape to the dummy console in test_v1_personal_paper_deploy_postgres.py --
# duplicated deliberately rather than imported (same reasoning as this repo's other
# cross-file constant duplications, e.g. M096's Store C fallback constants): a change to
# that file's fixture can never silently alter what THIS file exercises.
_DUMMY_CONSOLE_SCRIPT = """
import http.server, json, os, socketserver, sys, threading, time

from empirical_platform.shared import console_control

PORT = int(sys.argv[1])
SAFETY_DIRECTORY = sys.argv[2]
NEVER_EXITS = len(sys.argv) > 3 and sys.argv[3] == "never-exit"
PID = os.getpid()
TOKEN = console_control.write_control_token(
    __import__("pathlib").Path(SAFETY_DIRECTORY), pid=PID, port=PORT, capability="paper-exit"
)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<p>dummy console OK</p>"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/control/shutdown":
            self.send_response(404)
            self.end_headers()
            return
        presented = self.headers.get(console_control.CONTROL_TOKEN_HEADER, "")
        if presented != TOKEN:
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps({"accepted": True, "pid": PID}).encode("utf-8")
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        if not NEVER_EXITS:
            threading.Thread(
                target=lambda: (time.sleep(0.05), os._exit(0)), daemon=True
            ).start()
        # else: accepted, but deliberately never actually stops -- simulates a hang.

    def log_message(self, *args):
        pass

class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

with _Server(("127.0.0.1", PORT), Handler) as server:
    server.serve_forever(poll_interval=0.1)
"""


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _spawn(
    tmp_path: Path, script_name: str, script_body: str, *args: str, new_process_group: bool
) -> subprocess.Popen[bytes]:
    script_path = tmp_path / script_name
    script_path.write_text(script_body)
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if new_process_group else 0
    process = subprocess.Popen(  # noqa: S603 - fixed interpreter, fixed script this test wrote
        [sys.executable, str(script_path), *args], creationflags=creationflags
    )
    threading.Thread(target=process.wait, daemon=True).start()
    return process


def _cfg(*, tmp_path: Path, port: int, console_pid: int | None) -> deploy.DeployConfig:
    return deploy.DeployConfig(
        repo_path=REPO_ROOT,
        expected_release_head="unused",
        manifest_path=tmp_path / "manifest.json",
        backup_root=tmp_path,
        pg_bin=Path("."),
        store_b_config=_PLACEHOLDER_DB,
        store_c_config=_PLACEHOLDER_DB,
        migration_sql_path=REPO_ROOT / "tools" / deploy.MIGRATION_SQL_FILENAME,
        console_host="127.0.0.1",
        console_port=port,
        console_pid=console_pid,
        shutdown_timeout_seconds=5.0,
        startup_timeout_seconds=5.0,
    )


def test_an_independently_launched_console_can_be_stopped(tmp_path: Path) -> None:
    """The exact M097 shape: a console that is NOT this tool's own child and was NOT
    started with `CREATE_NEW_PROCESS_GROUP` -- precisely what made `CTRL_BREAK_EVENT`
    return `WinError 87`. The new mechanism does not care how the console was launched."""
    network = deploy.RealNetworkPort()
    process = deploy.RealProcessPort()
    port = _free_tcp_port()
    independent = _spawn(
        tmp_path,
        "dummy_independent.py",
        _DUMMY_CONSOLE_SCRIPT,
        str(port),
        str(tmp_path),
        new_process_group=False,
    )
    del independent
    deploy.wait_until(lambda: not network.port_is_free("127.0.0.1", port), timeout_seconds=5.0)
    real_pid = network.owning_pid("127.0.0.1", port)
    assert real_pid is not None

    cfg = _cfg(tmp_path=tmp_path, port=port, console_pid=real_pid)
    ports = deploy.Ports(broker=None, process=process, network=network)  # type: ignore[arg-type]
    detail = deploy.step5_shutdown(cfg, ports)
    assert "exited gracefully" in detail
    assert deploy.wait_until(lambda: network.port_is_free("127.0.0.1", port), timeout_seconds=5.0)


def test_a_deployment_managed_console_can_also_be_stopped(tmp_path: Path) -> None:
    """The contrasting case: launched the way `start_recovery_console` launches it (its
    own process group). Must work exactly the same way -- the mechanism no longer depends
    on this distinction at all."""
    network = deploy.RealNetworkPort()
    process = deploy.RealProcessPort()
    port = _free_tcp_port()
    managed = _spawn(
        tmp_path,
        "dummy_managed.py",
        _DUMMY_CONSOLE_SCRIPT,
        str(port),
        str(tmp_path),
        new_process_group=True,
    )
    del managed
    deploy.wait_until(lambda: not network.port_is_free("127.0.0.1", port), timeout_seconds=5.0)
    real_pid = network.owning_pid("127.0.0.1", port)
    assert real_pid is not None

    cfg = _cfg(tmp_path=tmp_path, port=port, console_pid=real_pid)
    ports = deploy.Ports(broker=None, process=process, network=network)  # type: ignore[arg-type]
    detail = deploy.step5_shutdown(cfg, ports)
    assert "exited gracefully" in detail


def test_step5_refuses_a_console_pid_that_does_not_own_the_port(tmp_path: Path) -> None:
    """Two REAL, independently running consoles. Asking to stop port A's console while
    claiming port B's PID must be refused -- and must leave BOTH processes running."""
    network = deploy.RealNetworkPort()
    port_a = _free_tcp_port()
    port_b = _free_tcp_port()
    _spawn(
        tmp_path,
        "dummy_a.py",
        _DUMMY_CONSOLE_SCRIPT,
        str(port_a),
        str(tmp_path),
        new_process_group=False,
    )
    _spawn(
        tmp_path,
        "dummy_b.py",
        _DUMMY_CONSOLE_SCRIPT,
        str(port_b),
        str(tmp_path),
        new_process_group=False,
    )
    deploy.wait_until(lambda: not network.port_is_free("127.0.0.1", port_a), timeout_seconds=5.0)
    deploy.wait_until(lambda: not network.port_is_free("127.0.0.1", port_b), timeout_seconds=5.0)
    pid_b = network.owning_pid("127.0.0.1", port_b)
    assert pid_b is not None

    cfg = _cfg(tmp_path=tmp_path, port=port_a, console_pid=pid_b)  # wrong PID for this port
    ports = deploy.Ports(broker=None, process=deploy.RealProcessPort(), network=network)  # type: ignore[arg-type]
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "does not match" in excinfo.value.reason
    assert not network.port_is_free("127.0.0.1", port_a)
    assert not network.port_is_free("127.0.0.1", port_b)


def test_step5_refuses_an_unrelated_process_occupying_the_port(tmp_path: Path) -> None:
    """Something real IS listening on the port, but it never wrote a control token (it is
    not our console at all) -- refuses rather than attempting anything against it.

    Deliberately an in-process listener (a background thread in THIS test process, not a
    separate subprocess): it is this scenario's OWN process identity, not the console's
    launch mechanics, that matters here, and a thread is immune to the venv-redirector
    parent/child PID split this file's other tests have to account for when spawning real
    consoles (see `test_an_independently_launched_console_can_be_stopped`'s docstring)."""
    network = deploy.RealNetworkPort()
    port = _free_tcp_port()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    # A larger backlog than the default 1: `port_is_free` itself probes with a real
    # connect-then-immediately-disconnect, and this test does that several times in a row
    # (the assert below, then again inside `step5_shutdown`, then again in the final
    # assert) -- a backlog of 1 can still show as "occupied" by a stale, unaccepted
    # connection from the PREVIOUS probe and falsely refuse the NEXT one.
    listener.listen(16)
    try:
        assert not network.port_is_free("127.0.0.1", port)

        cfg = _cfg(tmp_path=tmp_path, port=port, console_pid=None)
        ports = deploy.Ports(broker=None, process=deploy.RealProcessPort(), network=network)  # type: ignore[arg-type]
        with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
            deploy.step5_shutdown(cfg, ports)
        assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
        assert "no readable control token" in excinfo.value.reason
        assert not network.port_is_free("127.0.0.1", port)  # still listening, untouched
    finally:
        listener.close()


def test_step5_times_out_when_the_console_accepts_but_never_actually_stops(
    tmp_path: Path,
) -> None:
    network = deploy.RealNetworkPort()
    port = _free_tcp_port()
    _spawn(
        tmp_path,
        "never_exits.py",
        _DUMMY_CONSOLE_SCRIPT,
        str(port),
        str(tmp_path),
        "never-exit",
        new_process_group=False,
    )
    deploy.wait_until(lambda: not network.port_is_free("127.0.0.1", port), timeout_seconds=5.0)
    real_pid = network.owning_pid("127.0.0.1", port)
    assert real_pid is not None

    cfg = deploy.DeployConfig(
        repo_path=REPO_ROOT,
        expected_release_head="unused",
        manifest_path=tmp_path / "manifest.json",
        backup_root=tmp_path,
        pg_bin=Path("."),
        store_b_config=_PLACEHOLDER_DB,
        store_c_config=_PLACEHOLDER_DB,
        migration_sql_path=REPO_ROOT / "tools" / deploy.MIGRATION_SQL_FILENAME,
        console_host="127.0.0.1",
        console_port=port,
        console_pid=real_pid,
        shutdown_timeout_seconds=1.5,  # short on purpose: it really will never stop
        startup_timeout_seconds=5.0,
    )
    ports = deploy.Ports(broker=None, process=deploy.RealProcessPort(), network=network)  # type: ignore[arg-type]
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "did not exit" in excinfo.value.reason


def test_the_consoles_own_route_rejects_a_missing_or_wrong_token_and_keeps_running(
    tmp_path: Path,
) -> None:
    """Independent of the deployment tool entirely: a raw HTTP request with no token, or
    the wrong token, must be refused by the console itself, and the console must still be
    running and answering afterwards."""
    network = deploy.RealNetworkPort()
    port = _free_tcp_port()
    _spawn(
        tmp_path,
        "dummy_auth.py",
        _DUMMY_CONSOLE_SCRIPT,
        str(port),
        str(tmp_path),
        new_process_group=False,
    )
    deploy.wait_until(lambda: not network.port_is_free("127.0.0.1", port), timeout_seconds=5.0)

    import urllib.error
    import urllib.request

    for headers in ({}, {"X-Empirical-Shutdown-Token": "definitely-wrong"}):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/control/shutdown",
            method="POST",
            headers=headers,
            data=b"",
        )
        try:
            urllib.request.urlopen(request, timeout=5)  # noqa: S310
            raise AssertionError("expected HTTP 401")
        except urllib.error.HTTPError as error:
            assert error.code == 401

    status, body = network.http_get(f"http://127.0.0.1:{port}/", timeout=5.0)
    assert status == 200 and "dummy console OK" in body


def test_step5_refuses_a_control_token_file_planted_as_a_symlink(tmp_path: Path) -> None:
    """MILESTONE-098 SECURITY HARDENING: a real running console, but its control-token file
    has been replaced (e.g. by a lower-privileged co-resident process, before the console
    started) with a symlink to an attacker-controlled file. The deployment tool must refuse
    outright rather than follow it -- and the real console, which already wrote its OWN
    token successfully before this test plants the symlink over the read PATH the
    deployment tool uses, must still be left running untouched."""
    network = deploy.RealNetworkPort()
    port = _free_tcp_port()
    _spawn(
        tmp_path,
        "dummy_symlink.py",
        _DUMMY_CONSOLE_SCRIPT,
        str(port),
        str(tmp_path),
        new_process_group=False,
    )
    deploy.wait_until(lambda: not network.port_is_free("127.0.0.1", port), timeout_seconds=5.0)
    real_pid = network.owning_pid("127.0.0.1", port)
    assert real_pid is not None

    token_path = tmp_path / "console-control" / f"paper-exit-{port}.json"
    deploy.wait_until(lambda: token_path.exists(), timeout_seconds=5.0)
    decoy = tmp_path / "decoy.json"
    decoy.write_text(token_path.read_text(encoding="utf-8"), encoding="utf-8")
    token_path.unlink()
    try:
        token_path.symlink_to(decoy)
    except (OSError, NotImplementedError):
        pytest.skip("this environment does not permit creating symlinks")

    cfg = _cfg(tmp_path=tmp_path, port=port, console_pid=real_pid)
    ports = deploy.Ports(broker=None, process=deploy.RealProcessPort(), network=network)  # type: ignore[arg-type]
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "symlink" in excinfo.value.reason
    assert not network.port_is_free("127.0.0.1", port)  # the real console is untouched


def test_step5_refuses_a_stale_token_file_from_a_different_earlier_process(
    tmp_path: Path,
) -> None:
    """A real running console, but the on-disk token file at its own path has been
    overwritten (simulating a leftover from an earlier, now-dead process that happened to
    reuse this port number before the OS reassigned it) to claim the SAME PID but a
    start-time fingerprint that cannot possibly belong to the process actually running
    now. Must be refused, and the real console left running."""
    network = deploy.RealNetworkPort()
    port = _free_tcp_port()
    _spawn(
        tmp_path,
        "dummy_stale.py",
        _DUMMY_CONSOLE_SCRIPT,
        str(port),
        str(tmp_path),
        new_process_group=False,
    )
    deploy.wait_until(lambda: not network.port_is_free("127.0.0.1", port), timeout_seconds=5.0)
    real_pid = network.owning_pid("127.0.0.1", port)
    assert real_pid is not None

    token_path = tmp_path / "console-control" / f"paper-exit-{port}.json"
    deploy.wait_until(lambda: token_path.exists(), timeout_seconds=5.0)
    import json as _json

    payload = _json.loads(token_path.read_text(encoding="utf-8"))
    payload["start_fingerprint"] = "a fingerprint from a process that is not really running"
    token_path.write_text(_json.dumps(payload), encoding="utf-8")

    cfg = _cfg(tmp_path=tmp_path, port=port, console_pid=real_pid)
    ports = deploy.Ports(broker=None, process=deploy.RealProcessPort(), network=network)  # type: ignore[arg-type]
    with pytest.raises(deploy.DeploymentBlockedError) as excinfo:
        deploy.step5_shutdown(cfg, ports)
    assert excinfo.value.step == deploy.STEP_5_SHUTDOWN
    assert "fingerprint" in excinfo.value.reason
    assert not network.port_is_free("127.0.0.1", port)  # the real console is untouched


def _run_dumb_tcp_relay(listen_sock: socket.socket, target_host: str, target_port: int) -> None:
    """A byte-for-byte TCP relay that never parses HTTP and adds NO header of any kind --
    the realistic worst-case stand-in for Tailscale `serve`/`funnel` or a transparent
    reverse proxy that merely forwards raw bytes between a remote peer and this
    loopback-bound console. Unlike a proxy that adds `X-Forwarded-*` headers (already
    covered by `test_m098_console_shutdown_control.py`'s unit tests), THIS relay gives the
    console nothing to detect at the HTTP layer at all: its own connection to the console is
    itself on loopback, so `REMOTE_ADDR` looks exactly like a genuine local caller's."""
    while True:
        try:
            client, _ = listen_sock.accept()
        except OSError:
            return

        def _pump(src: socket.socket, dst: socket.socket) -> None:
            try:
                while True:
                    chunk = src.recv(65536)
                    if not chunk:
                        break
                    dst.sendall(chunk)
            except OSError:
                pass
            finally:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        upstream = socket.create_connection((target_host, target_port))
        threading.Thread(target=_pump, args=(client, upstream), daemon=True).start()
        threading.Thread(target=_pump, args=(upstream, client), daemon=True).start()


def test_step5_shutdown_route_still_refuses_through_a_header_stripping_tcp_relay(
    tmp_path: Path,
) -> None:
    """MILESTONE-098 FINAL HARDENING: practically verifies isolation from Tailscale/a
    reverse proxy in the WORST case -- a relay that forwards every byte verbatim and adds
    NO forwarding header at all. The console's `REMOTE_ADDR`/forwarding-header checks
    cannot distinguish this relay's own loopback connection from a genuine local caller, so
    the ONLY thing standing between a remote peer reached through it and this route is the
    per-instance secret token, which is never sent over any network. This is a REAL TCP
    relay and a REAL running dummy console -- not a request-object-level simulation."""
    network = deploy.RealNetworkPort()
    console_port = _free_tcp_port()
    _spawn(
        tmp_path,
        "dummy_relay_target.py",
        _DUMMY_CONSOLE_SCRIPT,
        str(console_port),
        str(tmp_path),
        new_process_group=False,
    )
    deploy.wait_until(
        lambda: not network.port_is_free("127.0.0.1", console_port), timeout_seconds=5.0
    )

    relay_port = _free_tcp_port()
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen_sock.bind(("127.0.0.1", relay_port))
    listen_sock.listen(16)
    threading.Thread(
        target=_run_dumb_tcp_relay, args=(listen_sock, "127.0.0.1", console_port), daemon=True
    ).start()

    import urllib.error
    import urllib.request

    try:
        for headers in ({}, {"X-Empirical-Shutdown-Token": "definitely-wrong"}):
            request = urllib.request.Request(
                f"http://127.0.0.1:{relay_port}/control/shutdown",
                method="POST",
                headers=headers,
                data=b"",
            )
            try:
                urllib.request.urlopen(request, timeout=5)  # noqa: S310
                raise AssertionError("expected HTTP 401 through the header-stripping relay")
            except urllib.error.HTTPError as error:
                assert error.code == 401
    finally:
        listen_sock.close()

    # The console is still running and answering directly, entirely unaffected.
    status, body = network.http_get(f"http://127.0.0.1:{console_port}/", timeout=5.0)
    assert status == 200 and "dummy console OK" in body
