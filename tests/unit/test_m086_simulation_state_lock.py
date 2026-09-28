"""MILESTONE-086 -- one Operator Console per simulation state directory, a real OS lock."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from empirical_platform.shared.brokerage.simulation_paper import (
    SimulationStateLock,
    SimulationStateLockedError,
)


def test_the_lock_is_exclusive_within_a_process_and_released_explicitly(tmp_path: Path) -> None:
    first = SimulationStateLock(tmp_path)
    second = SimulationStateLock(tmp_path)
    first.acquire()
    assert first.held and first.path.exists()
    with pytest.raises(SimulationStateLockedError) as refused:
        second.acquire()
    assert "already owns the simulation state directory" in str(refused.value)
    assert not second.held
    first.acquire()  # re-entrant for the holder: a no-op
    first.release()
    assert not first.held
    second.acquire()  # now free
    second.release()


_CHILD = """
import sys, time
from pathlib import Path
from empirical_platform.shared.brokerage.simulation_paper import SimulationStateLock
state_dir, stop_file = Path(sys.argv[1]), Path(sys.argv[2])
lock = SimulationStateLock(state_dir)
lock.acquire()
print("HELD", flush=True)
while not stop_file.exists():
    time.sleep(0.05)
lock.release()
print("RELEASED", flush=True)
"""


def test_the_lock_is_exclusive_across_processes(tmp_path: Path) -> None:
    """A real second process: it holds the lock; this process is refused until it exits."""
    stop_file = tmp_path / "stop"
    child = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c", _CHILD, str(tmp_path), str(stop_file)],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "HELD"
        mine = SimulationStateLock(tmp_path)
        with pytest.raises(SimulationStateLockedError):
            mine.acquire()
        assert not mine.held
        stop_file.write_text("stop", encoding="utf-8")
        assert child.stdout.readline().strip() == "RELEASED"
        child.wait(timeout=30)
        deadline = time.monotonic() + 10
        while True:
            try:
                mine.acquire()
                break
            except SimulationStateLockedError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        assert mine.held
        mine.release()
    finally:
        if child.poll() is None:
            child.kill()


def test_a_dead_holder_leaves_no_stale_lock(tmp_path: Path) -> None:
    """The OS drops the lock with the process: a crash never wedges the console."""
    stop_file = tmp_path / "never"
    child = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c", _CHILD, str(tmp_path), str(stop_file)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "HELD"
    child.kill()
    child.wait(timeout=30)
    mine = SimulationStateLock(tmp_path)
    deadline = time.monotonic() + 10
    while True:
        try:
            mine.acquire()
            break
        except SimulationStateLockedError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)
    mine.release()
