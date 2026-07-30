"""MILESTONE-029 behavioral tests for `QueryEntryPoint`.

Mirrors `test_command_entry_point.py`: the bound handler is invoked
exactly once, the query instance reaches it unchanged, the result
returns unchanged, and any handler exception propagates with its exact
identity preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.query import QueryEntryPoint

if TYPE_CHECKING:
    from empirical_platform.shared.contracts.query import QueryHandler


@dataclass(frozen=True, slots=True)
class _FakeQuery:
    value: int


@dataclass(frozen=True, slots=True)
class _FakeQueryResult:
    value: int


class _RecordingHandler:
    """Conforms structurally to QueryHandler via `handle()` only."""

    def __init__(self, result: _FakeQueryResult) -> None:
        self.result = result
        self.calls: list[_FakeQuery] = []

    def handle(self, query: _FakeQuery) -> _FakeQueryResult:
        self.calls.append(query)
        return self.result


class _FailingHandler:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def handle(self, query: _FakeQuery) -> _FakeQueryResult:
        self.calls += 1
        raise self.exc


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that QueryEntryPoint accepts a conforming
    QueryHandler without inheritance (structural typing only)."""
    handler: QueryHandler[_FakeQuery, _FakeQueryResult] = _RecordingHandler(
        _FakeQueryResult(value=1)
    )
    entry_point: QueryEntryPoint[_FakeQuery, _FakeQueryResult] = QueryEntryPoint(handler)
    assert entry_point is not None


def test_bound_handler_invoked_exactly_once() -> None:
    handler = _RecordingHandler(_FakeQueryResult(value=1))
    entry_point = QueryEntryPoint(handler)

    entry_point(_FakeQuery(value=1))

    assert len(handler.calls) == 1


def test_query_instance_reaches_handler_unchanged() -> None:
    handler = _RecordingHandler(_FakeQueryResult(value=1))
    entry_point = QueryEntryPoint(handler)
    query = _FakeQuery(value=42)

    entry_point(query)

    assert handler.calls[0] is query


def test_result_returns_unchanged() -> None:
    result = _FakeQueryResult(value=99)
    handler = _RecordingHandler(result)
    entry_point = QueryEntryPoint(handler)

    returned = entry_point(_FakeQuery(value=1))

    assert returned is result


def test_handler_exception_identity_is_preserved() -> None:
    exc = ValueError("boom")
    handler = _FailingHandler(exc)
    entry_point = QueryEntryPoint(handler)

    with pytest.raises(ValueError) as excinfo:
        entry_point(_FakeQuery(value=1))

    assert excinfo.value is exc
    assert handler.calls == 1


def test_handler_bound_at_construction_not_per_call() -> None:
    handler = _RecordingHandler(_FakeQueryResult(value=1))
    entry_point = QueryEntryPoint(handler)

    entry_point(_FakeQuery(value=1))
    entry_point(_FakeQuery(value=2))

    assert len(handler.calls) == 2
    assert entry_point._handler is handler  # noqa: SLF001


def test_malformed_handler_fails_naturally_without_wrapping() -> None:
    """A handler without a conforming `handle()` fails with a plain Python
    error; M029 must not catch and translate it."""

    class _NoHandleMethod:
        pass

    entry_point = QueryEntryPoint(_NoHandleMethod())  # type: ignore[arg-type]

    with pytest.raises(AttributeError):
        entry_point(_FakeQuery(value=1))
