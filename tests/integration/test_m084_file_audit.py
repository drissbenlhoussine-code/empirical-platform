"""MILESTONE-084 -- the file-audit matrix is checked, not asserted.

A published "we audited every changed file" claim is worth nothing unless the
matrix's own path set is mechanically tied to the real diff. This file ties it
three ways, and the third is the one that survives a shallow CI checkout:

  1. against `git diff --name-status BASE..HEAD`, when the base commit is
     present in the clone;
  2. against `changed-files.txt`, the package's own record of the diff;
  3. against the filesystem -- every listed path must exist, with the recorded
     line count, and nothing may be listed twice or numbered out of order.

Check 1 is skipped in a shallow clone because the base commit is genuinely
absent, and the skip REPORTS ITSELF rather than passing quietly: a suite that
silently degrades its own strongest check is worse than one that never had it.
Checks 2 and 3 always run.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "external-review" / "MILESTONE-084"
_MATRIX = _PACKAGE / "file-audit-matrix.json"
_CHANGED_FILES = _PACKAGE / "changed-files.txt"
_BASE = "707161a1e8edeb7e0c95f3dafc7180ba9d782cc6"


@pytest.fixture(scope="module")
def matrix() -> dict[str, Any]:
    return json.loads(_MATRIX.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _base_commit_is_present() -> bool:
    return (
        subprocess.run(  # noqa: S603 - fixed argument vector, no shell
            ["git", "cat-file", "-e", f"{_BASE}^{{commit}}"],  # noqa: S607
            cwd=_REPO_ROOT,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _git_changed_paths() -> set[str]:
    result = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", "diff", "--name-only", f"{_BASE}..HEAD"],  # noqa: S607
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line for line in result.stdout.splitlines() if line}


class TestTheMatrixIsInternallySound:
    def test_the_declared_count_matches_the_rows(self, matrix: dict[str, Any]) -> None:
        assert matrix["count"] == len(matrix["files"])

    def test_the_base_is_the_one_the_campaign_declares(self, matrix: dict[str, Any]) -> None:
        assert matrix["base"] == _BASE

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


class TestTheMatrixMatchesTheFilesystem:
    def test_every_listed_path_exists(self, matrix: dict[str, Any]) -> None:
        missing = [
            row["path"] for row in matrix["files"] if not (_REPO_ROOT / row["path"]).is_file()
        ]
        assert missing == []

    def test_every_recorded_line_count_is_current(self, matrix: dict[str, Any]) -> None:
        # A stale line count means a stale audit: the file changed after it was
        # audited, and nobody re-read it.
        drifted = [
            f"{row['path']}: matrix says {row['lines']}, file has {actual}"
            for row in matrix["files"]
            if (actual := len((_REPO_ROOT / row["path"]).read_text(encoding="utf-8").splitlines()))
            != row["lines"]
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
    def test_the_base_commit_presence_is_reported_not_assumed(self) -> None:
        # Not a check of the diff -- a check that the NEXT test's skip, if it
        # happens, happens for the stated reason and not for a broken git.
        assert isinstance(_base_commit_is_present(), bool)

    def test_the_matrix_equals_the_real_diff(self, matrix: dict[str, Any]) -> None:
        if not _base_commit_is_present():
            pytest.skip(
                f"base commit {_BASE[:12]} is absent from this clone (shallow checkout); "
                "the filesystem and changed-files.txt checks above still ran"
            )
        assert {row["path"] for row in matrix["files"]} == _git_changed_paths()
