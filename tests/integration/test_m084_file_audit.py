"""MILESTONE-084 -- the file-audit matrix is checked, not asserted.

A published "we audited every changed file" claim is worth nothing unless the
matrix's own path set is mechanically tied to a real diff. This file ties it
four ways, and the last is the one that survives a shallow CI checkout:

  1. against `git diff --name-status BASE..HEAD` over the PINNED range, when
     both pinned commits are present in the clone;
  2. against the pinned tree's own file contents, so a recorded line count is
     the count the approved commit actually holds;
  3. against `changed-files.txt`, the package's own record of the diff;
  4. against the filesystem -- every listed path must still exist, and nothing
     may be listed twice or numbered out of order.

Checks 1 and 2 are skipped in a shallow clone because the pinned commits are
genuinely absent, and the skip REPORTS ITSELF rather than passing quietly: a
suite that silently degrades its own strongest check is worse than one that
never had it. Checks 3 and 4 always run.

Why the range is pinned, and what that fixes (FIND-F-01)
--------------------------------------------------------

The original checks compared `BASE..HEAD` against the moving branch tip, and
compared recorded line counts against the WORKING TREE. Both were correct while
this branch WAS the pull request. Both became wrong at merge:

  * `..HEAD` then also swept in the merge, freeze and checkpoint commits, so the
    matrix was compared against a path set two files larger than the one that
    was reviewed, and the render crashed on a path it had no ownership rule for;
  * the working-tree line counts followed any later edit to a shared toolchain
    file, so a legitimate later change would report M084's audit as stale.

Both ends are now pinned to the approved M084 tree. The pin is not a pair of
magic numbers: `BASE` and `HEAD` are asserted here to be the two parents of the
recorded `MERGE` commit, so a transcription slip in any one of the three fails
loudly instead of silently auditing the wrong tree. The tests below also assert
that the pinned range EXCLUDES the post-merge governance commits, which is the
exact regression FIND-F-01 was.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tools.render_m084_file_audit import (
    BASE,
    BASE_GROUPS,
    EXIT_RANGE_UNAVAILABLE,
    HEAD,
    HEAD_GROUPS,
    MERGE,
    blob_text,
    build,
    changed_status,
    commit_present,
    main,
    range_available,
    render_markdown,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "external-review" / "MILESTONE-084"
_MATRIX = _PACKAGE / "file-audit-matrix.json"
_MATRIX_MARKDOWN = _PACKAGE / "file-audit-matrix.md"
_CHANGED_FILES = _PACKAGE / "changed-files.txt"

# The two paths that the stale `..HEAD` range swept in once the pull request was
# merged. Named explicitly so the regression cannot come back unnoticed.
_POST_MERGE_GOVERNANCE_PATHS = frozenset(
    {
        "PROJECT_CHECKPOINT.md",
        "MILESTONE_084_DECISION_TO_APPROVAL_PRODUCT_CORE_MACRO_MILESTONE_FREEZE.md",
    }
)


@pytest.fixture(scope="module")
def matrix() -> dict[str, Any]:
    return json.loads(_MATRIX.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _git(*arguments: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", *arguments],  # noqa: S607
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _parents(commit: str) -> list[str]:
    return _git("rev-list", "--parents", "-n", "1", commit).split()[1:]


def _requires_pinned_range() -> None:
    if not range_available():
        pytest.skip(
            f"pinned commits {BASE[:12]}/{HEAD[:12]} are absent from this clone "
            "(shallow checkout); the changed-files.txt and filesystem checks still ran"
        )


class TestTheMatrixIsInternallySound:
    def test_the_declared_count_matches_the_rows(self, matrix: dict[str, Any]) -> None:
        assert matrix["count"] == len(matrix["files"])

    def test_the_base_is_the_one_the_campaign_declares(self, matrix: dict[str, Any]) -> None:
        assert "".join(matrix["base_groups"]) == BASE

    def test_the_head_is_the_one_the_campaign_declares(self, matrix: dict[str, Any]) -> None:
        assert "".join(matrix["head_groups"]) == HEAD

    def test_the_recorded_commits_are_grouped_and_carry_no_forty_hex_token(
        self, matrix: dict[str, Any]
    ) -> None:
        # The matrix records both commits in groups so that no token in the
        # generated file is a 40-character hex string. Storing either as one
        # string would put the file back in front of the secret scanner and
        # require an exemption keyed on the word "base", which proves nothing
        # about the value it would clear.
        for key in ("base_groups", "head_groups"):
            groups = matrix[key]
            assert isinstance(groups, list), key
            assert all(len(group) == 8 for group in groups[:-1]), (key, groups)
        assert re.search(r"[0-9a-f]{40}", _MATRIX.read_text(encoding="utf-8")) is None

    def test_numbering_is_contiguous_and_starts_at_one(self, matrix: dict[str, Any]) -> None:
        assert [row["n"] for row in matrix["files"]] == list(range(1, matrix["count"] + 1))

    def test_no_path_is_listed_twice(self, matrix: dict[str, Any]) -> None:
        paths = [row["path"] for row in matrix["files"]]
        assert len(set(paths)) == len(paths)

    def test_paths_are_sorted_so_the_matrix_is_diffable(self, matrix: dict[str, Any]) -> None:
        paths = [row["path"] for row in matrix["files"]]
        assert paths == sorted(paths)

    def test_every_row_is_fully_populated(self, matrix: dict[str, Any]) -> None:
        for row in matrix["files"]:
            assert set(row) == {"n", "path", "status", "ownership", "lines", "surface"}
            assert row["status"] in {"new", "modified"}
            assert row["ownership"] != "?", row["path"]
            assert row["surface"], row["path"]


class TestThePinProvesItself:
    """The pin is three commit ids. Git decides whether they are the right ones."""

    def test_the_recorded_merge_commit_is_actually_a_merge(self) -> None:
        _requires_pinned_range()
        if not commit_present(MERGE):
            pytest.skip(f"merge commit {MERGE[:12]} is absent from this clone")
        assert len(_parents(MERGE)) == 2

    def test_base_and_head_are_the_two_parents_of_the_merge(self) -> None:
        # This is what makes BASE and HEAD evidence rather than assertion. A
        # mistyped digit in any of the three fails here.
        _requires_pinned_range()
        if not commit_present(MERGE):
            pytest.skip(f"merge commit {MERGE[:12]} is absent from this clone")
        assert _parents(MERGE) == [BASE, HEAD]

    def test_the_grouped_constants_join_to_the_full_ids(self) -> None:
        assert "".join(BASE_GROUPS) == BASE
        assert "".join(HEAD_GROUPS) == HEAD
        assert len(BASE) == 40
        assert len(HEAD) == 40


class TestTheMatrixMatchesTheFilesystem:
    def test_every_listed_path_exists(self, matrix: dict[str, Any]) -> None:
        missing = [
            row["path"] for row in matrix["files"] if not (_REPO_ROOT / row["path"]).is_file()
        ]
        assert missing == []


class TestTheMatrixMatchesTheApprovedTree:
    def test_every_recorded_line_count_matches_the_approved_commit(
        self, matrix: dict[str, Any]
    ) -> None:
        # Against the PINNED commit, not the working tree. A stale count here
        # means the matrix does not describe the tree M084 delivered. Whether
        # today's files still match that tree is a different question, and
        # `tools/check_frozen_paths.py` is what asks it.
        _requires_pinned_range()
        drifted = [
            f"{row['path']}: matrix says {row['lines']}, approved commit has {actual}"
            for row in matrix["files"]
            if (actual := len(blob_text(row["path"]).splitlines())) != row["lines"]
        ]
        assert drifted == []


class TestTheMatrixMatchesTheDeclaredDiff:
    def test_the_matrix_equals_changed_files_txt(self, matrix: dict[str, Any]) -> None:
        recorded = {
            line.split("\t", 1)[1]
            for line in _CHANGED_FILES.read_text(encoding="utf-8").splitlines()
            if "\t" in line and line[0] in {"A", "M", "D"}
        }
        assert {row["path"] for row in matrix["files"]} == recorded


class TestTheMatrixMatchesGit:
    def test_the_pinned_commit_presence_is_reported_not_assumed(self) -> None:
        # Not a check of the diff -- a check that the next skips, if they
        # happen, happen for the stated reason and not for a broken git.
        assert isinstance(range_available(), bool)
        assert isinstance(commit_present(BASE), bool)

    def test_the_matrix_equals_the_pinned_diff(self, matrix: dict[str, Any]) -> None:
        _requires_pinned_range()
        assert {row["path"] for row in matrix["files"]} == set(changed_status())

    def test_the_pinned_range_is_not_empty(self, matrix: dict[str, Any]) -> None:
        # Anti-vacuity: an empty diff would make the comparison above trivially
        # true against an empty matrix.
        _requires_pinned_range()
        assert len(changed_status()) == matrix["count"] > 0


class TestThePinExcludesThePostMergeHistory:
    """FIND-F-01, held fixed. This is the exact failure, named."""

    def test_the_pinned_range_excludes_the_post_merge_governance_paths(self) -> None:
        _requires_pinned_range()
        assert _POST_MERGE_GOVERNANCE_PATHS.isdisjoint(changed_status())

    def test_those_paths_are_real_and_would_have_been_swept_in_by_the_branch_tip(self) -> None:
        # The other half of the anti-vacuity pair: the paths above must be ones
        # that a `..HEAD` comparison ACTUALLY pulls in, or excluding them proves
        # nothing. Once master carries the merge, the tip-relative range differs
        # from the pinned range by exactly those governance paths.
        _requires_pinned_range()
        if not commit_present(MERGE):
            pytest.skip(f"merge commit {MERGE[:12]} is absent from this clone")
        head_is_past_the_merge = (
            subprocess.run(  # noqa: S603 - fixed argument vector, no shell
                ["git", "merge-base", "--is-ancestor", MERGE, "HEAD"],  # noqa: S607
                cwd=_REPO_ROOT,
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
        if not head_is_past_the_merge:
            pytest.skip("this checkout does not yet contain the M084 merge commit")
        tip_relative = set(_git("diff", "--name-only", f"{BASE}..HEAD").split())
        assert _POST_MERGE_GOVERNANCE_PATHS <= tip_relative
        assert tip_relative != set(changed_status())


class TestTheRenderedMatrixIsTheGate:
    """`--check` runs inside the suite, so CI enforces it without a new job."""

    def test_the_committed_matrix_is_the_current_rendering(self) -> None:
        _requires_pinned_range()
        assert main(["--check"]) == 0

    def test_the_markdown_is_the_deterministic_rendering_of_the_json(
        self, matrix: dict[str, Any]
    ) -> None:
        _requires_pinned_range()
        assert _MATRIX_MARKDOWN.read_text(encoding="utf-8") == render_markdown(matrix)

    def test_a_drifted_line_count_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Anti-vacuity for the gate itself. `--check` is only worth running if a
        # wrong value makes it fail, so mutate one and require exit 1. The real
        # package files are never touched: the module's targets are redirected
        # into tmp_path.
        _requires_pinned_range()
        import tools.render_m084_file_audit as module

        mutated = build()
        mutated["files"][0]["lines"] += 1
        json_target = tmp_path / "file-audit-matrix.json"
        markdown_target = tmp_path / "file-audit-matrix.md"
        json_target.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
        markdown_target.write_text(render_markdown(mutated), encoding="utf-8")
        monkeypatch.setattr(module, "MATRIX_JSON", json_target)
        monkeypatch.setattr(module, "MATRIX_MARKDOWN", markdown_target)

        assert main(["--check"]) == 1

    def test_an_absent_pinned_commit_is_reported_rather_than_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The shallow-clone path, exercised rather than described: when the pin
        # cannot be resolved, `--check` must not return 0.
        import tools.render_m084_file_audit as module

        monkeypatch.setattr(module, "range_available", lambda: False)
        assert main(["--check"]) == EXIT_RANGE_UNAVAILABLE
        assert EXIT_RANGE_UNAVAILABLE != 0
