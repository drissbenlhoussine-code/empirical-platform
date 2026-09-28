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
        reconciler.stop()  # returns only once the thread has ended
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
        reconciler.stop()
        assert not reconciler.is_alive()
        assert calls == [] and reconciler.passes == 0

    def test_stop_waits_for_a_blocked_refresh_however_long_it_takes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A refresh blocked in flight: stop() does not return -- and so nothing after it can
        run -- until the refresh is released; the report interval only prints, it never permits
        the join to give up."""
        import time

        from empirical_platform.entrypoints.operator_console import _Reconciler

        started = threading.Event()
        release = threading.Event()
        events: list[str] = []

        def blocked_refresh() -> None:
            started.set()
            release.wait()
            events.append("refresh finished")

        reconciler = _Reconciler(blocked_refresh, 0.01)
        reconciler.start()
        assert started.wait(5)

        def stop_then_tear_down() -> None:
            reconciler.stop(report_every=0.05)
            events.append("teardown")

        stopper = threading.Thread(target=stop_then_tear_down, daemon=True)
        stopper.start()
        time.sleep(0.5)  # far longer than several report intervals
        assert stopper.is_alive() and reconciler.is_alive()
        assert events == []  # no teardown while the refresh is blocked
        assert "nothing is closed until it finishes" in capsys.readouterr().err
        release.set()
        stopper.join(timeout=5)
        assert not stopper.is_alive() and not reconciler.is_alive()
        assert events == ["refresh finished", "teardown"]

    def test_the_runtime_closes_only_after_the_blocked_refresh_completes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The launcher's real `main()` with a fake runtime, application and server: a refresh
        is blocked in flight when Ctrl+C arrives; the runtime (service + state lock) is closed
        only after that refresh has finished and the thread has terminated."""
        import contextlib
        import time
        from collections.abc import Iterator
        from pathlib import Path

        from empirical_platform.entrypoints import operator_console as launcher

        started = threading.Event()
        release = threading.Event()
        events: list[str] = []

        class FakeService:
            def refresh_executions(self) -> None:
                events.append("refresh start")
                started.set()
                release.wait()
                events.append("refresh end")

        class FakeRuntime:
            service = FakeService()

        @contextlib.contextmanager
        def fake_runtime(*, state_dir: Path) -> Iterator[FakeRuntime]:
            try:
                yield FakeRuntime()
            finally:
                events.append("runtime closed")

        class FakeServer:
            server_port = 0

            def serve_forever(self, poll_interval: float) -> None:
                assert started.wait(5)  # the pass is in flight when the operator presses Ctrl+C
                raise KeyboardInterrupt

        @contextlib.contextmanager
        def fake_serve(application: object, *, host: str, port: int) -> Iterator[FakeServer]:
            try:
                yield FakeServer()
            finally:
                events.append("server closed")

        # Stacked-milestone evolution (M087): the launcher composes the exit-capable runtime.
        monkeypatch.setattr(launcher, "simulation_exit_console_runtime", fake_runtime)
        monkeypatch.setattr(launcher, "build_application", lambda runtime, security: object())
        monkeypatch.setattr(launcher, "serve", fake_serve)

        outcome: list[int] = []
        main_thread = threading.Thread(
            target=lambda: outcome.append(
                launcher.main(["--no-browser", "--reconcile-every", "0.01"])
            ),
            daemon=True,
        )
        main_thread.start()
        assert started.wait(5)
        time.sleep(0.5)
        assert main_thread.is_alive()
        assert events == ["refresh start"]  # neither the server nor the runtime has closed
        release.set()
        main_thread.join(timeout=10)
        assert not main_thread.is_alive() and outcome == [0]
        assert events == ["refresh start", "refresh end", "server closed", "runtime closed"]

    def test_the_launcher_stops_the_reconciler_before_the_runtime_closes(self) -> None:
        """Source order, parsed. MILESTONE-088 factored the serve/reconciler block that used
        to sit inline in `main` into `_serve_with_reconciler`, shared with the PAPER launch
        path, so the property is now checked in two parts: `main` calls it from INSIDE the
        `simulation_exit_console_runtime` block (so the runtime cannot close first), and
        `_serve_with_reconciler` itself still stops the reconciler in a `finally` inside the
        `serve` block (before the server closes) and again in an outer `finally` (before ITS
        own caller can proceed) -- exactly the same two-`finally` shape as before, just in its
        own function. No branch closes anyway, in either function."""
        import ast
        from pathlib import Path

        source = Path("src/empirical_platform/entrypoints/operator_console.py").read_text("utf-8")
        tree = ast.parse(source)
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        main_text = ast.unparse(main)
        # MILESTONE-088's PAPER branch calls _serve_with_reconciler too, and returns earlier
        # in the function body than the SIMULATION branch below it -- so the NEXT occurrence
        # after `with simulation_exit_console_runtime(`, not the first anywhere, is the one
        # that must be inside it.
        runtime_with = main_text.index("with simulation_exit_console_runtime(")
        serve_call = main_text.index("_serve_with_reconciler(", runtime_with)
        assert runtime_with < serve_call  # the call happens INSIDE the runtime's `with` block

        helper = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_serve_with_reconciler"
        )
        text = ast.unparse(helper)
        serve_with = text.index("with serve(")
        stop_call = text.index("reconciler.stop()")
        assert serve_with < stop_call
        # The stop is in a `finally` of a try nested in the serve block, i.e. before both exits.
        assert "finally:" in text[serve_with:stop_call]
        assert text.count("reconciler.stop()") == 2  # ... and once more in the outer finally
        assert "closing anyway" not in source
        stop = next(
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "stop"
        )
        assert "while self.is_alive()" in ast.unparse(stop)  # join until terminated
