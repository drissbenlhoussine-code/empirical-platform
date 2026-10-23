"""MILESTONE-098: unit coverage for `shared.console_control` (the token file read/write/
remove contract) and `_operator_console_web.Router.service_post` (the dispatch rule that
lets exactly one route skip CSRF/session cookie handling for a machine-to-machine caller).

Real OS process/port mechanics and the real console's `/control/shutdown` route wiring are
covered by `tests/integration/test_m098_windows_console_shutdown.py` (Windows-only, real
subprocesses) and by the updated dummy console in
`tests/integration/test_v1_personal_paper_deploy_postgres.py`. This file is fakes/tmp_path
only -- no real socket, no real subprocess.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from empirical_platform.entrypoints import operator_console
from empirical_platform.entrypoints._operator_console_web import (
    Request,
    Response,
    Router,
    SecuritySession,
    html_response,
)
from empirical_platform.shared import console_control

# ---------------------------------------------------------------------------------------
# write_control_token / read_control_token / remove_control_token
# ---------------------------------------------------------------------------------------


def test_write_then_read_round_trips_with_matching_identity(tmp_path: Path) -> None:
    token = console_control.write_control_token(
        tmp_path, pid=4242, port=8189, capability="paper-exit"
    )
    record = console_control.read_control_token(
        tmp_path, port=8189, expected_capability="paper-exit", expected_pid=4242
    )
    assert record.token == token
    assert record.pid == 4242
    assert record.port == 8189
    assert record.capability == "paper-exit"


def test_read_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(console_control.ControlTokenError, match="no readable control token"):
        console_control.read_control_token(
            tmp_path, port=8189, expected_capability="paper-exit", expected_pid=4242
        )


def test_read_refuses_malformed_json(tmp_path: Path) -> None:
    path = console_control.control_token_path(tmp_path, port=8189)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(console_control.ControlTokenError, match="no readable control token"):
        console_control.read_control_token(
            tmp_path, port=8189, expected_capability="paper-exit", expected_pid=4242
        )


def test_read_refuses_a_missing_field(tmp_path: Path) -> None:
    path = console_control.control_token_path(tmp_path, port=8189)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"pid": 4242, "port": 8189}), encoding="utf-8")
    with pytest.raises(console_control.ControlTokenError, match="malformed"):
        console_control.read_control_token(
            tmp_path, port=8189, expected_capability="paper-exit", expected_pid=4242
        )


def test_read_refuses_a_capability_mismatch(tmp_path: Path) -> None:
    console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="simulation")
    with pytest.raises(console_control.ControlTokenError, match="capability"):
        console_control.read_control_token(
            tmp_path, port=8189, expected_capability="paper-exit", expected_pid=4242
        )


def test_read_refuses_a_port_field_mismatch(tmp_path: Path) -> None:
    """Simulates manual tampering: the file lives at the path for port 8189 (so it IS the
    file this port's caller would read) but its own recorded `port` field disagrees."""
    path = console_control.control_token_path(tmp_path, port=8189)
    path.parent.mkdir(parents=True)
    payload = {
        "pid": 4242,
        "port": 9999,
        "capability": "paper-exit",
        "started_utc": "2026-01-01T00:00:00+00:00",
        "token": "deadbeef",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(console_control.ControlTokenError, match="different port"):
        console_control.read_control_token(
            tmp_path, port=8189, expected_capability="paper-exit", expected_pid=4242
        )


def test_read_refuses_a_pid_mismatch_defeating_pid_reuse(tmp_path: Path) -> None:
    """The caller must independently confirm, at the OS level, which PID really owns the
    port right now, and pass THAT as `expected_pid` -- a stale file naming an old PID that
    has since been reused by an unrelated process must never be trusted."""
    console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    with pytest.raises(console_control.ControlTokenError, match="PID reuse"):
        console_control.read_control_token(
            tmp_path, port=8189, expected_capability="paper-exit", expected_pid=9999
        )


def test_the_raw_token_never_appears_in_any_mismatch_error_message(tmp_path: Path) -> None:
    token = console_control.write_control_token(
        tmp_path, pid=4242, port=8189, capability="paper-exit"
    )
    for expected_capability, expected_pid in (("simulation", 4242), ("paper-exit", 1)):
        with pytest.raises(console_control.ControlTokenError) as excinfo:
            console_control.read_control_token(
                tmp_path,
                port=8189,
                expected_capability=expected_capability,
                expected_pid=expected_pid,
            )
        assert token not in str(excinfo.value)


def test_remove_control_token_deletes_the_file(tmp_path: Path) -> None:
    console_control.write_control_token(tmp_path, pid=4242, port=8189, capability="paper-exit")
    path = console_control.control_token_path(tmp_path, port=8189)
    assert path.exists()
    console_control.remove_control_token(tmp_path, port=8189)
    assert not path.exists()


def test_remove_control_token_is_a_no_op_when_nothing_exists(tmp_path: Path) -> None:
    console_control.remove_control_token(tmp_path, port=8189)  # must not raise


def test_different_ports_use_different_files_and_do_not_collide(tmp_path: Path) -> None:
    console_control.write_control_token(tmp_path, pid=1, port=8189, capability="paper-exit")
    console_control.write_control_token(tmp_path, pid=2, port=9000, capability="paper-exit")
    first = console_control.read_control_token(
        tmp_path, port=8189, expected_capability="paper-exit", expected_pid=1
    )
    second = console_control.read_control_token(
        tmp_path, port=9000, expected_capability="paper-exit", expected_pid=2
    )
    assert first.pid == 1
    assert second.pid == 2


def test_write_narrows_permissions_best_effort_and_never_raises_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permission narrowing is defense-in-depth, not the primary authentication factor (the
    secret token is). A narrowing failure must never prevent the console from starting."""

    def _boom(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("icacls is not available in this sandbox")

    monkeypatch.setattr(console_control.subprocess, "run", _boom)
    monkeypatch.setattr(
        console_control.Path,
        "chmod",
        lambda self, mode: (_ for _ in ()).throw(OSError("chmod refused")),
    )
    token = console_control.write_control_token(
        tmp_path, pid=4242, port=8189, capability="paper-exit"
    )
    record = console_control.read_control_token(
        tmp_path, port=8189, expected_capability="paper-exit", expected_pid=4242
    )
    assert record.token == token


# ---------------------------------------------------------------------------------------
# Router.service_post: the dispatch rule the console's `/control/shutdown` route relies on.
# ---------------------------------------------------------------------------------------


def _wsgi_call(
    router: Router, *, method: str, path: str, headers: dict[str, str] | None = None
) -> tuple[str, list[tuple[str, str]], bytes]:
    environ: dict[str, object] = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": ""}
    for key, value in (headers or {}).items():
        environ[f"HTTP_{key.upper().replace('-', '_')}"] = value
    captured: dict[str, object] = {}

    def start_response(status: str, response_headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = response_headers

    body = b"".join(router(environ, start_response))
    return captured["status"], captured["headers"], body  # type: ignore[return-value]


def test_service_post_calls_the_handler_when_authorized() -> None:
    router = Router(SecuritySession())
    calls: list[str] = []

    def handler(request: Request, csrf: str) -> Response:
        del request, csrf
        calls.append("called")
        return html_response("<p>ok</p>")

    router.service_post("/control/shutdown", handler, authorize=lambda request: True)
    status, headers, body = _wsgi_call(router, method="POST", path="/control/shutdown")
    assert status == "200 OK"
    assert calls == ["called"]
    assert b"ok" in body
    assert not any(name == "Set-Cookie" for name, _ in headers)


def test_service_post_refuses_without_calling_the_handler_when_unauthorized() -> None:
    router = Router(SecuritySession())
    calls: list[str] = []

    def handler(request: Request, csrf: str) -> Response:
        del request, csrf
        calls.append("called")
        return html_response("<p>ok</p>")

    router.service_post("/control/shutdown", handler, authorize=lambda request: False)
    status, _headers, _body = _wsgi_call(router, method="POST", path="/control/shutdown")
    assert status == "401 Unauthorized"
    assert calls == []


def test_service_post_never_requires_a_csrf_token_or_session_cookie() -> None:
    """The caller is a local tool process, not a browser -- there is no session for it to
    carry a CSRF token in, unlike every other POST route this console serves."""
    router = Router(SecuritySession())

    def handler(request: Request, csrf: str) -> Response:
        del request, csrf
        return html_response("<p>ok</p>")

    seen_headers: list[dict[str, str]] = []

    def authorize(request: Request) -> bool:
        seen_headers.append(dict(request.headers))
        return request.headers.get("x-empirical-shutdown-token") == "right-token"

    router.service_post("/control/shutdown", handler, authorize=authorize)
    status, _headers, _body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": "right-token"},
    )
    assert status == "200 OK"
    assert "csrf_token" not in seen_headers[0]


# ---------------------------------------------------------------------------------------
# operator_console._install_shutdown_control: the real wiring, against a fake server
# object (no real socket -- real OS process/port mechanics are covered by the Windows-only
# integration file).
# ---------------------------------------------------------------------------------------


class _FakeServer:
    def __init__(self, port: int) -> None:
        self.server_port = port
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def test_install_shutdown_control_writes_a_token_naming_this_process(tmp_path: Path) -> None:
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability=operator_console.SHUTDOWN_CONTROL_CAPABILITY,
        expected_pid=operator_console.os.getpid(),
    )
    assert record.port == 8189


def test_install_shutdown_control_route_requires_the_exact_token(tmp_path: Path) -> None:
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]

    status, _headers, _body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": "definitely-wrong"},
    )
    assert status == "401 Unauthorized"
    assert server.shutdown_calls == 0


def test_install_shutdown_control_accepts_the_real_token_and_shuts_down_async(
    tmp_path: Path,
) -> None:
    router = Router(SecuritySession())
    server = _FakeServer(8189)
    operator_console._install_shutdown_control(router, server, safety_directory=tmp_path)  # type: ignore[arg-type]
    record = console_control.read_control_token(
        tmp_path,
        port=8189,
        expected_capability=operator_console.SHUTDOWN_CONTROL_CAPABILITY,
        expected_pid=operator_console.os.getpid(),
    )

    status, _headers, body = _wsgi_call(
        router,
        method="POST",
        path="/control/shutdown",
        headers={"X-Empirical-Shutdown-Token": record.token},
    )
    assert status == "202 Accepted"
    payload = json.loads(body)
    assert payload == {"accepted": True, "pid": operator_console.os.getpid()}

    # `server.shutdown()` is started on a background thread so the HTTP response can be
    # sent first (see the function's own docstring for why calling it synchronously, on
    # the same thread handling this request, would be the correct-but-irrelevant-here
    # deadlock case `BaseServer.shutdown()`'s own docs warn about).
    deadline = time.monotonic() + 2.0
    while server.shutdown_calls == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.shutdown_calls == 1
