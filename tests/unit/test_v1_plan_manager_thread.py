"""RELEASE v1 -- `PlanManagerThread` starts, polls at least once, survives a bad tick, and
stops cleanly. Mirrors `_Reconciler`'s own direct-unit-test style (`test_m086_operator_
console_launcher.py`): the thread is tested standalone, not through a real WSGI server.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

from empirical_platform.usecases.position_plan_manager import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    ManagerHeartbeat,
    PlanManagerThread,
    manager_liveness_alert,
)


class _FakeManager:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls: list[datetime] = []
        self._fail_first = fail_first
        self._failed_once = False
        self.ready = threading.Event()

    def evaluate_once(self, *, now: datetime) -> tuple[()]:
        if self._fail_first and not self._failed_once:
            self._failed_once = True
            self.ready.set()
            raise RuntimeError("simulated bad tick")
        self.calls.append(now)
        self.ready.set()
        return ()


def _now() -> datetime:
    return datetime.now(UTC)


def test_the_thread_starts_and_polls_at_least_once() -> None:
    manager = _FakeManager()
    thread = PlanManagerThread(manager, now=_now, interval_seconds=1)  # type: ignore[arg-type]
    thread.start()
    try:
        assert manager.ready.wait(timeout=5)
        assert len(manager.calls) >= 1
    finally:
        thread.stop()


def test_a_failed_tick_does_not_stop_the_loop() -> None:
    manager = _FakeManager(fail_first=True)
    thread = PlanManagerThread(manager, now=_now, interval_seconds=1)  # type: ignore[arg-type]
    thread.start()
    try:
        assert manager.ready.wait(timeout=5)  # the first (failing) tick
        manager.ready.clear()
        assert manager.ready.wait(timeout=5)  # a second tick still runs
        assert len(manager.calls) >= 1
    finally:
        thread.stop()


def test_stop_is_idempotent_and_actually_joins() -> None:
    manager = _FakeManager()
    thread = PlanManagerThread(manager, now=_now, interval_seconds=1)  # type: ignore[arg-type]
    thread.start()
    assert manager.ready.wait(timeout=5)
    thread.stop()
    thread.stop()  # must not raise
    time.sleep(0.05)
    assert thread._thread is not None
    assert not thread._thread.is_alive()


def test_calling_start_twice_does_not_create_a_second_thread() -> None:
    manager = _FakeManager()
    thread = PlanManagerThread(manager, now=_now, interval_seconds=1)  # type: ignore[arg-type]
    thread.start()
    first = thread._thread
    thread.start()
    try:
        assert thread._thread is first
    finally:
        thread.stop()


# ---------------------------------------------------------------------------
# RELEASE v1 SAFETY ALERT: `ManagerHeartbeat`, consumed by `manager_liveness_alert`
# ---------------------------------------------------------------------------


def test_heartbeat_is_none_before_start() -> None:
    manager = _FakeManager()
    thread = PlanManagerThread(manager, now=_now, interval_seconds=1)  # type: ignore[arg-type]
    assert thread.heartbeat() is None


def _wait_for_heartbeat(
    thread: PlanManagerThread, *, at_least_ticks: int, timeout: float = 5.0
) -> ManagerHeartbeat:
    """Poll `thread.heartbeat()` directly rather than racing `manager.ready`: the fake
    manager's `ready` event fires INSIDE `evaluate_once`, before `_run` has written the
    heartbeat for that same tick -- waiting on `ready` alone is a real race against the
    heartbeat write, not just a slow-test convenience."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        heartbeat = thread.heartbeat()
        if heartbeat is not None and heartbeat.ticks_completed >= at_least_ticks:
            return heartbeat
        time.sleep(0.01)
    raise AssertionError(f"heartbeat never reached {at_least_ticks} completed tick(s)")


def test_heartbeat_advances_after_a_successful_tick() -> None:
    manager = _FakeManager()
    thread = PlanManagerThread(manager, now=_now, interval_seconds=1)  # type: ignore[arg-type]
    thread.start()
    try:
        heartbeat = _wait_for_heartbeat(thread, at_least_ticks=1)
        assert heartbeat.last_tick_at is not None
        assert heartbeat.last_tick_error is None
        assert heartbeat.ticks_completed >= 1
    finally:
        thread.stop()


def test_heartbeat_records_the_error_from_a_failed_tick_but_keeps_advancing() -> None:
    manager = _FakeManager(fail_first=True)
    thread = PlanManagerThread(manager, now=_now, interval_seconds=1)  # type: ignore[arg-type]
    thread.start()
    try:
        heartbeat = _wait_for_heartbeat(thread, at_least_ticks=1)  # the first (failing) tick
        assert heartbeat.last_tick_at is not None
        assert heartbeat.last_tick_error is not None
        assert "simulated bad tick" in heartbeat.last_tick_error
        recovered = _wait_for_heartbeat(thread, at_least_ticks=heartbeat.ticks_completed + 1)
        assert recovered.last_tick_error is None
        assert recovered.ticks_completed == heartbeat.ticks_completed + 1
        assert recovered.started_at == heartbeat.started_at, "started_at never moves"
    finally:
        thread.stop()


# ---------------------------------------------------------------------------
# RELEASE v1 SAFETY ALERT: `manager_liveness_alert` -- pure, no thread involved
# ---------------------------------------------------------------------------

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


def test_no_heartbeat_at_all_is_never_escalated() -> None:
    """A capability with no automatic manager composed at all (e.g. `--recovery-mode`, or
    no exit path) must not be confused with a manager that stopped -- that state is already
    visible elsewhere and this alert must never duplicate or contradict it."""
    assert manager_liveness_alert(None, now=_NOW, has_open_positions=True) is None


def test_no_open_positions_is_never_escalated_even_if_stale() -> None:
    stale = _heartbeat(last_tick_at=_NOW - timedelta(hours=1))
    assert manager_liveness_alert(stale, now=_NOW, has_open_positions=False) is None


def test_a_fresh_successful_heartbeat_with_open_positions_is_not_escalated() -> None:
    fresh = _heartbeat(last_tick_at=_NOW - timedelta(seconds=5))
    assert manager_liveness_alert(fresh, now=_NOW, has_open_positions=True) is None


def test_a_stale_heartbeat_with_open_positions_is_escalated() -> None:
    stale = _heartbeat(last_tick_at=_NOW - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS * 5))
    alert = manager_liveness_alert(stale, now=_NOW, has_open_positions=True)
    assert alert is not None
    assert "has not completed a tick" in alert
    assert "a position depends on it" in alert


def test_never_ticked_at_all_and_stale_since_start_is_escalated() -> None:
    """The thread started but has not completed even its first tick, and enough time has
    passed that it should have -- `last_tick_at is None` must not be read as "fresh"."""
    never_ticked = _heartbeat(
        started_at=_NOW - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS * 5),
        last_tick_at=None,
    )
    alert = manager_liveness_alert(never_ticked, now=_NOW, has_open_positions=True)
    assert alert is not None
    assert "its first tick" in alert


def test_a_recent_but_failing_tick_is_escalated_with_the_recorded_error() -> None:
    failing = _heartbeat(
        last_tick_at=_NOW - timedelta(seconds=1), last_tick_error="RuntimeError: boom"
    )
    alert = manager_liveness_alert(failing, now=_NOW, has_open_positions=True)
    assert alert is not None
    assert "most recent tick failed" in alert
    assert "RuntimeError: boom" in alert


def test_staleness_takes_priority_wording_over_a_stale_recorded_error() -> None:
    """When BOTH conditions hold (stale AND the last recorded tick failed), the staleness
    message fires -- it is the more urgent fact (the manager may not even be running to
    retry the failing tick at all)."""
    stale_and_failing = _heartbeat(
        last_tick_at=_NOW - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS * 10),
        last_tick_error="RuntimeError: boom",
    )
    alert = manager_liveness_alert(stale_and_failing, now=_NOW, has_open_positions=True)
    assert alert is not None
    assert "has not completed a tick" in alert
