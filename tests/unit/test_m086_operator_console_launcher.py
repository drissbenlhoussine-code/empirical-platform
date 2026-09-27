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
