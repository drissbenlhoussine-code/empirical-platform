"""The M085 base-commit pin is well formed, and really is this branch's base.

WHY THIS FILE EXISTS. `tools/render_m085_exhaustion_table.py` pinned the required
base commit with a single-character transcription error (`62d50e51` where the
commit reads `64e50e51`). Nothing failed. The exhaustion table simply reported
item 1 as `EXECUTED_FAIL_BLOCKER` with the evidence `branch base is (unresolved)`,
because `git merge-base` against a nonexistent object prints nothing — so a WRONG
PIN and an ACTUALLY-WRONG BASE were indistinguishable in the output. A gate that
cannot tell "you are on the wrong base" from "I cannot read my own pin" is not a
gate.

The M084 tooling has `tests/unit/test_m084_audit_portability.py` pinning its
commits across four tools, which is why the same class of error was caught there.
M085 pinned its base in one tool and tested it nowhere.

WHY SOME CHECKS SKIP, AND WHY THE SKIP REPORTS ITSELF
-----------------------------------------------------

GitHub Actions checks out with `fetch-depth: 1`, so the pinned base commit is
genuinely absent from the CI clone and every history question about it is
unanswerable there. The first version of this file asserted those questions
unconditionally and FAILED CI — which is the same mistake as FIND-P5-03, a test
asserting a property of the CHECKOUT rather than of the content.

The fix is the pattern `tests/integration/test_m084_file_audit.py` already
established for exactly this: history-dependent checks skip when the history is
absent, and the skip **reports itself** rather than passing quietly, because a
suite that silently degrades its own strongest check is worse than one that never
had it. The form checks and the corrupted-pin detection below always run.

The corruption checks are guarded too, and deliberately: with no history present,
a real pin and a corrupted one BOTH resolve to nothing, so "a corrupted pin is
detected" would hold for the wrong reason. That is the vacuity this file exists to
prevent, so it is not reintroduced here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from tools import render_m085_exhaustion_table as exhaustion

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", *arguments],  # noqa: S607
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _base_present() -> bool:
    """Is the pinned base commit actually in this clone?"""
    return _git("cat-file", "-e", f"{exhaustion.BASE}^{{commit}}").returncode == 0


def _requires_the_base_commit() -> None:
    if not _base_present():
        pytest.skip(
            f"the pinned base {exhaustion.BASE[:12]} is absent from this clone "
            "(shallow checkout); the pin's form and the item-1 failure path still ran"
        )


class TestThePinIsWellFormed:
    """Always runs: these ask about the pin, not about the repository."""

    def test_the_groups_assemble_to_a_forty_character_hex_sha(self) -> None:
        assert len(exhaustion.BASE) == 40
        assert all(character in "0123456789abcdef" for character in exhaustion.BASE)

    def test_the_groups_are_split_only_for_the_secret_scanner(self) -> None:
        # The split exists so a 40-hex literal does not trip the high-entropy
        # detector. It must still be a faithful split of the whole.
        assert "".join(exhaustion._BASE_GROUPS) == exhaustion.BASE
        assert len(exhaustion._BASE_GROUPS) == 5

    def test_the_pin_is_the_commit_this_milestone_was_required_to_branch_from(self) -> None:
        # The required base, written out once here as the independent expectation.
        # This is the check that would have caught the transcription error with no
        # git history at all, which is why it is the one that always runs.
        assert exhaustion.BASE == "a224076754fb38909ee04c2464e50e51df12d7ad"


class TestThePresenceOfTheBaseIsReportedNotAssumed:
    def test_presence_is_a_boolean_answer(self) -> None:
        # Not a check of the base — a check that the skips below, if they happen,
        # happen for the stated reason and not because git itself is broken.
        assert isinstance(_base_present(), bool)
        assert _git("rev-parse", "HEAD").returncode == 0


class TestThePinNamesARealCommit:
    def test_the_pinned_commit_exists_in_this_repository(self) -> None:
        _requires_the_base_commit()
        assert _base_present()

    def test_the_pinned_commit_is_the_merge_base_of_this_branch(self) -> None:
        _requires_the_base_commit()
        result = _git("merge-base", "HEAD", exhaustion.BASE)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == exhaustion.BASE

    def test_merge_base_against_the_pin_produces_a_nonempty_answer(self) -> None:
        # Anti-vacuity for the assertion above. `git merge-base` prints NOTHING on
        # an unreadable pin, so the comparison would be "'' == BASE" -> a clean,
        # wrong failure message blaming the branch. An empty answer means the pin
        # is unreadable, which is a different defect and must be named differently.
        _requires_the_base_commit()
        assert _git("merge-base", "HEAD", exhaustion.BASE).stdout.strip() != ""


class TestACorruptedPinIsDetected:
    @pytest.mark.parametrize("position", [0, 19, 25, 39])
    def test_flipping_one_character_stops_resolving(self, position: int) -> None:
        """The mutation the real defect was: one wrong hex digit, anywhere."""
        _requires_the_base_commit()
        original = exhaustion.BASE[position]
        replacement = "0" if original != "0" else "1"
        corrupted = exhaustion.BASE[:position] + replacement + exhaustion.BASE[position + 1 :]
        assert corrupted != exhaustion.BASE
        assert _git("cat-file", "-e", f"{corrupted}^{{commit}}").returncode != 0
        assert _git("merge-base", "HEAD", corrupted).stdout.strip() != exhaustion.BASE

    def test_the_item_one_check_fails_on_a_corrupted_pin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Always runs. It needs no history: an all-zero pin resolves nowhere in any
        # clone, so the gate must report failure either way.
        corrupted = "0" * 40
        monkeypatch.setattr(exhaustion, "BASE", corrupted)
        passed, evidence = exhaustion._base_is_the_required_one()
        assert passed is False
        assert "unresolved" in evidence or corrupted[:12] not in evidence

    def test_the_item_one_check_passes_on_the_real_pin(self) -> None:
        # The positive half: without this, the test above would pass against a
        # check that always fails. Needs the history, so it skips without it.
        _requires_the_base_commit()
        passed, evidence = exhaustion._base_is_the_required_one()
        assert passed is True
        assert exhaustion.BASE[:12] in evidence
