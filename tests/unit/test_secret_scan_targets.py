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
