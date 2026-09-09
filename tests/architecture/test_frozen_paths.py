"""A frozen milestone's files are not editable by later work.

M084 modified two M083-owned test files -- adding CASCADE to M083's reset and
rewriting M083's downgrade-target helper -- because M084's foreign key had made
M083's suite fail. The edits were small, well-intentioned and wrong: they turn
"M083 still passes" into "M083 passes a test M084 rewrote", which is not the
same claim and is not the one the freeze was for. Nothing mechanical objected
at the time. These tests are that objection.

The guard is deliberately structural rather than semantic. Asking a reviewer to
decide, per diff, whether an edit "really" changed a frozen milestone's meaning
puts the judgement in the worst possible place: with the author of the change.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools.check_frozen_paths import BASE, EXEMPT, FROZEN, owned_paths, owner_of, violations

_REPO_ROOT = Path(__file__).resolve().parents[2]


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


class TestTheGuardGovernsSomething:
    def test_every_frozen_milestone_owns_at_least_one_real_path(self) -> None:
        # A pattern set matching nothing would pass the guard while governing
        # nothing -- worse than having no guard, because it reads as one.
        owners = owned_paths(_tracked())
        assert owners
        for milestone, paths in owners.items():
            assert paths, f"{milestone} owns no tracked paths"

    def test_m083_ownership_covers_its_tests_production_migration_and_authority(self) -> None:
        # Ownership derived from names could silently miss a whole category, so
        # each category the freeze covers is named here explicitly.
        paths = owned_paths(_tracked())["M083"]
        assert any(p.startswith("tests/integration/test_m083_") for p in paths)
        assert any(p.startswith("tests/unit/") for p in paths)
        assert any(p.startswith("src/empirical_platform/") for p in paths)
        assert any(p.startswith("migrations/versions/") for p in paths)
        assert any(p.startswith("external-review/MILESTONE-083/") for p in paths)
        assert any(p.startswith("tools/render_m083_authority") for p in paths)

    def test_the_two_files_m084_edited_are_governed(self) -> None:
        # The specific regression this guard exists to prevent.
        paths = set(owned_paths(_tracked())["M083"])
        assert "tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py" in paths
        assert (
            "tests/integration/test_m083_evaluation_evidence_watermark_extended_attacks.py" in paths
        )


class TestOwnershipGoesToTheHighestMilestoneNamed:
    """A later milestone owns what it authors about an earlier one."""

    def test_a_path_naming_one_milestone_belongs_to_it(self) -> None:
        assert owner_of("tests/integration/test_m083_authority_contract.py") == "M083"
        assert owner_of("tools/render_m083_authority.py") == "M083"
        assert owner_of("external-review/MILESTONE-083/README.md") == "M083"
        assert owner_of("tests/integration/test_m084_concurrency.py") == "M084"

    def test_a_path_naming_two_milestones_belongs_to_the_later_one(self) -> None:
        # M084's replacement coverage for the frozen M083 suites names M083
        # loudly, because that is what it is about. Reading it as M083's would
        # freeze M084's own new tests the moment they were written.
        assert owner_of("tests/integration/test_m084_m083_compatibility.py") == "M084"
        assert owner_of("tools/m084_frozen_m083_acceptance.py") == "M084"

    def test_a_path_naming_no_milestone_falls_back_to_the_primitive(self) -> None:
        # M083's production and test modules are named after the primitive it
        # introduced, not after its number.
        assert (
            owner_of("src/empirical_platform/decision_candidate/evaluation_evidence_watermark.py")
            == "M083"
        )
        assert owner_of("tests/unit/test_evaluation_evidence_watermark_io.py") == "M083"
        assert owner_of("pyproject.toml") is None

    def test_the_milestone_token_needs_a_boundary(self) -> None:
        # Guards against a hex migration id or a longer word being read as a
        # milestone number.
        assert owner_of("migrations/versions/a3f7c21d9b04_create_m084_schema.py") == "M084"
        assert owner_of("docs/m0834_notes.md") is None


class TestNothingFrozenChanged:
    def test_no_frozen_path_differs_from_the_base_commit(self) -> None:
        breaches = {milestone: paths for milestone, paths in violations().items() if paths}
        assert breaches == {}, (
            f"frozen milestone files were modified between {BASE[:12]} and HEAD: {breaches}. "
            "Fix the later milestone's own code, build a harness it owns, or record a "
            "measured limitation -- and restore these paths byte-for-byte."
        )

    def test_the_exemption_list_is_empty(self) -> None:
        # An exemption needs pre-existing repository policy establishing the
        # path as shared, non-frozen infrastructure. An author's judgement that
        # their own edit is harmless is not such policy, and this assertion is
        # here so that adding one has to be a deliberate, reviewed act.
        assert EXEMPT == frozenset()

    def test_the_guard_names_the_frozen_milestones_it_knows(self) -> None:
        assert set(FROZEN) == {"M083"}
