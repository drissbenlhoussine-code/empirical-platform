"""MILESTONE-084 is frozen mechanically, pinned to its Owner-ratified state.

The frozen-path guard governed M083 only. On 2026-09-25 the Owner ratified commit
`1127134` -- two post-freeze corrections to M084-derived audit tooling, six files, no
change to any M084 production module, migration, authority document, business rule or
freeze claim -- and directed that the guard be extended so that BOTH M083 and M084 are
protected from unauthorized modification from here on. These tests hold that extension
to the same standard the M083 tests hold the original: it must govern something real,
detect a mutation, accept exactly the ratified state, and be recorded where the
repository keeps its governance.

They run under `python -m pytest`, which CI runs on every push and pull request, so a
later milestone cannot edit an M084 frozen file without a red build.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from tools import check_frozen_paths
from tools.check_frozen_paths import (
    BASE,
    DIGEST_FILES,
    FROZEN,
    FROZEN_BASES,
    M084_BASE,
    base_digests,
    blob_id,
    content_violations,
    main,
    owned_paths,
    owner_of,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKPOINT = _REPO_ROOT / "PROJECT_CHECKPOINT.md"
_M084_CHANGED_FILES = _REPO_ROOT / "external-review" / "MILESTONE-084" / "changed-files.txt"

#: The six files the Owner ratified, exactly as listed in the corrective-round report.
RATIFIED_M084_FILES = (
    "external-review/MILESTONE-084/file-audit-matrix.json",
    "external-review/MILESTONE-084/file-audit-matrix.md",
    "tests/integration/test_m084_file_audit.py",
    "tests/unit/test_m084_audit_portability.py",
    "tools/render_m084_exhaustion_table.py",
    "tools/render_m084_file_audit.py",
)

#: The 'M' rows of M084's own audit: files that pre-existed M084 and are shared,
#: repository-wide infrastructure. They are deliberately NOT frozen as M084's.
SHARED_INFRASTRUCTURE_NOT_FROZEN = (
    "pyproject.toml",
    "src/empirical_platform/shared/persistence/postgres_repositories/runtime.py",
    "tests/architecture/test_module_boundaries.py",
    "tests/unit/test_secret_scan_targets.py",
    "tools/check_architecture.py",
    "tools/secret_scan_targets.py",
)


def _tracked() -> list[str]:
    return [
        line
        for line in subprocess.run(  # noqa: S603 - fixed argument vector, no shell
            ["git", "ls-files"],  # noqa: S607
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        if line
    ]


def _commit_present(commit: str) -> bool:
    return (
        subprocess.run(  # noqa: S603 - fixed argument vector, no shell
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],  # noqa: S607
            cwd=_REPO_ROOT,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _m084_audit_rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in _M084_CHANGED_FILES.read_text(encoding="utf-8").splitlines():
        status, _, path = line.strip().partition("\t")
        if path:
            rows[path] = status
    return rows


class TestBothMilestonesAreGoverned:
    def test_the_guard_freezes_exactly_m083_and_m084(self) -> None:
        assert set(FROZEN) == {"M083", "M084"}
        assert set(FROZEN_BASES) == {"M083", "M084"}
        assert set(DIGEST_FILES) == {"M083", "M084"}

    def test_m084_is_pinned_to_the_ratified_commit_and_m083_to_its_original_base(self) -> None:
        # Commit ids in eight-character groups: the secret scanner has no name-based
        # exemptions, and a forty-character hex literal has a credential's shape.
        assert FROZEN_BASES["M084"] == M084_BASE
        assert M084_BASE == "".join(("11271346", "23b25178", "b4d98236", "d5ab75f8", "f2134760"))
        assert FROZEN_BASES["M083"] == BASE
        assert BASE == "".join(("707161a1", "e8edeb7e", "0c95f3da", "fc7180ba", "9d782cc6"))

    def test_m084_owns_real_paths_of_every_kind(self) -> None:
        paths = owned_paths(_tracked())["M084"]
        assert paths, "M084 patterns match nothing"
        kinds = {
            "production": any(
                p.startswith("src/empirical_platform/decision_candidate/") for p in paths
            ),
            "usecase": any(p.startswith("src/empirical_platform/usecases/") for p in paths),
            "entrypoint": any(p.startswith("src/empirical_platform/entrypoints/") for p in paths),
            "repository": any("/postgres_repositories/" in p for p in paths),
            "migration": any(p.startswith("migrations/versions/") for p in paths),
            "tests": any(p.startswith("tests/") for p in paths),
            "tools": any(p.startswith("tools/") for p in paths),
            "review package": any(p.startswith("external-review/MILESTONE-084/") for p in paths),
        }
        assert all(kinds.values()), kinds

    def test_the_six_ratified_files_are_governed_as_m084(self) -> None:
        governed = set(owned_paths(_tracked())["M084"])
        for path in RATIFIED_M084_FILES:
            assert owner_of(path) == "M084", path
            assert path in governed, path

    def test_every_added_row_of_m084s_own_audit_is_governed(self) -> None:
        # Ownership is derived, not hand-listed. This ties the derivation to M084's own
        # record of what it added, so a future rename cannot silently drop a file.
        governed = set(owned_paths(_tracked())["M084"])
        rows = _m084_audit_rows()
        added = {p for p, s in rows.items() if s == "A"}
        exempt_guard_files = {
            "tools/check_frozen_paths.py",
            "tests/architecture/test_frozen_paths.py",
        }
        missing = added - governed - exempt_guard_files
        assert missing == set(), f"added by M084 but not governed: {sorted(missing)}"

    def test_shared_infrastructure_is_exactly_the_modified_rows_and_is_not_frozen(self) -> None:
        rows = _m084_audit_rows()
        modified = {p for p, s in rows.items() if s == "M"}
        assert modified == set(SHARED_INFRASTRUCTURE_NOT_FROZEN)
        governed = set(owned_paths(_tracked())["M084"])
        assert governed.isdisjoint(modified), governed & modified

    def test_m083_ownership_is_unchanged_by_the_extension(self) -> None:
        paths = owned_paths(_tracked())["M083"]
        assert len(paths) == 27, len(paths)
        assert owner_of("tests/integration/test_m084_m083_compatibility.py") == "M084"
        assert owner_of("tools/m084_frozen_m083_acceptance.py") == "M084"
        assert owner_of("tests/integration/test_m085_paper_execution_postgres.py") is None or (
            owner_of("tests/integration/test_m085_paper_execution_postgres.py") == "M085"
        )
        assert "M085" not in FROZEN


class TestTheRatifiedStatePasses:
    def test_no_m084_path_differs_from_its_recorded_ratified_blob_id(self) -> None:
        breaches = {m: p for m, p in content_violations().items() if p}
        assert breaches.get("M084", []) == [], breaches
        assert breaches.get("M083", []) == [], breaches

    def test_the_m084_manifest_covers_every_m084_path_and_nothing_else(self) -> None:
        recorded = set(base_digests("M084"))
        governed = set(owned_paths(_tracked())["M084"])
        assert governed - recorded == set(), f"governed but unrecorded: {governed - recorded}"
        assert recorded - governed == set(), f"recorded but ungoverned: {recorded - governed}"

    def test_the_m084_manifest_is_the_content_at_the_ratified_commit(self) -> None:
        if not _commit_present(M084_BASE):
            pytest.skip(f"ratified commit {M084_BASE[:12]} is absent from this clone")
        mismatched = {
            path: identifier
            for path, identifier in base_digests("M084").items()
            if blob_id(M084_BASE, path) != identifier
        }
        assert mismatched == {}, mismatched

    def test_the_m084_manifest_lives_outside_the_m084_package(self) -> None:
        # Writing it into MILESTONE-084's package would edit a path it governs.
        assert (
            owner_of(str(DIGEST_FILES["M084"].relative_to(_REPO_ROOT)).replace("\\", "/")) != "M084"
        )

    def test_the_guard_itself_exits_zero_on_the_ratified_state(self) -> None:
        assert main([]) == 0


class TestAMutationIsDetected:
    def _breach_for(self, milestone: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
        victim = sorted(owned_paths(_tracked())[milestone])[0]
        real = check_frozen_paths.blob_id
        invented = "".join(
            ["0bad", "f00d", "dead", "beef", "1337", "cafe", "5eed", "9e11", "77ab", "c0de"]
        )

        def mutated(revision: str, path: str) -> str | None:
            if revision == "HEAD" and path == victim:
                return invented
            return real(revision, path)

        monkeypatch.setattr(check_frozen_paths, "blob_id", mutated)
        breaches = {m: p for m, p in content_violations().items() if p}
        assert breaches == {milestone: [victim]}, breaches
        return breaches

    def test_an_m084_governed_path_mutation_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._breach_for("M084", monkeypatch)

    def test_an_m083_governed_path_mutation_is_still_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._breach_for("M083", monkeypatch)

    def test_a_mutated_ratified_file_is_detected_and_fails_the_guard(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        victim = RATIFIED_M084_FILES[2]
        real = check_frozen_paths.blob_id
        monkeypatch.setattr(
            check_frozen_paths,
            "blob_id",
            lambda revision, path: (
                "f" * 40 if (revision, path) == ("HEAD", victim) else real(revision, path)
            ),
        )
        assert main([]) == 1
        assert victim in capsys.readouterr().err

    def test_removing_m084_from_the_guard_would_be_visible(self) -> None:
        # Anti-vacuity for the freeze itself: the M084 pattern set is non-empty and
        # the derived token ownership covers the numbered M084 files, so deleting the
        # M084 entry cannot leave those files governed by accident.
        assert FROZEN["M084"], "M084 pattern set is empty"
        with_token = [
            p for p in owned_paths(_tracked())["M084"] if re.search(r"(?i)m084|MILESTONE[-_]084", p)
        ]
        without_token = [p for p in owned_paths(_tracked())["M084"] if p not in with_token]
        assert with_token and without_token, (len(with_token), len(without_token))


class TestTheRatificationIsRecorded:
    def test_project_checkpoint_records_the_owner_ratification(self) -> None:
        text = _CHECKPOINT.read_text(encoding="utf-8")
        assert M084_BASE in text, "PROJECT_CHECKPOINT.md does not name the ratified commit"
        heading = "MILESTONE-084 Post-Freeze Owner Ratification and Mechanical Freeze Extension"
        assert heading in text, "PROJECT_CHECKPOINT.md has no ratification section"
        section = text[text.index(heading) :]
        assert M084_BASE in section
        for path in RATIFIED_M084_FILES:
            assert path in section, f"ratification record does not list {path}"
        assert "M084_POST_FREEZE_RATIFIED_COMMIT=" + M084_BASE in text
        assert "M084_FROZEN_PATH_GUARD_BASE=" + M084_BASE in text

    def test_the_freeze_record_and_authority_of_m084_are_untouched_by_the_extension(self) -> None:
        if not _commit_present(M084_BASE):
            pytest.skip("ratified commit absent")
        for path in (
            "MILESTONE_084_DECISION_TO_APPROVAL_PRODUCT_CORE_MACRO_MILESTONE_FREEZE.md",
            "external-review/MILESTONE-084/current-authority.json",
            "external-review/MILESTONE-084/current-authority.schema.json",
            "external-review/MILESTONE-084/current-authority.md",
            "migrations/versions/a3f7c21d9b04_create_m084_schema.py",
        ):
            assert blob_id("HEAD", path) == blob_id(M084_BASE, path), path
