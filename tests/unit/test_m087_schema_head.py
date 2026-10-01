"""MILESTONE-087 -- two exact-head guards, two meanings, neither weakened.

`M085_SCHEMA_HEAD` is permanently the M085 revision; `M087_SCHEMA_HEAD` is the M087 revision.
Each guard accepts exactly its own revision and refuses the other's, any older revision, an
unknown newer revision, multiple heads and a missing version. The M087 revision descends
directly from the M085 revision; nothing was inserted into or replaced inside M085's history.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    M085_SCHEMA_HEAD,
    PaperSchemaHeadError,
    require_exact_m085_schema_head,
)
from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
    M087_SCHEMA_HEAD,
    ExitSchemaHeadError,
    require_exact_m087_schema_head,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_M085 = "".join(("a7d3c9", "e14f26"))
#: MILESTONE-090's own additive migration, no longer the sole head (RELEASE v1's own
#: migration now stacks beyond it -- see `_V1_APPROVED_PLAN` below). It carries no schema-
#: head guard of its own (see external-review/MILESTONE-090/scope-and-design.md Section 4
#: -- a research/read schema, not a real-broker safety gate), so there is no
#: `M090_SCHEMA_HEAD` constant to import from a persistence module; the revision id is
#: grouped here the same way `_M085` is above.
_M090 = "".join(("a2b4c6d8", "e0f2"))
#: RELEASE v1's own additive migration, the current sole head of this chain. It DOES carry
#: its own schema-head guard (`require_exact_v1_approved_plan_schema_head` in
#: `approved_plan_repositories.py`) since, unlike M090, it feeds a real-broker safety
#: decision (the automatic exit manager) -- see that migration's own docstring.
_V1_APPROVED_PLAN = "".join(("b9f2c4d6", "a8e1"))
_M087 = "".join(("e7c1a9", "d3b5f2"))
_OLDER = "".join(("9c4b2e", "7d5a18"))
_UNKNOWN_NEWER = "ffff" + "0" * 8


class _Work:
    def __init__(self, rows: list[dict[str, object]], failure: Exception | None) -> None:
        self._rows = rows
        self._failure = failure

    def __enter__(self) -> _Work:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, statement: str, parameters: object = None) -> list[dict[str, object]]:
        del statement, parameters
        if self._failure is not None:
            raise self._failure
        return list(self._rows)


class _Service:
    """Answers only the schema-revision query; opens nothing."""

    def __init__(self, rows: list[dict[str, object]], failure: Exception | None = None) -> None:
        self._rows = rows
        self._failure = failure

    def unit_of_work(self) -> Any:  # noqa: ANN401 - stands in for the real unit of work
        return _Work(self._rows, self._failure)


def _rows(*revisions: str) -> list[dict[str, object]]:
    return [{"version_num": r} for r in revisions]


def test_the_two_pins_are_the_two_reviewed_revisions() -> None:
    assert M085_SCHEMA_HEAD == _M085  # permanently the M085 revision
    assert M087_SCHEMA_HEAD == _M087
    assert M085_SCHEMA_HEAD != M087_SCHEMA_HEAD


def test_each_guard_accepts_exactly_its_own_revision() -> None:
    assert require_exact_m085_schema_head(_Service(_rows(_M085))) == _M085  # type: ignore[arg-type]
    assert require_exact_m087_schema_head(_Service(_rows(_M087))) == _M087  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("rows", "label"),
    [
        (_rows(_M085), "the M085 head"),
        (_rows(_OLDER), "an older revision"),
        (_rows(_UNKNOWN_NEWER), "an unknown newer revision"),
        (_rows(_M087, _M085), "multiple heads"),
        ([], "a missing version"),
    ],
)
def test_the_m087_guard_refuses_everything_but_the_m087_revision(
    rows: list[dict[str, object]], label: str
) -> None:
    with pytest.raises(ExitSchemaHeadError, match=_M087):
        require_exact_m087_schema_head(_Service(rows))  # type: ignore[arg-type]
    del label


@pytest.mark.parametrize(
    ("rows", "label"),
    [
        (_rows(_M087), "the M087 head -- a descendant is NOT the M085 head"),
        (_rows(_OLDER), "an older revision"),
        (_rows(_UNKNOWN_NEWER), "an unknown newer revision"),
        (_rows(_M085, _M087), "multiple heads"),
        ([], "a missing version"),
    ],
)
def test_the_m085_guard_is_not_weakened_and_refuses_the_m087_revision(
    rows: list[dict[str, object]], label: str
) -> None:
    with pytest.raises(PaperSchemaHeadError, match=_M085):
        require_exact_m085_schema_head(_Service(rows))  # type: ignore[arg-type]
    del label


def test_an_unreadable_revision_refuses_both_guards() -> None:
    with pytest.raises(ExitSchemaHeadError, match="could not be read"):
        require_exact_m087_schema_head(_Service([], RuntimeError("down")))  # type: ignore[arg-type]
    with pytest.raises(PaperSchemaHeadError, match="could not be read"):
        require_exact_m085_schema_head(_Service([], RuntimeError("down")))  # type: ignore[arg-type]


def test_the_m087_revision_descends_directly_from_the_m085_revision() -> None:
    """M087 stacks directly on M085 with nothing inserted between them.

    MILESTONE-090 pinned: M087 is no longer the sole head of the whole chain (M090's own
    additive migration now stacks beyond it) -- that broader claim moved to
    `test_the_m090_revision_is_the_sole_head_descending_linearly_from_m085_through_m087` below.
    This test keeps proving the narrower, still-true fact this file's docstring promises: M085
    -> M087 is direct, with no insertion or replacement inside that specific step.
    """
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    m087 = script.get_revision(M087_SCHEMA_HEAD)
    assert m087 is not None and m087.down_revision == M085_SCHEMA_HEAD
    m085 = script.get_revision(M085_SCHEMA_HEAD)
    assert m085 is not None and m085.down_revision == _OLDER
    # Exactly one revision sits above M085: nothing else was stacked, inserted or replaced
    # between M085 and M087 specifically.
    above = [
        r.revision
        for r in script.iterate_revisions(M087_SCHEMA_HEAD, M085_SCHEMA_HEAD)
        if r is not None and r.revision != M085_SCHEMA_HEAD
    ]
    assert above == [M087_SCHEMA_HEAD]


def test_the_v1_revision_is_the_sole_head_descending_linearly_from_m085_through_m090() -> None:
    """The chain remains a single, linear, non-branching history through RELEASE v1.

    Renamed/split again from the pre-v1 test of the same spirit (see the docstring above):
    the chain's sole head is now the v1 approved-plan revision, which descends directly
    from M090, which descends directly from M087, which descends directly from M085 --
    proven the same way, one link further each time.
    """
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [_V1_APPROVED_PLAN]
    v1 = script.get_revision(_V1_APPROVED_PLAN)
    assert v1 is not None and v1.down_revision == _M090
    m090 = script.get_revision(_M090)
    assert m090 is not None and m090.down_revision == M087_SCHEMA_HEAD
