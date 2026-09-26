"""V1 narrow correction: rows 21 and 29 recognise EXACTLY the Owner-ratified content, nothing wider.

The exhaustion table's renderer used to flag `PROJECT_CHECKPOINT.md` whenever it appeared in the
diff and any path matching `m084|MILESTONE-084` outside six audit-tooling files. Both rules then
tripped on content the Owner had ratified (§119, commit `5ae236c`): the checkpoint record itself
and the M085-owned M084 blob-id manifest the frozen-path guard reads. The correction recognises
each by the git blob id of its ratified content and by nothing else. These tests prove the rules
are as narrow as claimed, on fabricated inputs with no git involved, and that the pins are
well-formed. The renderer's `--check` remains the gate that runs them against the real tree.
"""

from __future__ import annotations

import pytest
from tools import render_m085_exhaustion_table as exhaustion

_OTHER_BLOB = "0" * 40


class TestThePinsAreWellFormed:
    @pytest.mark.parametrize(
        ("groups", "blob"),
        [
            (exhaustion._RATIFIED_CHECKPOINT_BLOB_GROUPS, exhaustion.RATIFIED_CHECKPOINT_BLOB),
            (
                exhaustion._RATIFIED_M084_MANIFEST_BLOB_GROUPS,
                exhaustion.RATIFIED_M084_MANIFEST_BLOB,
            ),
        ],
        ids=["checkpoint", "manifest"],
    )
    def test_the_groups_assemble_to_a_forty_character_hex_blob_id(
        self, groups: tuple[str, ...], blob: str
    ) -> None:
        assert "".join(groups) == blob
        assert len(blob) == 40
        assert all(character in "0123456789abcdef" for character in blob)
        assert all(len(group) < 40 for group in groups), "no token may be a bare 40-hex value"

    def test_the_two_pins_are_different_objects(self) -> None:
        assert exhaustion.RATIFIED_CHECKPOINT_BLOB != exhaustion.RATIFIED_M084_MANIFEST_BLOB


class TestRow29TheCheckpoint:
    def test_absent_from_the_diff_is_untouched(self) -> None:
        ok, evidence = exhaustion.checkpoint_untouched_or_ratified(["src/x.py"], _OTHER_BLOB)
        assert ok and "not in the diff" in evidence

    def test_present_with_exactly_the_ratified_content_passes(self) -> None:
        ok, evidence = exhaustion.checkpoint_untouched_or_ratified(
            ["PROJECT_CHECKPOINT.md"], exhaustion.RATIFIED_CHECKPOINT_BLOB
        )
        assert ok and "ratified" in evidence

    @pytest.mark.parametrize("blob", [_OTHER_BLOB, "", exhaustion.RATIFIED_M084_MANIFEST_BLOB])
    def test_present_with_any_other_content_is_reported(self, blob: str) -> None:
        ok, evidence = exhaustion.checkpoint_untouched_or_ratified(["PROJECT_CHECKPOINT.md"], blob)
        assert not ok
        assert "WAS MODIFIED beyond the ratified" in evidence

    def test_a_single_flipped_character_in_the_blob_is_reported(self) -> None:
        ratified = exhaustion.RATIFIED_CHECKPOINT_BLOB
        flipped = ("0" if ratified[0] != "0" else "1") + ratified[1:]
        assert not exhaustion.checkpoint_untouched_or_ratified(["PROJECT_CHECKPOINT.md"], flipped)[
            0
        ]


class TestRow21TheM084Paths:
    def test_no_m084_path_changed_passes(self) -> None:
        ok, evidence = exhaustion.m084_paths_authorized(["src/x.py", "tests/y.py"], _OTHER_BLOB)
        assert ok and "none" in evidence

    def test_the_six_ratified_audit_files_are_authorized_as_before(self) -> None:
        ok, _ = exhaustion.m084_paths_authorized(
            sorted(exhaustion._AUTHORIZED_M084_PATHS), _OTHER_BLOB
        )
        assert ok

    def test_the_manifest_with_its_ratified_content_is_authorized(self) -> None:
        ok, _ = exhaustion.m084_paths_authorized(
            [exhaustion.M084_MANIFEST_PATH], exhaustion.RATIFIED_M084_MANIFEST_BLOB
        )
        assert ok

    @pytest.mark.parametrize("blob", [_OTHER_BLOB, "", exhaustion.RATIFIED_CHECKPOINT_BLOB])
    def test_the_manifest_with_any_other_content_is_reported(self, blob: str) -> None:
        ok, evidence = exhaustion.m084_paths_authorized([exhaustion.M084_MANIFEST_PATH], blob)
        assert not ok and exhaustion.M084_MANIFEST_PATH in evidence

    @pytest.mark.parametrize(
        "path",
        [
            "src/empirical_platform/decision_candidate/m084_thing.py",
            "external-review/MILESTONE-084/anything-else.md",
            "tests/unit/test_m084_new.py",
            "external-review/MILESTONE-085/m084-frozen-path-digests.json.bak",
        ],
    )
    def test_any_other_m084_path_is_still_reported(self, path: str) -> None:
        ok, evidence = exhaustion.m084_paths_authorized(
            [path, exhaustion.M084_MANIFEST_PATH], exhaustion.RATIFIED_M084_MANIFEST_BLOB
        )
        # Exactly the one unauthorized path is reported; the ratified manifest is not.
        assert not ok and evidence.endswith(f"['{path}']")

    def test_the_pattern_was_not_widened(self) -> None:
        # A ratified manifest never excuses a second M084 path in the same diff.
        ok, _ = exhaustion.m084_paths_authorized(
            [exhaustion.M084_MANIFEST_PATH, "tools/m084_helper.py"],
            exhaustion.RATIFIED_M084_MANIFEST_BLOB,
        )
        assert not ok
