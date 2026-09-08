"""MILESTONE-083 -- pure row-mapping AND Python-control-flow unit tests.

Owner finding M083-REV-004: this file previously covered only
`_row_to_watermark`. It now also drives `capture`/`get`'s own Python control
flow (SQL dispatch shape, the existing-row fast path, conflict handling,
unrelated-error propagation) through a hand-written fake that duck-types the
narrow `unit_of_work()`/`execute()` surface `PostgresPersistenceService`
exposes -- NOT a database, and NOT a simulation of what the BEFORE INSERT
trigger computes. The fake never decides what receipt identities a watermark
contains; it only returns pre-scripted rows so the REPOSITORY CLASS's own
branching (not PostgreSQL's) can be exercised offline. Real PostgreSQL
snapshot/trigger/concurrency semantics remain covered exclusively by
`tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py`
against a real database -- faking those would mean re-implementing the
trigger's own logic in test glue, making the glue the thing under test
instead of PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import SimpleNamespace
from typing import Any

import pytest

from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.persistence.postgres_repositories.evaluation_evidence_watermark_repository import (  # noqa: E501
    PostgresEvaluationEvidenceWatermarkRepository,
    _row_to_watermark,
)


class _FakeUnitOfWork:
    """Duck-types the narrow `execute()` surface a real unit of work exposes."""

    def __init__(
        self, script: Callable[[str, Mapping[str, object]], Sequence[Mapping[str, Any]]]
    ) -> None:
        self._script = script
        self.statements: list[str] = []

    def __enter__(self) -> _FakeUnitOfWork:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def execute(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> Sequence[Mapping[str, Any]]:
        self.statements.append(statement)
        return self._script(statement, parameters or {})


class _FakeService:
    """Duck-types the one method the repository calls on the real service."""

    def __init__(
        self, script: Callable[[str, Mapping[str, object]], Sequence[Mapping[str, Any]]]
    ) -> None:
        self._script = script
        self.unit_of_work_calls = 0

    def unit_of_work(self) -> _FakeUnitOfWork:
        self.unit_of_work_calls += 1
        return _FakeUnitOfWork(self._script)


class _FakeDBAPIError(Exception):
    """A minimal stand-in for the real driver exception `unique_violation_
    constraint_name` unwraps via `error.__cause__.orig.diag`. It must itself
    be a real exception -- Python's `__cause__` rejects anything else."""

    def __init__(self, orig: object) -> None:
        super().__init__("fake DBAPI cause")
        self.orig = orig


def _fake_unique_violation(constraint_name: str) -> FoundationError:
    """A FoundationError shaped exactly as `unique_violation_constraint_name`
    inspects it: `__cause__.orig.diag.sqlstate == "23505"` and a
    `constraint_name` diagnostic -- the real structural shape, not a string
    the translator would merely happen to match."""
    diag = SimpleNamespace(sqlstate="23505", constraint_name=constraint_name)
    orig = SimpleNamespace(diag=diag)
    error = FoundationError(
        category=FoundationErrorCategory.PERSISTENCE,
        message="unique violation",
        layer="persistence",
        operation="execute",
    )
    error.__cause__ = _FakeDBAPIError(orig)
    return error


def _fake_unrelated_error() -> FoundationError:
    """A FoundationError that is NOT a recognized unique-violation on the
    watermark primary key -- e.g. no structured diagnostic at all. Must
    propagate, never be swallowed or misclassified as a conflict."""
    error = FoundationError(
        category=FoundationErrorCategory.PERSISTENCE,
        message="connection reset",
        layer="persistence",
        operation="execute",
    )
    error.__cause__ = RuntimeError("connection reset by peer")
    return error


def test_get_returns_none_when_no_row_exists() -> None:
    def script(statement: str, params: Mapping[str, object]) -> Sequence[Mapping[str, Any]]:
        assert statement.strip().upper().startswith("SELECT")
        assert params == {"watermark_governance_id": "WM-MISSING"}
        return []

    repo = PostgresEvaluationEvidenceWatermarkRepository(_FakeService(script))  # type: ignore[arg-type]
    assert repo.get("WM-MISSING") is None


def test_get_returns_the_mapped_watermark_when_a_row_exists() -> None:
    def script(statement: str, params: Mapping[str, object]) -> Sequence[Mapping[str, Any]]:
        return [{"watermark_governance_id": "WM-FOUND", "receipt_governance_ids": ["RC-A"]}]

    repo = PostgresEvaluationEvidenceWatermarkRepository(_FakeService(script))  # type: ignore[arg-type]
    watermark = repo.get("WM-FOUND")
    assert watermark is not None
    assert watermark.watermark_governance_id == "WM-FOUND"
    assert watermark.receipt_governance_ids == ("RC-A",)


def test_capture_existing_row_fast_path_never_attempts_insert() -> None:
    """The existence pre-check short-circuits capture entirely: no INSERT
    statement is ever dispatched when the watermark already exists."""
    calls: list[str] = []

    def script(statement: str, params: Mapping[str, object]) -> Sequence[Mapping[str, Any]]:
        calls.append(statement.strip().split(None, 1)[0].upper())
        return [{"watermark_governance_id": "WM-EXISTING", "receipt_governance_ids": []}]

    repo = PostgresEvaluationEvidenceWatermarkRepository(_FakeService(script))  # type: ignore[arg-type]
    watermark = repo.capture(watermark_governance_id="WM-EXISTING")
    assert watermark.watermark_governance_id == "WM-EXISTING"
    assert calls == ["SELECT"], "capture must not attempt INSERT when a row already exists"


def test_capture_happy_path_dispatches_exact_insert_shape_and_returns_new_row() -> None:
    calls: list[tuple[str, Mapping[str, object]]] = []

    def script(statement: str, params: Mapping[str, object]) -> Sequence[Mapping[str, Any]]:
        calls.append((statement.strip(), params))
        kind = statement.strip().split(None, 1)[0].upper()
        if kind == "SELECT":
            return []  # no existing row
        assert kind == "INSERT"
        assert "public.evaluation_evidence_watermark" in statement
        assert "RETURNING watermark_governance_id, receipt_governance_ids" in statement
        assert params == {"watermark_governance_id": "WM-NEW"}
        return [{"watermark_governance_id": "WM-NEW", "receipt_governance_ids": ["RC-A", "RC-B"]}]

    repo = PostgresEvaluationEvidenceWatermarkRepository(_FakeService(script))  # type: ignore[arg-type]
    watermark = repo.capture(watermark_governance_id="WM-NEW")
    assert watermark.watermark_governance_id == "WM-NEW"
    assert watermark.receipt_governance_ids == ("RC-A", "RC-B")
    kinds = [statement.split(None, 1)[0].upper() for statement, _ in calls]
    assert kinds == ["SELECT", "INSERT"]


def test_capture_conflict_reads_back_and_returns_the_winner() -> None:
    """Recognized primary-key conflict: INSERT loses the race, get() is
    called again, and the winner it finds is returned rather than raised."""
    call_kinds: list[str] = []

    def script(statement: str, params: Mapping[str, object]) -> Sequence[Mapping[str, Any]]:
        kind = statement.strip().split(None, 1)[0].upper()
        call_kinds.append(kind)
        if kind == "SELECT":
            if call_kinds.count("SELECT") == 1:
                return []  # first pre-check: no existing row yet
            return [{"watermark_governance_id": "WM-RACE", "receipt_governance_ids": ["RC-WINNER"]}]
        assert kind == "INSERT"
        raise _fake_unique_violation("pk_evaluation_evidence_watermark")

    repo = PostgresEvaluationEvidenceWatermarkRepository(_FakeService(script))  # type: ignore[arg-type]
    watermark = repo.capture(watermark_governance_id="WM-RACE")
    assert watermark.watermark_governance_id == "WM-RACE"
    assert watermark.receipt_governance_ids == ("RC-WINNER",)
    assert call_kinds == ["SELECT", "INSERT", "SELECT"]


def test_capture_conflict_with_no_readable_winner_raises() -> None:
    """A conflict occurred but the read-back finds nothing -- an impossible
    state under real PostgreSQL (the winner's row must exist to have
    conflicted), guarded defensively and never silently swallowed."""
    call_kinds: list[str] = []

    def script(statement: str, params: Mapping[str, object]) -> Sequence[Mapping[str, Any]]:
        kind = statement.strip().split(None, 1)[0].upper()
        call_kinds.append(kind)
        if kind == "SELECT":
            return []
        raise _fake_unique_violation("pk_evaluation_evidence_watermark")

    repo = PostgresEvaluationEvidenceWatermarkRepository(_FakeService(script))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="conflicted but cannot be read back"):
        repo.capture(watermark_governance_id="WM-GHOST")


def test_capture_propagates_an_unrelated_foundation_error_unmodified() -> None:
    """A FoundationError that is NOT the watermark's own primary-key
    conflict (e.g. an unrelated persistence fault) must propagate as-is --
    never reclassified as a conflict, never swallowed."""

    def script(statement: str, params: Mapping[str, object]) -> Sequence[Mapping[str, Any]]:
        kind = statement.strip().split(None, 1)[0].upper()
        if kind == "SELECT":
            return []
        raise _fake_unrelated_error()

    repo = PostgresEvaluationEvidenceWatermarkRepository(_FakeService(script))  # type: ignore[arg-type]
    with pytest.raises(FoundationError, match="connection reset"):
        repo.capture(watermark_governance_id="WM-FAULT")


def test_capture_propagates_a_unique_violation_on_an_unrecognized_constraint() -> None:
    """A real unique-violation SQLSTATE, but naming a constraint this
    repository does not own -- must not be misclassified as ITS conflict."""

    def script(statement: str, params: Mapping[str, object]) -> Sequence[Mapping[str, Any]]:
        kind = statement.strip().split(None, 1)[0].upper()
        if kind == "SELECT":
            return []
        raise _fake_unique_violation("some_other_tables_constraint")

    repo = PostgresEvaluationEvidenceWatermarkRepository(_FakeService(script))  # type: ignore[arg-type]
    with pytest.raises(FoundationError, match="unique violation"):
        repo.capture(watermark_governance_id="WM-OTHER-CONSTRAINT")


def test_row_to_watermark_maps_a_plain_mapping() -> None:
    watermark = _row_to_watermark(
        {"watermark_governance_id": "WM-ROW", "receipt_governance_ids": ["RC-A", "RC-B"]}
    )
    assert watermark.watermark_governance_id == "WM-ROW"
    assert watermark.receipt_governance_ids == ("RC-A", "RC-B")


def test_row_to_watermark_maps_an_empty_receipt_array() -> None:
    watermark = _row_to_watermark(
        {"watermark_governance_id": "WM-EMPTY-ROW", "receipt_governance_ids": []}
    )
    assert watermark.receipt_governance_ids == ()


def test_row_to_watermark_coerces_non_string_column_values() -> None:
    """A defensive `str()` coercion, exercised against non-`str` DBAPI values
    (e.g. a driver returning a `memoryview` or a psycopg-specific text type)
    rather than assumed to be a no-op."""

    class _Weird:
        def __str__(self) -> str:
            return "WM-WEIRD"

    watermark = _row_to_watermark(
        {"watermark_governance_id": _Weird(), "receipt_governance_ids": [_Weird()]}
    )
    assert watermark.watermark_governance_id == "WM-WEIRD"
    assert watermark.receipt_governance_ids == ("WM-WEIRD",)
