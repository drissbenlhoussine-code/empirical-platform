"""M100 review follow-ups: Host-header refusal and the submit-time working-order guard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from tests.unit._m085_fakes import FakeBroker, FakeKillSwitch, FakeMarketData

from empirical_platform.entrypoints._operator_console_web import (
    Router,
    SecuritySession,
    _host_header_is_loopback,
    html_response,
)
from empirical_platform.shared.brokerage.paper_time import PaperTimeReading, PaperTimeWindow
from empirical_platform.usecases import paper_execution

_NOW = datetime(2026, 11, 6, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("127.0.0.1:8189", True),
        ("localhost:8086", True),
        ("[::1]:8086", True),
        ("LOCALHOST", True),
        (None, True),
        ("evil.example:8086", False),
        ("127.0.0.1.evil.example", False),
        ("localhost.evil.example:80", False),
        ("", False),
    ],
)
def test_host_header_classification(host: str | None, allowed: bool) -> None:
    assert _host_header_is_loopback(host) is allowed


def _call(router: Router, host: str | None) -> str:
    environ: dict[str, Any] = {"REQUEST_METHOD": "GET", "PATH_INFO": "/ping"}
    if host is not None:
        environ["HTTP_HOST"] = host
    status: list[str] = []
    body = router(environ, lambda s, _h: status.append(s))
    return status[0] + "|" + b"".join(body).decode()


def test_a_rebound_host_never_reaches_a_handler_or_gets_a_csrf_token() -> None:
    router = Router(SecuritySession())
    router.get("/ping", lambda request, csrf: html_response(f"<p>{csrf}</p>"))
    rebound = _call(router, "evil.example:8086")
    assert rebound.startswith("421")
    assert "<p>" not in rebound
    assert _call(router, "127.0.0.1:8086").startswith("200")


@dataclass
class _Order:
    quantity: str
    symbol: str = "AAPL"


def test_a_working_order_is_folded_into_exposure_at_submit_time() -> None:
    class _Clock:
        def read(self) -> PaperTimeReading:
            return PaperTimeReading(_NOW, 0.0)

    broker = FakeBroker()
    broker.open_orders = (_Order("1"), _Order("2.4"))
    evidence = paper_execution._gather(
        broker=broker,  # type: ignore[arg-type]
        market_data=FakeMarketData(),  # type: ignore[arg-type]
        kill_switch=FakeKillSwitch(),  # type: ignore[arg-type]
        symbol="AAPL",
        snapshot_id="SNAP",
        at=_NOW,
        timing=PaperTimeWindow(_Clock()),
    )
    assert evidence.existing_position_quantity == 1 + 3  # ceil(2.4) rounds up, fail closed


def test_no_working_order_keeps_exposure_at_the_held_quantity() -> None:
    class _Clock:
        def read(self) -> PaperTimeReading:
            return PaperTimeReading(_NOW, 0.0)

    evidence = paper_execution._gather(
        broker=FakeBroker(),  # type: ignore[arg-type]
        market_data=FakeMarketData(),  # type: ignore[arg-type]
        kill_switch=FakeKillSwitch(),  # type: ignore[arg-type]
        symbol="AAPL",
        snapshot_id="SNAP",
        at=_NOW,
        timing=PaperTimeWindow(_Clock()),
    )
    assert evidence.existing_position_quantity == 0


@pytest.mark.parametrize(
    ("configured", "host", "allowed"),
    [
        ("", "desktop.tail1234.ts.net", False),
        ("desktop.tail1234.ts.net", "desktop.tail1234.ts.net", True),
        ("desktop.tail1234.ts.net", "DESKTOP.tail1234.ts.net:443", True),
        ("desktop.tail1234.ts.net, other.example", "other.example", True),
        ("desktop.tail1234.ts.net", "evil.example", False),
        ("*.ts.net", "desktop.tail1234.ts.net", False),  # no wildcards
        ("10.0.0.0/8", "10.1.2.3", False),  # no ranges
        ("desktop.tail1234.ts.net", "desktop.tail1234.ts.net.evil.example", False),
    ],
)
def test_the_host_allowlist_is_exact_opt_in_and_never_wildcard(
    monkeypatch: pytest.MonkeyPatch, configured: str, host: str, allowed: bool
) -> None:
    from empirical_platform.entrypoints._operator_console_web import ALLOWED_HOSTS_VARIABLE

    monkeypatch.setenv(ALLOWED_HOSTS_VARIABLE, configured)
    assert _host_header_is_loopback(host) is allowed
    assert _host_header_is_loopback("127.0.0.1:8189") is True  # loopback always works
