"""MILESTONE-086 -- the launcher binds to loopback only, and the local server really serves."""

from __future__ import annotations

import http.client
import threading

import pytest

from empirical_platform.entrypoints._operator_console_web import (
    Router,
    SecuritySession,
    html_response,
    serve,
)
from empirical_platform.entrypoints.operator_console import DEFAULT_HOST, DEFAULT_PORT, _loopback


def test_the_default_binding_is_loopback() -> None:
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 8086
    assert _loopback("127.0.0.1") == "127.0.0.1"
    assert _loopback("::1") == "::1"


_ALL_INTERFACES = "0.0.0.0"  # noqa: S104 - asserted to be REFUSED, never bound


@pytest.mark.parametrize(
    "host", [_ALL_INTERFACES, "192.168.1.10", "10.0.0.5", "example.com", "", "localhost"]
)
def test_any_non_loopback_host_is_refused_before_anything_starts(host: str) -> None:
    with pytest.raises(SystemExit) as refused:
        _loopback(host)
    assert "REFUSED" in str(refused.value)


def test_the_threaded_local_server_serves_and_stops() -> None:
    router = Router(SecuritySession())
    router.get("/ping", lambda request, csrf: html_response("<p>pong</p>"))
    with serve(router, host="127.0.0.1", port=0) as server:
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True
        )
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("GET", "/ping")
            response = connection.getresponse()
            body = response.read().decode()
            assert response.status == 200 and "pong" in body
            assert response.getheader("X-Frame-Options") == "DENY"
            assert response.getheader("Content-Security-Policy", "").startswith(
                "default-src 'none'"
            )
            connection.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
        assert server.server_address[0] == "127.0.0.1"


class TestTheReconcilerIsStoppedAndJoined:
    def test_stop_joins_and_a_pass_in_flight_completes_first(self) -> None:
        import time

        from empirical_platform.entrypoints.operator_console import _Reconciler

        events: list[str] = []

        def slow_refresh() -> None:
            events.append("start")
            time.sleep(0.3)
            events.append("end")

        reconciler = _Reconciler(slow_refresh, 0.05)
        reconciler.start()
        deadline = time.monotonic() + 5
        while "start" not in events and time.monotonic() < deadline:
            time.sleep(0.01)
        assert "start" in events
        assert reconciler.stop(timeout=5) is True  # returns only once the thread has ended
        assert not reconciler.is_alive()
        assert events[-1] == "end"  # the pass in flight finished before stop() returned
        passes_after_stop = reconciler.passes
        time.sleep(0.3)
        assert reconciler.passes == passes_after_stop  # nothing runs after the join

    def test_stop_before_the_first_pass_never_runs_one(self) -> None:
        from empirical_platform.entrypoints.operator_console import _Reconciler

        calls: list[int] = []
        reconciler = _Reconciler(lambda: calls.append(1), 10.0)
        reconciler.start()
        assert reconciler.stop(timeout=5) is True
        assert calls == [] and reconciler.passes == 0

    def test_the_launcher_stops_the_reconciler_before_the_runtime_closes(self) -> None:
        """Source order, parsed: `reconciler.stop()` sits inside the `serve` block's `finally`,
        which runs before the `simulation_console_runtime` context (service + lock) exits."""
        import ast
        from pathlib import Path

        source = Path("src/empirical_platform/entrypoints/operator_console.py").read_text("utf-8")
        tree = ast.parse(source)
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        text = ast.unparse(main)
        runtime_with = text.index("with simulation_console_runtime(")
        serve_with = text.index("with serve(")
        stop_call = text.index("reconciler.stop()")
        assert runtime_with < serve_with < stop_call
        # The stop is in a `finally` of a try nested in the serve block, i.e. before both exits.
        assert "finally:" in text[serve_with:stop_call]
