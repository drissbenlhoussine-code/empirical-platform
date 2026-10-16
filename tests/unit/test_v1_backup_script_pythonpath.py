"""Guards against regressing the worktree PYTHONPATH fix for the hourly Personal Paper
backup. A worktree's shared `.venv` editable install resolves to the main checkout's
`src`, not the worktree's own; Scheduled Tasks start a fresh process with no inherited
PYTHONPATH, so `tools/personal_paper_backup.py` fails closed with ModuleNotFoundError
unless the backup script sets it explicitly before invoking python.
"""

from __future__ import annotations

import re
from pathlib import Path

_SCRIPT = (Path(__file__).resolve().parents[2] / "scripts" / "backup-personal-paper.ps1").read_text(
    encoding="utf-8"
)


def test_pythonpath_is_set_from_repository_parameter() -> None:
    assert re.search(r"\$env:PYTHONPATH\s*=\s*Join-Path\s+\$Repository\s+['\"]src['\"]", _SCRIPT), (
        "backup-personal-paper.ps1 must set $env:PYTHONPATH from $Repository before running python"
    )


def test_pythonpath_is_set_before_the_python_invocation() -> None:
    pythonpath_line = _SCRIPT.index("$env:PYTHONPATH")
    invocation_line = _SCRIPT.index("& $python $program")
    assert 0 < pythonpath_line < invocation_line


def test_pythonpath_assignment_is_process_scoped_only() -> None:
    """`$env:NAME = value` is always process-scoped; guard against a future rewrite to
    `[Environment]::SetEnvironmentVariable(..., 'User')` or `'Machine')`, which would leak
    this worktree's src path into other worktrees' or the main checkout's own runs."""
    assert "[Environment]::SetEnvironmentVariable('PYTHONPATH'" not in _SCRIPT
    assert '[Environment]::SetEnvironmentVariable("PYTHONPATH"' not in _SCRIPT
