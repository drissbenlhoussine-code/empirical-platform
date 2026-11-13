"""RELEASE v1 SAFETY VISIBILITY -- pure-function coverage of `manager_status`/
`manager_status_detail`/`ManagerThreadHandle` (`usecases.position_plan_manager`), the logic
behind `/safety`'s new automatic-manager-status field. Mirrors `test_v1_plan_manager_thread
.py`'s own `manager_liveness_alert` section in style: no thread, no WSGI client, just the
pure classification and its text, exercised directly.

PRECEDENCE UNDER TEST, exactly `manager_status`'s own docstring: `recovery_mode` first, then
`manager_supported`, then "does a heartbeat exist at all", then staleness/error, and only
then `HEALTHY` -- the "never HEALTHY without full, fresh, error-free evidence" rule.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from empirical_platform.usecases.position_plan_manager import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    ManagerHeartbeat,
    ManagerStatus,
    ManagerThreadHandle,
    manager_status,
    manager_status_detail,
)

_NOW = datetime(2026, 10, 19, 20, 0, tzinfo=UTC)


def _heartbeat(
    *,
    started_at: datetime = _NOW - timedelta(minutes=5),
    last_tick_at: datetime | None = _NOW,
    last_tick_error: str | None = None,
    ticks_completed: int = 10,
) -> ManagerHeartbeat:
    return ManagerHeartbeat(
        started_at=started_at,
        last_tick_at=last_tick_at,
        last_tick_error=last_tick_error,
        ticks_completed=ticks_completed,
    )


# ---------------------------------------------------------------------------
# `manager_status` -- the 5-state classification
# ---------------------------------------------------------------------------


def test_recovery_mode_wins_even_with_no_heartbeat_and_supported_true() -> None:
    assert (
        manager_status(None, now=_NOW, recovery_mode=True, manager_supported=True)
        is ManagerStatus.RECOVERY_MODE
    )


def test_recovery_mode_wins_even_over_a_fresh_healthy_looking_heartbeat() -> None:
    """Defensive: even if some future composition bug left a real heartbeat behind while
    `recovery_mode` is also true, RECOVERY_MODE must still win -- it is checked first and
    unconditionally, precisely so it is never mistaken for, or masked by, another state."""
    fresh = _heartbeat(last_tick_at=_NOW - timedelta(seconds=1))
    assert (
        manager_status(fresh, now=_NOW, recovery_mode=True, manager_supported=True)
        is ManagerStatus.RECOVERY_MODE
    )


def test_not_supported_is_unknown_regardless_of_heartbeat() -> None:
    """A capability with no plan-manager concept at all (SIMULATION, plain PAPER) must never
    be asserted STOPPED (nothing was ever supposed to run) or HEALTHY (no evidence either
    way) -- UNKNOWN is the only truthful answer."""
    assert (
        manager_status(None, now=_NOW, recovery_mode=False, manager_supported=False)
        is ManagerStatus.UNKNOWN
    )
    fresh = _heartbeat(last_tick_at=_NOW - timedelta(seconds=1))
    assert (
        manager_status(fresh, now=_NOW, recovery_mode=False, manager_supported=False)
        is ManagerStatus.UNKNOWN
    )


def test_supported_but_no_heartbeat_at_all_is_stopped() -> None:
    assert (
        manager_status(None, now=_NOW, recovery_mode=False, manager_supported=True)
        is ManagerStatus.STOPPED
    )


def test_fresh_error_free_heartbeat_is_healthy() -> None:
    fresh = _heartbeat(last_tick_at=_NOW - timedelta(seconds=5), last_tick_error=None)
    assert (
        manager_status(fresh, now=_NOW, recovery_mode=False, manager_supported=True)
        is ManagerStatus.HEALTHY
    )


def test_old_last_tick_at_is_stale() -> None:
    stale = _heartbeat(last_tick_at=_NOW - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS * 5))
    assert (
        manager_status(stale, now=_NOW, recovery_mode=False, manager_supported=True)
        is ManagerStatus.STALE
    )


def test_never_ticked_and_stale_since_start_is_stale() -> None:
    """`last_tick_at is None` must not be read as fresh -- it falls back to `started_at`."""
    never_ticked = _heartbeat(
        started_at=_NOW - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS * 5),
        last_tick_at=None,
    )
    assert (
        manager_status(never_ticked, now=_NOW, recovery_mode=False, manager_supported=True)
        is ManagerStatus.STALE
    )


def test_fresh_but_erroring_last_tick_is_stale_not_healthy() -> None:
    """A heartbeat that is fresh BY TIMESTAMP but whose last recorded tick failed is still
    not evidence of a healthy manager -- requirement: never HEALTHY without full evidence.
    There is no sixth state for "ticking but currently failing", so this folds into STALE."""
    failing = _heartbeat(
        last_tick_at=_NOW - timedelta(seconds=1), last_tick_error="RuntimeError: boom"
    )
    assert (
        manager_status(failing, now=_NOW, recovery_mode=False, manager_supported=True)
        is ManagerStatus.STALE
    )


def test_a_heartbeat_at_exactly_the_staleness_boundary_is_not_yet_stale() -> None:
    boundary = _heartbeat(last_tick_at=_NOW - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS * 4))
    assert (
        manager_status(boundary, now=_NOW, recovery_mode=False, manager_supported=True)
        is ManagerStatus.HEALTHY
    )


# ---------------------------------------------------------------------------
# `manager_status_detail` -- the plain-language, actionable text per state
# ---------------------------------------------------------------------------


def test_recovery_mode_detail_names_the_flag_and_is_not_alarming() -> None:
    detail = manager_status_detail(ManagerStatus.RECOVERY_MODE, None, now=_NOW)
    assert "--recovery-mode" in detail
    assert "deliberate" in detail
    assert "not failed" in detail or "not stopped" in detail


def test_unknown_detail_does_not_claim_health() -> None:
    detail = manager_status_detail(ManagerStatus.UNKNOWN, None, now=_NOW)
    assert "healthy" not in detail.lower() or "not a claim" in detail.lower()
    assert "gap" in detail.lower() or "unknown" in detail.lower() or "unproven" in detail.lower()


def test_stopped_detail_says_no_heartbeat_and_how_to_fix_it() -> None:
    detail = manager_status_detail(ManagerStatus.STOPPED, None, now=_NOW)
    assert "no heartbeat" in detail.lower()
    assert "restart" in detail.lower()
    assert "silent failure" in detail.lower()


def test_stale_detail_for_an_old_timestamp_names_the_staleness() -> None:
    stale = _heartbeat(last_tick_at=_NOW - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS * 10))
    detail = manager_status_detail(ManagerStatus.STALE, stale, now=_NOW)
    assert "has not completed a tick" in detail
    assert "hung or crashed" in detail


def test_stale_detail_for_a_recent_error_names_the_recorded_error() -> None:
    failing = _heartbeat(
        last_tick_at=_NOW - timedelta(seconds=1), last_tick_error="RuntimeError: boom"
    )
    detail = manager_status_detail(ManagerStatus.STALE, failing, now=_NOW)
    assert "most recent tick failed" in detail
    assert "RuntimeError: boom" in detail
    assert "still running" in detail


def test_healthy_detail_reports_tick_count_and_no_error() -> None:
    fresh = _heartbeat(last_tick_at=_NOW - timedelta(seconds=3), ticks_completed=42)
    detail = manager_status_detail(ManagerStatus.HEALTHY, fresh, now=_NOW)
    assert "42" in detail
    assert "no error" in detail.lower()


# ---------------------------------------------------------------------------
# `ManagerThreadHandle` -- the mutable, late-bound box
# ---------------------------------------------------------------------------


def test_handle_heartbeat_is_none_before_a_thread_is_set() -> None:
    handle = ManagerThreadHandle()
    assert handle.thread is None
    assert handle.heartbeat() is None


def test_handle_heartbeat_reads_through_to_the_set_thread() -> None:
    class _Thread:
        def heartbeat(self) -> ManagerHeartbeat:
            return _heartbeat()

    handle = ManagerThreadHandle()
    handle.thread = _Thread()  # type: ignore[assignment]
    assert handle.heartbeat() == _heartbeat()
