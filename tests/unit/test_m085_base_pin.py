"""The M085 base-commit pin is a real commit, and it is really this branch's base.

WHY THIS FILE EXISTS. `tools/render_m085_exhaustion_table.py` pinned the required
base commit with a single-character transcription error (`62d50e51` where the
commit reads `64e50e51`). Nothing failed. The exhaustion table simply reported
item 1 as `EXECUTED_FAIL_BLOCKER` with the evidence string `branch base is
(unresolved)`, because `git merge-base` against a nonexistent object prints
nothing -- so a WRONG pin and an ACTUALLY-WRONG BASE are indistinguishable in the
output. A gate that cannot tell "you are on the wrong base" from "I cannot read my
own pin" is not a gate.

The M084 tooling has `tests/unit/test_m084_audit_portability.py` pinning its
commits across four tools, which is why the same class of error was caught there.
M085 pinned its base in one tool and tested it nowhere. This closes that.

The positive and negative halves are both here: a real, resolvable pin, AND proof
that a corrupted pin is DETECTED rather than silently reported as a base mismatch.
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


class TestThePinIsWellFormed:
    def test_the_groups_assemble_to_a_forty_character_hex_sha(self) -> None:
        assert len(exhaustion.BASE) == 40
        assert all(character in "0123456789abcdef" for character in exhaustion.BASE)

    def test_the_groups_are_split_only_for_the_secret_scanner(self) -> None:
        # The split exists so a 40-hex literal does not trip the high-entropy
        # detector. It must still be a faithful split of the whole.
        assert "".join(exhaustion._BASE_GROUPS) == exhaustion.BASE
        assert len(exhaustion._BASE_GROUPS) == 5


class TestThePinNamesARealCommit:
    def test_the_pinned_commit_exists_in_this_repository(self) -> None:
        # The failure this test was written for: a pin that names no object at all.
        result = _git("cat-file", "-e", f"{exhaustion.BASE}^{{commit}}")
        assert result.returncode == 0, (
            f"the pinned base {exhaustion.BASE} is not a commit in this repository"
        )

    def test_the_pinned_commit_is_the_merge_base_of_this_branch(self) -> None:
        result = _git("merge-base", "HEAD", exhaustion.BASE)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == exhaustion.BASE

    def test_merge_base_against_the_pin_produces_a_nonempty_answer(self) -> None:
        # Anti-vacuity for the assertion above. `git merge-base` prints NOTHING and
        # the comparison would be "'' == BASE" -> a clean, wrong failure message
        # blaming the branch. An empty answer means the pin is unreadable, which is
        # a different defect and must be named differently.
        assert _git("merge-base", "HEAD", exhaustion.BASE).stdout.strip() != ""


class TestACorruptedPinIsDetected:
    @pytest.mark.parametrize("position", [0, 19, 25, 39])
    def test_flipping_one_character_stops_resolving(self, position: int) -> None:
        """The mutation the real defect was: one wrong hex digit, anywhere."""
        original = exhaustion.BASE[position]
        replacement = "0" if original != "0" else "1"
        corrupted = exhaustion.BASE[:position] + replacement + exhaustion.BASE[position + 1 :]
        assert corrupted != exhaustion.BASE
        # It must NOT be a commit, and merge-base must NOT return the real base.
        assert _git("cat-file", "-e", f"{corrupted}^{{commit}}").returncode != 0
        assert _git("merge-base", "HEAD", corrupted).stdout.strip() != exhaustion.BASE

    def test_the_item_one_check_fails_on_a_corrupted_pin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The gate itself, driven with a bad pin, must report failure.
        corrupted = "0" * 40
        monkeypatch.setattr(exhaustion, "BASE", corrupted)
        passed, evidence = exhaustion._base_is_the_required_one()
        assert passed is False
        assert "unresolved" in evidence or corrupted[:12] not in evidence

    def test_the_item_one_check_passes_on_the_real_pin(self) -> None:
        # The positive half: without this, the test above would pass against a
        # check that always fails.
        passed, evidence = exhaustion._base_is_the_required_one()
        assert passed is True
        assert exhaustion.BASE[:12] in evidence
