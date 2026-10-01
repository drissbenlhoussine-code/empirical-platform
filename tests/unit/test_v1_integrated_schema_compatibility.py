"""RELEASE v1 -- the integrated-runtime schema-compatibility guard, on its own.

`require_v1_integrated_schema_compatibility` is a SECOND, distinctly-named guard from
`require_exact_m085_schema_head` (see `test_m087_schema_head.py` for that one, which this
pass leaves completely unchanged). It proves three independent things, each failing
closed on its own: the database is at exactly the one reviewed v1 head; `M085_SCHEMA_HEAD`
is a genuine ancestor of that head in the REAL Alembic revision graph this repository
ships; and the specific M085 tables Paper execution depends on still exist. None of the
three is "any later revision" -- an unknown future revision, a broken ancestry claim or a
missing table each refuse before anything is built.
"""

from __future__ import annotations

from typing import Any

import pytest

from empirical_platform.shared.persistence.postgres_repositories import (
    paper_execution_repositories,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    _M085_REQUIRED_TABLES,
    M085_SCHEMA_HEAD,
    V1_INTEGRATED_SCHEMA_HEAD,
    SchemaCompatibilityError,
    require_v1_integrated_schema_compatibility,
)

_UNKNOWN_NEWER = "ffff" + "0" * 8
_M084_HEAD = "".join(("a3f7c2", "1d9b04"))


def _all_tables() -> list[dict[str, object]]:
    return [{"tablename": t} for t in _M085_REQUIRED_TABLES]


class _Work:
    """Answers the revision query and the table-existence query by statement text."""

    def __init__(
        self,
        revision_rows: list[dict[str, object]],
        table_rows: list[dict[str, object]],
        failure: Exception | None,
    ) -> None:
        self._revision_rows = revision_rows
        self._table_rows = table_rows
        self._failure = failure

    def __enter__(self) -> _Work:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, statement: str, parameters: object = None) -> list[dict[str, object]]:
        del parameters
        if self._failure is not None:
            raise self._failure
        if "alembic_version" in statement:
            return list(self._revision_rows)
        return list(self._table_rows)


class _Service:
    """Answers only the two queries the guard issues; opens nothing."""

    def __init__(
        self,
        revision_rows: list[dict[str, object]],
        table_rows: list[dict[str, object]] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self._revision_rows = revision_rows
        self._table_rows = table_rows if table_rows is not None else _all_tables()
        self._failure = failure

    def unit_of_work(self) -> Any:  # noqa: ANN401 - stands in for the real unit of work
        return _Work(self._revision_rows, self._table_rows, self._failure)


def _rows(*revisions: str) -> list[dict[str, object]]:
    return [{"version_num": r} for r in revisions]


def test_the_pin_is_the_reviewed_v1_head() -> None:
    assert V1_INTEGRATED_SCHEMA_HEAD == "".join(("b9f2c4d6", "a8e1"))
    assert V1_INTEGRATED_SCHEMA_HEAD != M085_SCHEMA_HEAD


def test_the_exact_head_with_every_required_table_is_accepted() -> None:
    service = _Service(_rows(V1_INTEGRATED_SCHEMA_HEAD))
    assert (
        require_v1_integrated_schema_compatibility(service)  # type: ignore[arg-type]
        == V1_INTEGRATED_SCHEMA_HEAD
    )


@pytest.mark.parametrize(
    ("rows", "label"),
    [
        (_rows(M085_SCHEMA_HEAD), "the historical M085 head -- the exact production bug"),
        (_rows(_M084_HEAD), "an older revision"),
        (_rows(_UNKNOWN_NEWER), "an unknown, unreviewed newer revision"),
        (_rows(V1_INTEGRATED_SCHEMA_HEAD, M085_SCHEMA_HEAD), "multiple heads"),
        ([], "a missing version"),
    ],
)
def test_any_other_revision_refuses(rows: list[dict[str, object]], label: str) -> None:
    with pytest.raises(SchemaCompatibilityError, match=V1_INTEGRATED_SCHEMA_HEAD):
        require_v1_integrated_schema_compatibility(_Service(rows))  # type: ignore[arg-type]
    del label


def test_an_unreadable_database_refuses() -> None:
    service = _Service(_rows(V1_INTEGRATED_SCHEMA_HEAD), failure=RuntimeError("down"))
    with pytest.raises(SchemaCompatibilityError, match="could not be read"):
        require_v1_integrated_schema_compatibility(service)  # type: ignore[arg-type]


def test_a_missing_required_m085_table_refuses() -> None:
    incomplete = [row for row in _all_tables() if row["tablename"] != "paper_execution_attempt"]
    service = _Service(_rows(V1_INTEGRATED_SCHEMA_HEAD), table_rows=incomplete)
    with pytest.raises(SchemaCompatibilityError, match="paper_execution_attempt"):
        require_v1_integrated_schema_compatibility(service)  # type: ignore[arg-type]


def test_m085_is_a_genuine_ancestor_of_the_v1_head_in_the_real_migration_graph() -> None:
    """Not inferred from milestone numbers -- walked from the migrations this repo ships.

    This is the SAME chain `test_m087_schema_head.py`'s
    `test_the_v1_revision_is_the_sole_head_descending_linearly_from_m085_through_m090`
    already proves link-by-link; this test proves the guard's OWN ancestry walk -- over
    the real `migrations/` directory, not a mock -- reaches the v1 head successfully only
    because that walk actually finds M085 on the path.
    """
    service = _Service(_rows(V1_INTEGRATED_SCHEMA_HEAD))
    assert (
        require_v1_integrated_schema_compatibility(service)  # type: ignore[arg-type]
        == V1_INTEGRATED_SCHEMA_HEAD
    )


def test_the_ancestry_proof_fails_closed_for_an_unrelated_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ancestry proof is a REAL check, not a decoration that can never fail.

    Monkeypatches the module's own `M085_SCHEMA_HEAD` to a revision this repository's real
    `migrations/` directory does not contain on the v1 head's ancestry line at all, so the
    guard's ancestry walk -- which reads the real migration history, not a mock -- must
    conclude it is absent and refuse, even though the revision and table checks both pass.
    """
    monkeypatch.setattr(paper_execution_repositories, "M085_SCHEMA_HEAD", "0" * 12)
    service = _Service(_rows(V1_INTEGRATED_SCHEMA_HEAD))
    with pytest.raises(SchemaCompatibilityError, match="is not an ancestor"):
        require_v1_integrated_schema_compatibility(service)  # type: ignore[arg-type]


def test_an_unknown_head_fails_the_ancestry_lookup_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A head that is not in this repository's migration history at all fails closed too.

    Distinct from the previous test: there, the CONFIGURED head is real but M085 is not on
    its line; here, the configured head itself does not exist in the migration scripts this
    repository ships, so the ancestry walk cannot even start. Alembic's own
    `ScriptDirectory.get_revision` raises rather than returning `None` for a revision id it
    does not recognize, so this is caught by the walk's own broad failure handler -- still a
    fail-closed refusal, just folded into the "could not be read" message rather than the
    narrower "does not exist" one `_ancestor_revisions` would raise if `get_revision` ever
    returned `None` instead.
    """
    bogus_head = "ffff" + "1" * 8
    monkeypatch.setattr(paper_execution_repositories, "V1_INTEGRATED_SCHEMA_HEAD", bogus_head)
    service = _Service(_rows(bogus_head))
    with pytest.raises(
        SchemaCompatibilityError, match="could not be read to prove schema ancestry"
    ):
        require_v1_integrated_schema_compatibility(service)  # type: ignore[arg-type]


def test_an_unreadable_migration_history_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        paper_execution_repositories,
        "_MIGRATIONS_DIR",
        paper_execution_repositories._REPO_ROOT / "does-not-exist",
    )
    service = _Service(_rows(V1_INTEGRATED_SCHEMA_HEAD))
    with pytest.raises(SchemaCompatibilityError, match="could not be read"):
        require_v1_integrated_schema_compatibility(service)  # type: ignore[arg-type]


def test_the_refusal_is_an_operator_refusal() -> None:
    assert issubclass(SchemaCompatibilityError, ValueError)
