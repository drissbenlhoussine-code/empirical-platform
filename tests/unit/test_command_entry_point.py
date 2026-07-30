"""MILESTONE-029 behavioral tests for `CommandEntryPoint`.

Proves the frozen invariants from the M029 design: the bound handler is
invoked exactly once, the command instance reaches it unchanged, the
result returns unchanged, and any handler exception propagates with its
exact identity preserved (not wrapped, not translated).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint

if TYPE_CHECKING:
    from empirical_platform.shared.contracts.command import CommandHandler


@dataclass(frozen=True, slots=True)
class _FakeCommand:
    value: int


@dataclass(frozen=True, slots=True)
class _FakeResult:
    value: int


class _RecordingHandler:
    """Conforms structurally to CommandHandler via `handle()` only."""

    def __init__(self, result: _FakeResult) -> None:
        self.result = result
        self.calls: list[_FakeCommand] = []

    def handle(self, command: _FakeCommand) -> _FakeResult:
        self.calls.append(command)
        return self.result


class _FailingHandler:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def handle(self, command: _FakeCommand) -> _FakeResult:
        self.calls += 1
        raise self.exc


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that CommandEntryPoint accepts a conforming
    CommandHandler without inheritance (structural typing only)."""
    handler: CommandHandler[_FakeCommand, _FakeResult] = _RecordingHandler(_FakeResult(value=1))
    entry_point: CommandEntryPoint[_FakeCommand, _FakeResult] = CommandEntryPoint(handler)
    assert entry_point is not None


def test_bound_handler_invoked_exactly_once() -> None:
    handler = _RecordingHandler(_FakeResult(value=1))
    entry_point = CommandEntryPoint(handler)

    entry_point(_FakeCommand(value=1))

    assert len(handler.calls) == 1


def test_command_instance_reaches_handler_unchanged() -> None:
    handler = _RecordingHandler(_FakeResult(value=1))
    entry_point = CommandEntryPoint(handler)
    command = _FakeCommand(value=42)

    entry_point(command)

    assert handler.calls[0] is command


def test_result_returns_unchanged() -> None:
    result = _FakeResult(value=99)
    handler = _RecordingHandler(result)
    entry_point = CommandEntryPoint(handler)

    returned = entry_point(_FakeCommand(value=1))

    assert returned is result


def test_handler_exception_identity_is_preserved() -> None:
    exc = ValueError("boom")
    handler = _FailingHandler(exc)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(ValueError) as excinfo:
        entry_point(_FakeCommand(value=1))

    assert excinfo.value is exc
    assert handler.calls == 1


def test_domain_style_exception_is_not_wrapped() -> None:
    class _DomainError(Exception):
        pass

    exc = _DomainError("domain failure")
    handler = _FailingHandler(exc)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(_DomainError) as excinfo:
        entry_point(_FakeCommand(value=1))

    assert excinfo.value is exc
    assert type(excinfo.value) is _DomainError


def test_handler_bound_at_construction_not_per_call() -> None:
    handler = _RecordingHandler(_FakeResult(value=1))
    entry_point = CommandEntryPoint(handler)

    entry_point(_FakeCommand(value=1))
    entry_point(_FakeCommand(value=2))

    assert len(handler.calls) == 2
    assert entry_point._handler is handler  # noqa: SLF001


def test_malformed_handler_fails_naturally_without_wrapping() -> None:
    """A handler without a conforming `handle()` fails with a plain Python
    error; M029 must not catch and translate it."""

    class _NoHandleMethod:
        pass

    entry_point = CommandEntryPoint(_NoHandleMethod())  # type: ignore[arg-type]

    with pytest.raises(AttributeError):
        entry_point(_FakeCommand(value=1))
