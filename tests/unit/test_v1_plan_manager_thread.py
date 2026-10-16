"""RELEASE v1 -- `PlanManagerThread` starts, polls at least once, survives a bad tick, and
stops cleanly. Mirrors `_Reconciler`'s own direct-unit-test style (`test_m086_operator_
console_launcher.py`): the thread is tested standalone, not through a real WSGI server.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

from empirical_platform.usecases.position_plan_manager import PlanManagerThread


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
