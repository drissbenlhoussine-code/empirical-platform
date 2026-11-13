"""M101: the standalone authenticated stop only ever signals the verified owner of the port."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.personal_paper_deploy import ConsoleShutdownError
from tools.stop_paper_console import (
    EXIT_NOT_RUNNING,
    EXIT_REFUSED,
    EXIT_STOPPED,
    EXIT_TIMEOUT,
    stop_console,
)

_SAFETY = Path("safety-dir")


class _Network:
    def __init__(self, *owners: int | None | Exception) -> None:
        self._owners = list(owners)
        self.queries = 0

    def owning_pid(self, host: str, port: int) -> int | None:
        del host, port
        self.queries += 1
        value = self._owners.pop(0) if len(self._owners) > 1 else self._owners[0]
        if isinstance(value, Exception):
            raise value
        return value


class _Process:
    def __init__(self, *, exits_after_polls: int = 2, refuse: str | None = None) -> None:
        self.stopped: list[tuple[int, str, int, Path]] = []
        self._polls_left = exits_after_polls
        self._refuse = refuse

    def is_running(self, pid: int) -> bool:
        del pid
        if self._polls_left <= 0:
            return False
        self._polls_left -= 1
        return True

    def graceful_stop(self, pid: int, *, host: str, port: int, safety_directory: Path) -> None:
        if self._refuse is not None:
            raise ConsoleShutdownError(self._refuse)
        self.stopped.append((pid, host, port, safety_directory))


def _run(
    network: _Network, process: _Process, *, timeout: float = 5.0, check_only: bool = False
) -> tuple[int, list[str]]:
    lines: list[str] = []
    clock = {"now": 0.0}

    def sleep(seconds: float) -> None:
        clock["now"] += seconds

    code = stop_console(
        host="127.0.0.1",
        port=8189,
        safety_directory=_SAFETY,
        network=network,  # type: ignore[arg-type]
        process=process,  # type: ignore[arg-type]
        timeout_seconds=timeout,
        check_only=check_only,
        out=lines.append,
        sleep=sleep,
        monotonic=lambda: clock["now"],
    )
    return code, lines


def test_a_verified_listener_is_stopped_with_its_exact_pid_and_the_safety_directory() -> None:
    process = _Process()
    code, lines = _run(_Network(4242), process)
    assert code == EXIT_STOPPED
    assert process.stopped == [(4242, "127.0.0.1", 8189, _SAFETY)]
    assert any("has exited" in line for line in lines)


def test_nothing_listening_is_reported_and_nothing_is_signalled() -> None:
    process = _Process()
    code, _ = _run(_Network(None), process)
    assert code == EXIT_NOT_RUNNING
    assert process.stopped == []


def test_check_only_reports_the_owner_and_signals_nothing() -> None:
    process = _Process()
    network = _Network(4242)
    code, lines = _run(network, process, check_only=True)
    assert code == EXIT_STOPPED
    assert process.stopped == []
    assert network.queries == 1
    assert any("PID 4242" in line for line in lines)


def test_an_owner_that_changes_between_discovery_and_signal_is_never_signalled() -> None:
    process = _Process()
    code, lines = _run(_Network(4242, 9999), process)
    assert code == EXIT_REFUSED
    assert process.stopped == []
    assert any("changed from PID 4242" in line for line in lines)


@pytest.mark.parametrize("position", ["discovery", "reconfirm"])
def test_an_undeterminable_listener_is_a_refusal_never_treated_as_free(position: str) -> None:
    boom = RuntimeError("listener table unreadable")
    network = _Network(boom) if position == "discovery" else _Network(4242, boom)
    process = _Process()
    code, _ = _run(network, process)
    assert code == EXIT_REFUSED
    assert process.stopped == []


def test_a_refused_authenticated_request_is_reported_and_nothing_is_forced() -> None:
    process = _Process(refuse="console refused the shutdown request (HTTP 403)")
    code, lines = _run(_Network(4242), process)
    assert code == EXIT_REFUSED
    assert any("HTTP 403" in line and "Nothing was stopped" in line for line in lines)


def test_an_accepted_request_whose_process_never_exits_times_out_without_any_kill() -> None:
    process = _Process(exits_after_polls=10_000)
    code, lines = _run(_Network(4242), process, timeout=2.0)
    assert code == EXIT_TIMEOUT
    assert process.stopped == [(4242, "127.0.0.1", 8189, _SAFETY)]  # asked once, politely
    assert any("still running" in line for line in lines)
