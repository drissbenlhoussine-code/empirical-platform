"""MILESTONE-027 negative/positive type-check verification for CommandHandler.

Invokes `mypy` as a subprocess against isolated fixture files under
`tests/typing_fixtures/command_handler/`, proving malformed handler shapes
are mechanically rejected. These fixtures are never added to
`[tool.mypy] packages`, so the canonical `mypy` gate never walks them; only
this test ever type-checks them, via an explicit subprocess invocation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_FIXTURES = _REPO_ROOT / "tests" / "typing_fixtures" / "command_handler"


def _run_mypy(fixture: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - test invokes current Python with controlled fixture args.
        [sys.executable, "-m", "mypy", "--config-file", str(_PYPROJECT), str(_FIXTURES / fixture)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_ok_handler_type_checks_cleanly() -> None:
    result = _run_mypy("ok_handler.py")
    assert result.returncode == 0
    assert "Success: no issues found" in result.stdout


@pytest.mark.parametrize(
    "fixture",
    ["wrong_method.py", "wrong_command_type.py", "wrong_result_type.py", "missing_handle.py"],
)
def test_malformed_handler_is_rejected(fixture: str) -> None:
    result = _run_mypy(fixture)
    assert result.returncode != 0
    assert "error: Incompatible types in assignment" in result.stdout
    assert "[assignment]" in result.stdout


def test_fixtures_are_not_part_of_canonical_mypy_package_scope() -> None:
    import tomllib

    config = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    packages = config["tool"]["mypy"]["packages"]
    assert packages == ["empirical_platform"]
