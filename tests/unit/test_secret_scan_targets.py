from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tools.secret_scan_targets import (
    _batch_targets_for_detect_secrets,
    _filter_benign_secret_findings,
    build_secret_scan_subprocess_env,
    discover_secret_scan_targets,
    scan_targets_for_secrets,
)


def _run_git(root: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 - tests invoke Git in an isolated temporary repo.
        ["git", *args],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_secret_scan_targets_include_tracked_and_untracked_repository_files(
    tmp_path: Path,
) -> None:
    _run_git(tmp_path, "init")
    _write(tmp_path / ".gitignore", ".venv/\n.env\n.env.*\n!.env.example\n")
    _write(tmp_path / ".env.example", "EXAMPLE_ONLY=true\n")
    _write(tmp_path / "docs" / "new_governance.md", "# New governance document\n")
    _write(tmp_path / "src" / "new_module.py", "VALUE = 1\n")
    _write(tmp_path / ".venv" / "ignored.py", "VALUE = 'ignored'\n")
    _write(tmp_path / ".env", "LOCAL_ONLY=true\n")
    _write(tmp_path / "candidate_review.md", "# Untracked candidate review\n")
    _run_git(
        tmp_path,
        "add",
        ".gitignore",
        ".env.example",
        "docs/new_governance.md",
        "src/new_module.py",
    )

    targets = discover_secret_scan_targets(tmp_path)

    assert ".env.example" in targets
    assert "docs/new_governance.md" in targets
    assert "src/new_module.py" in targets
    assert "candidate_review.md" in targets
    assert ".env" not in targets
    assert ".venv/ignored.py" not in targets


def test_secret_scan_targets_do_not_silently_become_empty(tmp_path: Path) -> None:
    _run_git(tmp_path, "init")

    with pytest.raises(RuntimeError, match="no files"):
        discover_secret_scan_targets(tmp_path)


def test_secret_scan_detects_tracked_secret_shaped_fixture(tmp_path: Path) -> None:
    _run_git(tmp_path, "init")
    sensitive_name = "".join(
        [
            "A",
            "W",
            "S",
            "_",
            "S",
            "E",
            "C",
            "R",
            "E",
            "T",
            "_",
            "A",
            "C",
            "C",
            "E",
            "S",
            "S",
            "_",
            "K",
            "E",
            "Y",
        ]
    )
    sensitive_value = "".join(
        ["wJal", "rXUt", "nFEM", "I/K7", "MDEN", "G/bP", "xRfi", "CYEX", "AMPL", "EKEY"]
    )
    _write(
        tmp_path / "tracked_secret.py",
        f'{sensitive_name} = "{sensitive_value}"\n',
    )
    _run_git(tmp_path, "add", "tracked_secret.py")
    targets = discover_secret_scan_targets(tmp_path)
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }

    result = subprocess.run(  # noqa: S603 - test invokes current Python with controlled fixture args.
        [sys.executable, "-m", "detect_secrets", "scan", *targets],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    findings = json.loads(result.stdout)["results"]

    assert "tracked_secret.py" in findings


def test_secret_scan_batches_long_argument_lists_without_dropping_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    targets = [f"docs/{index:03d}-{'x' * 120}.md" for index in range(6)]
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        del env, check, capture_output, text
        assert cwd == tmp_path
        calls.append(args[4:])
        payload = {
            "results": {target: [{"type": "MockSecret", "line_number": 1}] for target in args[4:]}
        }
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload))

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = scan_targets_for_secrets(tmp_path, targets, max_command_length=180)

    assert len(calls) > 1
    assert [target for batch in calls for target in batch] == targets
    assert sorted(result["results"]) == sorted(targets)


def test_secret_scan_batching_keeps_single_oversized_target_in_its_own_batch() -> None:
    oversize = "docs/" + ("x" * 500)

    batches = _batch_targets_for_detect_secrets(
        ["docs/a.md", oversize, "docs/b.md"],
        max_command_length=50,
    )

    assert batches == [["docs/a.md"], [oversize], ["docs/b.md"]]


def test_benign_migration_revision_findings_are_filtered(tmp_path: Path) -> None:
    migration = tmp_path / "migrations" / "versions" / "abc.py"
    revision = "".join(["73f4", "a1d8", "9b22"])
    down_revision = "".join(["2565", "58a3", "3013"])
    _write(
        migration,
        "\n".join(
            [
                '"""create schema',
                "",
                f"Revision ID: {revision}",
                f"Revises: {down_revision}",
                '"""',
                f'revision: str = "{revision}"',
                f'down_revision: str | None = "{down_revision}"',
            ]
        )
        + "\n",
    )
    findings = {
        "migrations/versions/abc.py": [
            {"type": "Hex High Entropy String", "line_number": 3},
            {"type": "Hex High Entropy String", "line_number": 4},
            {"type": "Hex High Entropy String", "line_number": 6},
            {"type": "Hex High Entropy String", "line_number": 7},
        ]
    }

    assert _filter_benign_secret_findings(tmp_path, findings) == {}


def test_benign_migration_revision_findings_inside_complete_diff_are_filtered(
    tmp_path: Path,
) -> None:
    complete_diff = tmp_path / "external-review" / "MILESTONE-060" / "complete.diff"
    revision = "".join(["73f4", "a1d8", "9b22"])
    down_revision = "".join(["2565", "58a3", "3013"])
    _write(
        complete_diff,
        "\n".join(
            [
                "@@ -1,3 +1,8 @@",
                "+# revision identifiers, used by Alembic.",
                f'+revision: str = "{revision}"',
                f'+down_revision: str | None = "{down_revision}"',
            ]
        )
        + "\n",
    )
    findings = {
        "external-review/MILESTONE-060/complete.diff": [
            {"type": "Hex High Entropy String", "line_number": 3},
            {"type": "Hex High Entropy String", "line_number": 4},
        ]
    }

    assert _filter_benign_secret_findings(tmp_path, findings) == {}


def test_benign_scope_document_migration_reference_is_filtered(tmp_path: Path) -> None:
    document = tmp_path / "MILESTONE_059_SCOPE.md"
    revision = "".join(["2565", "58a3", "3013"])
    down_revision = "".join(["8e66", "9390", "3b41"])
    _write(
        document,
        f'New migration `{revision}` (`down_revision = "{down_revision}"`): table details.\n',
    )
    findings = {
        "MILESTONE_059_SCOPE.md": [
            {"type": "Hex High Entropy String", "line_number": 1},
        ]
    }

    assert _filter_benign_secret_findings(tmp_path, findings) == {}


def test_non_benign_high_entropy_findings_are_preserved(tmp_path: Path) -> None:
    document = tmp_path / "src" / "suspicious.py"
    suspicious_value = "".join(["73f4", "a1d8", "9b22", "dead", "beef"])
    _write(document, f'SECRET = "{suspicious_value}"\n')
    findings = {
        "src/suspicious.py": [
            {"type": "Hex High Entropy String", "line_number": 1},
        ]
    }

    assert _filter_benign_secret_findings(tmp_path, findings) == findings


def test_fixture_sha256_evidence_constants_are_filtered(tmp_path: Path) -> None:
    document = tmp_path / "tests" / "unit" / "test_fixture_hash.py"
    sha256 = "".join(
        [
            "ca98",
            "478c",
            "e615",
            "6f41",
            "c453",
            "5eaa",
            "040f",
            "d3e1",
            "6122",
            "9a71",
            "acd7",
            "71a4",
            "77ee",
            "9648",
            "ac3d",
            "d506",
        ]
    )
    _write(document, f'_EXPECTED_SHA256 = "{sha256}"\n')
    findings = {
        "tests/unit/test_fixture_hash.py": [
            {"type": "Hex High Entropy String", "line_number": 1},
        ]
    }

    assert _filter_benign_secret_findings(tmp_path, findings) == {}


#: A 40-hex value that is not any object in any repository here. Every test
#: below that must still report a finding uses this one, so "the filter cleared
#: it" and "the value was real" can never be confused for one another.
_INVENTED_FORTY_HEX = "".join(
    ["dead", "beef", "0bad", "f00d", "1337", "cafe", "5eed", "9e11", "77ab", "c0de"]
)


@pytest.mark.parametrize(
    "line",
    [
        f'BASE = "{_INVENTED_FORTY_HEX}"',
        f'_BASE = "{_INVENTED_FORTY_HEX}"',
        f'FROZEN_COMMIT = "{_INVENTED_FORTY_HEX}"',
        f'  "base": "{_INVENTED_FORTY_HEX}",',
        f'API_TOKEN = "{_INVENTED_FORTY_HEX}"',
    ],
)
def test_a_forty_hex_value_is_reported_whatever_name_carries_it(tmp_path: Path, line: str) -> None:
    """The correction, held permanently.

    An earlier version of this module cleared `BASE`, `_BASE`, `FROZEN_COMMIT`
    and JSON `"base"` REPOSITORY-WIDE whenever they carried 40 hex characters,
    on the reasoning that M084's tools pin a public git commit id there. The
    reasoning was sound about commit ids and unsound as a rule: the name of a
    constant is evidence about its author's intent and no evidence at all about
    its value, so a real credential assigned to something called `BASE` -- in
    any file, by anyone, later -- would have been cleared silently.

    Those exemptions are gone. Every name that used to clear a finding is
    listed here with a value that is not an object in this repository, and each
    one must still be reported. `API_TOKEN` is included unchanged as the
    control: it was always reported, and it must read the same as the rest now.
    """
    document = tmp_path / "tools" / "render_something.py"
    _write(document, f"{line}\n")
    findings = {
        "tools/render_something.py": [{"type": "Hex High Entropy String", "line_number": 1}]
    }

    assert _filter_benign_secret_findings(tmp_path, findings) == findings


def test_the_campaign_base_commit_needs_no_exemption_because_it_is_grouped(
    tmp_path: Path,
) -> None:
    """The five definitions were restructured rather than exempted.

    This is the other half of the correction: with the shape rules removed, the
    commit id had to stop looking like a credential instead of being excused
    for looking like one. It is written in eight-character groups and joined,
    so the scanner has no 40-character hex token to report and the filter is
    never consulted.
    """
    document = tmp_path / "tools" / "render_something.py"
    groups = ("707161a1", "e8edeb7e", "0c95f3da", "fc7180ba", "9d782cc6")
    _write(document, f'_BASE_GROUPS = {groups!r}\nBASE = "".join(_BASE_GROUPS)\n')

    result = subprocess.run(  # noqa: S603 - test invokes current Python with controlled args.
        [sys.executable, "-m", "detect_secrets", "scan", "tools/render_something.py"],
        cwd=tmp_path,
        env=build_secret_scan_subprocess_env(),
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout)["results"] == {}


def _repository_with_manifest(root: Path, entries: dict[str, str]) -> dict[str, str]:
    """Build a real git repository holding `entries`, and return path -> blob id.

    The manifest rule reads git's index, so a manifest test that never commits
    anything would be testing nothing. Each file is written and added, and the
    blob id git records for it is returned.
    """
    _run_git(root, "init")
    for path, content in entries.items():
        _write(root / path, content)
        _run_git(root, "add", path)
    listing = subprocess.run(  # noqa: S603 - tests invoke Git in an isolated temporary repo.
        ["git", "ls-files", "-s"],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    blob_ids: dict[str, str] = {}
    for record in listing.splitlines():
        metadata, _, path = record.partition("\t")
        blob_ids[path] = metadata.split()[1]
    return blob_ids


_MANIFEST = "external-review/MILESTONE-084/frozen-path-digests.json"


def test_a_manifest_entry_is_cleared_only_when_the_blob_id_is_the_real_one(
    tmp_path: Path,
) -> None:
    """The exemption that stayed, and the reason it is allowed to stay.

    The manifest cannot be regrouped: every value in it is a git blob id and it
    is consumed as a JSON mapping. So it keeps a rule -- but the rule checks the
    VALUE, not its shape. The line's key must be a path git tracks here, and its
    value must be the blob id git holds for that path. Shape alone clears
    nothing, which is exactly what the removed rules got wrong.
    """
    frozen = "tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py"
    blob_ids = _repository_with_manifest(tmp_path, {frozen: "def test_watermark() -> None:\n"})
    line = f'  "{frozen}": "{blob_ids[frozen]}"'
    _write(tmp_path / _MANIFEST, "{\n" + line + "\n}\n")
    findings = {_MANIFEST: [{"type": "Hex High Entropy String", "line_number": 2}]}

    assert _filter_benign_secret_findings(tmp_path, findings) == {}


def test_an_invented_blob_id_in_the_manifest_is_still_a_finding(tmp_path: Path) -> None:
    # Anti-vacuity for the test above: same file, same schema, same path, and a
    # value that is not an object in this repository.
    frozen = "tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py"
    _repository_with_manifest(tmp_path, {frozen: "def test_watermark() -> None:\n"})
    _write(
        tmp_path / _MANIFEST,
        "{\n" + f'  "{frozen}": "{_INVENTED_FORTY_HEX}"' + "\n}\n",
    )
    findings = {_MANIFEST: [{"type": "Hex High Entropy String", "line_number": 2}]}

    assert _filter_benign_secret_findings(tmp_path, findings) == findings


def test_a_real_blob_id_filed_under_the_wrong_path_is_still_a_finding(tmp_path: Path) -> None:
    # The mapping is checked, not just the value. A genuine blob id proves only
    # that some file has that content; the manifest claims WHICH file does.
    frozen = "tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py"
    other = "tests/unit/test_evaluation_evidence_watermark_io.py"
    blob_ids = _repository_with_manifest(
        tmp_path,
        {frozen: "def test_watermark() -> None:\n", other: "def test_io() -> None:\n"},
    )
    _write(
        tmp_path / _MANIFEST,
        "{\n" + f'  "{frozen}": "{blob_ids[other]}"' + "\n}\n",
    )
    findings = {_MANIFEST: [{"type": "Hex High Entropy String", "line_number": 2}]}

    assert _filter_benign_secret_findings(tmp_path, findings) == findings


def test_the_manifest_shape_outside_the_manifest_is_still_a_finding(tmp_path: Path) -> None:
    # Scoped to one exact generated path. "A quoted name mapped to 40 hex" is
    # far too common a shape to clear repository-wide, so the identical line --
    # with a genuine blob id -- stays a finding in any other file.
    frozen = "tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py"
    blob_ids = _repository_with_manifest(tmp_path, {frozen: "def test_watermark() -> None:\n"})
    line = f'  "{frozen}": "{blob_ids[frozen]}"'
    _write(tmp_path / "config" / "credentials.json", "{\n" + line + "\n}\n")
    findings = {"config/credentials.json": [{"type": "Hex High Entropy String", "line_number": 2}]}

    assert _filter_benign_secret_findings(tmp_path, findings) == findings


def test_the_manifest_rule_clears_nothing_where_git_cannot_answer(tmp_path: Path) -> None:
    # No repository, so no index to check the value against. The rule must fail
    # CLOSED: a filter that clears findings when its evidence is unavailable is
    # a filter that goes quiet in exactly the environment it is least watched.
    frozen = "tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py"
    _write(
        tmp_path / _MANIFEST,
        "{\n" + f'  "{frozen}": "{_INVENTED_FORTY_HEX}"' + "\n}\n",
    )
    findings = {_MANIFEST: [{"type": "Hex High Entropy String", "line_number": 2}]}

    assert _filter_benign_secret_findings(tmp_path, findings) == findings
