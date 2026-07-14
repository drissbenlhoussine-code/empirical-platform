from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tools.secret_scan_targets import discover_secret_scan_targets


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
