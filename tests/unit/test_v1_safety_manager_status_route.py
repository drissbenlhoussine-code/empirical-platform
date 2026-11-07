"""RELEASE v1 SAFETY VISIBILITY -- `/safety`'s new automatic-position-manager status field,
driven through the REAL WSGI router (`build_paper_application`), the same discipline
`test_v1_paper_console_app_routes.py` already uses for the plan-aware `/active`/`/history`
overrides. Reuses that file's own `_backend()` fixture (the exit-capable `PaperConsoleBackend`
shape) via `dataclasses.replace`, so only the two fields this feature actually added
(`_manager_thread_handle`, `_recovery_mode`) vary between cases.

REQUIREMENT UNDER TEST (release mission item 4): heartbeat freshness must come from the real
`PlanManagerThread`/`ManagerHeartbeat` evaluation-loop evidence, never from "the HTTP server
answered this request". Every test here proves that by getting a 200 response from the WSGI
client (the server obviously "works") while independently controlling what the heartbeat
claims -- a stale or absent heartbeat must still show STALE/STOPPED, never HEALTHY, even
though the page rendered successfully.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from tests.unit.test_m086_operator_console_routes import Client
from tests.unit.test_v1_paper_console_app_routes import _backend

from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints._paper_operator_console_composition import PaperConsoleBackend
from empirical_platform.entrypoints.paper_operator_console_app import build_paper_application
from empirical_platform.usecases.position_plan_manager import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    ManagerHeartbeat,
    ManagerThreadHandle,
)


def _now() -> datetime:
    return datetime.now(UTC)


class _FakeManagerThread:
    """Duck-types `PlanManagerThread` far enough for `ManagerThreadHandle.heartbeat()`:
    just `.heartbeat()`. Never a real background thread -- these tests control the returned
    `ManagerHeartbeat` directly, deterministically, with no timing race."""

    def __init__(self, heartbeat: ManagerHeartbeat | None) -> None:
        self._heartbeat = heartbeat

    def heartbeat(self) -> ManagerHeartbeat | None:
        return self._heartbeat


def _exit_capable_backend(
    *, recovery_mode: bool, heartbeat: ManagerHeartbeat | None | object = "unset"
) -> PaperConsoleBackend:
    """The exit-capable (`--capability paper-exit`) composition shape: a non-`None`
    `_manager_thread_handle` -- see `ManagerThreadHandle`'s own docstring for why a plain
    PAPER backend never has one. `heartbeat="unset"` (the default) leaves `handle.thread`
    `None` -- the "never started" / STOPPED case; any other value (including `None`
    explicitly) sets a `_FakeManagerThread` returning it.
    """
    handle = ManagerThreadHandle()
    if heartbeat != "unset":
        handle.thread = _FakeManagerThread(heartbeat)  # type: ignore[assignment]
    base = _backend()
    return replace(base, _manager_thread_handle=handle, _recovery_mode=recovery_mode)


def _client(backend: PaperConsoleBackend) -> Client:
    return Client(build_paper_application(backend, security=SecuritySession()))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Omitted entirely for a capability with no plan-manager concept
# ---------------------------------------------------------------------------


def test_plain_paper_safety_page_has_no_manager_status_section_at_all() -> None:
    """M088's plain PAPER composition (`_manager_thread_handle` stays `None`, the default)
    must not get a five-state field forced onto it -- the card is omitted entirely, not
    rendered as UNKNOWN."""
    plain = _backend()  # `_manager_thread_handle` defaults to None
    reply = _client(plain).get("/safety")
    assert reply.code == 200
    assert "Automatic position manager" not in reply.body


# ---------------------------------------------------------------------------
# RECOVERY_MODE -- intentional, visually distinct from a real problem
# ---------------------------------------------------------------------------


def test_recovery_mode_shows_recovery_mode_not_stopped() -> None:
    backend = _exit_capable_backend(recovery_mode=True)  # handle.thread stays None too
    reply = _client(backend).get("/safety")
    assert reply.code == 200
    assert "RECOVERY_MODE" in reply.body
    assert "STOPPED" not in reply.body
    assert "--recovery-mode" in reply.body
    # Distinguishable from a real problem: the informational tone, not the danger one.
    assert "banner-info" in reply.body
    assert 'banner-danger"><strong>RECOVERY_MODE' not in reply.body


# ---------------------------------------------------------------------------
# STOPPED -- supported, not recovery mode, but no heartbeat has ever existed
# ---------------------------------------------------------------------------


def test_never_started_manager_shows_stopped() -> None:
    backend = _exit_capable_backend(recovery_mode=False)  # handle.thread left unset (None)
    reply = _client(backend).get("/safety")
    assert reply.code == 200
    assert "STOPPED" in reply.body
    assert "no heartbeat" in reply.body.lower()
    assert "HEALTHY" not in reply.body


# ---------------------------------------------------------------------------
# HEALTHY -- a real, fresh, error-free heartbeat
# ---------------------------------------------------------------------------


def test_fresh_error_free_heartbeat_shows_healthy() -> None:
    fresh = ManagerHeartbeat(
        started_at=_now() - timedelta(minutes=5),
        last_tick_at=_now() - timedelta(seconds=5),
        last_tick_error=None,
        ticks_completed=20,
    )
    backend = _exit_capable_backend(recovery_mode=False, heartbeat=fresh)
    reply = _client(backend).get("/safety")
    assert reply.code == 200
    assert "HEALTHY" in reply.body
    assert "STALE" not in reply.body
    assert "STOPPED" not in reply.body


# ---------------------------------------------------------------------------
# STALE -- heartbeat exists but the background loop is not demonstrably working
# ---------------------------------------------------------------------------


def test_stale_timestamp_shows_stale_not_healthy_even_though_the_server_answers() -> None:
    """RELEASE MISSION REQUIREMENT 4/5: the manager thread 'died' (its heartbeat stopped
    advancing) but the WSGI server -- the thing actually answering this very HTTP request --
    is completely unaffected and returns 200 regardless. The page must still say STALE, never
    HEALTHY: HTTP liveness is not evidence of background-loop liveness."""
    stalled = ManagerHeartbeat(
        started_at=_now() - timedelta(hours=1),
        last_tick_at=_now() - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS * 10),
        last_tick_error=None,
        ticks_completed=5,
    )
    backend = _exit_capable_backend(recovery_mode=False, heartbeat=stalled)
    reply = _client(backend).get("/safety")
    assert reply.code == 200  # the HTTP server is fine -- that is exactly the point
    assert "STALE" in reply.body
    assert "HEALTHY" not in reply.body
    assert "has not completed a tick" in reply.body


def test_recent_tick_error_shows_stale_not_healthy() -> None:
    failing = ManagerHeartbeat(
        started_at=_now() - timedelta(minutes=5),
        last_tick_at=_now() - timedelta(seconds=1),
        last_tick_error="RuntimeError: boom",
        ticks_completed=7,
    )
    backend = _exit_capable_backend(recovery_mode=False, heartbeat=failing)
    reply = _client(backend).get("/safety")
    assert reply.code == 200
    assert "STALE" in reply.body
    assert "HEALTHY" not in reply.body
    assert "RuntimeError: boom" in reply.body


# ---------------------------------------------------------------------------
# The provider is called fresh per request, never cached at construction time
# ---------------------------------------------------------------------------


def test_status_reflects_the_current_heartbeat_on_each_request_not_a_startup_snapshot() -> None:
    """The SAME handle, mutated between two requests to the SAME client/app, must change
    what `/safety` reports -- proving the route reads live state, not something captured once
    when `build_paper_application` ran."""
    handle = ManagerThreadHandle()
    base = _backend()
    backend = replace(base, _manager_thread_handle=handle, _recovery_mode=False)
    client = _client(backend)

    first = client.get("/safety")
    assert "STOPPED" in first.body

    handle.thread = _FakeManagerThread(  # type: ignore[assignment]
        ManagerHeartbeat(
            started_at=_now() - timedelta(minutes=1),
            last_tick_at=_now() - timedelta(seconds=2),
            last_tick_error=None,
            ticks_completed=1,
        )
    )
    second = client.get("/safety")
    assert "HEALTHY" in second.body
    assert "STOPPED" not in second.body
