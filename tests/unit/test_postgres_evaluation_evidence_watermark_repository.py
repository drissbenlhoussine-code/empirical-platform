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


# --------------------------------------------------------------------------
# AUDIT FINDING M083-AUD-001 -- fail-closed row mapping.
#
# RETRACTED PREDECESSOR: this file previously asserted the OPPOSITE contract,
# in `test_row_to_watermark_coerces_non_string_column_values`, which called a
# `str()` coercion of arbitrary DBAPI values "defensive" and asserted that an
# object whose `__str__` returned "WM-WEIRD" became the governance identity
# "WM-WEIRD". That test enshrined the defect rather than catching it: the same
# coercion silently converted a stored NULL array element into the receipt
# identity 'None', a memoryview into '<memory at 0x...>' and an integer into
# '1', each then counted by `captured_receipt_count` as a real M082 receipt --
# fabricating exactly the "exact receipt-identity set" this milestone claims.
#
# A NULL array ELEMENT is not hypothetical: PostgreSQL's NOT NULL applies to
# the array value, not its members, so ARRAY['real-id', NULL] is storable in
# this column, and SQLAlchemy/psycopg hands it back as a Python None. That was
# measured directly against the real schema, and the corrupt row was then read
# back through the real repository, before this contract was changed.
#
# The domain type's duplicate/canonical-order checks are NOT a substitute:
# they caught a stringified NULL only INCIDENTALLY, and only when 'None'
# happened to sort out of position. `['A-real-id', NULL]` stringifies to an
# ascending pair and passed. The tests below therefore assert the REASON for
# the refusal, not merely that something was raised.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("malformed_value", "expected_type_name"),
    [
        pytest.param(None, "NoneType", id="null-element"),
        pytest.param(memoryview(b"abc"), "memoryview", id="memoryview-element"),
        pytest.param(1, "int", id="int-element"),
        pytest.param(b"RC-A", "bytes", id="bytes-element"),
        pytest.param(["RC-A"], "list", id="nested-list-element"),
    ],
)
def test_row_to_watermark_refuses_a_non_string_receipt_element(
    malformed_value: object, expected_type_name: str
) -> None:
    with pytest.raises(FoundationError) as excinfo:
        _row_to_watermark(
            {
                "watermark_governance_id": "WM-ROW",
                "receipt_governance_ids": ["A-real-id", malformed_value],
            }
        )
    error = excinfo.value
    assert error.category is FoundationErrorCategory.PERSISTENCE
    assert error.operation == "evaluation_evidence_watermark.row_mapping"
    # The refusal must name the offending POSITION and the ACTUAL type -- i.e.
    # it is a type check, not an incidental ordering or duplicate complaint.
    assert "receipt_governance_ids[1]" in error.safe_message
    assert expected_type_name in error.safe_message


def test_row_to_watermark_refuses_a_null_element_that_sorts_into_canonical_position() -> None:
    """The exact case the domain type's order check does NOT catch.

    'A-real-id' < 'None' under byte-order comparison, so a stringified NULL
    lands in canonical ascending position and the pre-fix mapping ACCEPTED it,
    reporting `('A-real-id', 'None')` as the stored receipt set.
    """
    with pytest.raises(FoundationError) as excinfo:
        _row_to_watermark(
            {
                "watermark_governance_id": "WM-ROW",
                "receipt_governance_ids": ["A-real-id", None],
            }
        )
    assert "not str" in excinfo.value.safe_message
    assert "canonical" not in excinfo.value.safe_message


@pytest.mark.parametrize(
    ("malformed_value", "expected_type_name"),
    [
        pytest.param(None, "NoneType", id="null-identity"),
        pytest.param(b"WM-ROW", "bytes", id="bytes-identity"),
        pytest.param(7, "int", id="int-identity"),
    ],
)
def test_row_to_watermark_refuses_a_non_string_identity(
    malformed_value: object, expected_type_name: str
) -> None:
    with pytest.raises(FoundationError) as excinfo:
        _row_to_watermark(
            {"watermark_governance_id": malformed_value, "receipt_governance_ids": []}
        )
    assert "watermark_governance_id" in excinfo.value.safe_message
    assert expected_type_name in excinfo.value.safe_message


def test_row_to_watermark_refuses_a_non_array_receipt_column() -> None:
    with pytest.raises(FoundationError) as excinfo:
        _row_to_watermark({"watermark_governance_id": "WM-ROW", "receipt_governance_ids": None})
    assert "not an array" in excinfo.value.safe_message


def test_row_to_watermark_refuses_a_stringable_object_instead_of_trusting_dunder_str() -> None:
    """An object with a convenient `__str__` is still not a stored string.

    This is the precise inversion of the retracted predecessor test: the
    mapping must refuse it rather than adopt whatever `__str__` returns as an
    authoritative governance identity.
    """

    class _Weird:
        def __str__(self) -> str:
            return "WM-WEIRD"

    with pytest.raises(FoundationError):
        _row_to_watermark({"watermark_governance_id": _Weird(), "receipt_governance_ids": []})


def test_row_to_watermark_still_accepts_a_well_formed_row_unchanged() -> None:
    """Fail-closed must not mean fail-often: the real driver's own output shape
    (`str` and `list[str]`, measured against this schema) maps exactly as before.
    """
    watermark = _row_to_watermark(
        {"watermark_governance_id": "WM-OK", "receipt_governance_ids": ["RC-A", "RC-B"]}
    )
    assert watermark.watermark_governance_id == "WM-OK"
    assert watermark.receipt_governance_ids == ("RC-A", "RC-B")
    assert watermark.captured_receipt_count == 2
