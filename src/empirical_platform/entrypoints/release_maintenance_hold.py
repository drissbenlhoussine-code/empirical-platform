"""RELEASE v1 hardening -- the Owner's explicit command to remove the maintenance hold.

    python -m empirical_platform.entrypoints.release_maintenance_hold \\
        --journal-path <deployment journal.json>
    python -m empirical_platform.entrypoints.release_maintenance_hold --owner-override

`tools/personal_paper_deploy.py` creates the hold before it stops the console and NEVER removes
it. Removing it is part of the Owner-authorized PAPER activation. This command refuses unless
either (a) `--journal-path` names a deployment journal in which STEP_12, STEP_13 and STEP_14
(recovery-mode start, its verification, and the stop-before-active) are all `completed`, or
(b) the Owner passes `--owner-override` and thereby accepts responsibility for having verified
recovery mode by other means. It never starts anything and never touches a database.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from empirical_platform.shared import console_lifecycle
from empirical_platform.shared.persistence.database_safety import manifest_path

__all__ = ["main", "verification_problem"]

_REQUIRED_STEPS = ("STEP_12_RECOVERY_START", "STEP_13_VERIFY_STARTUP", "STEP_14_STOP_BEFORE_ACTIVE")


def verification_problem(journal_path: Path) -> str | None:
    """None when the journal proves recovery-mode verification; otherwise the reason it does
    not."""
    try:
        value = json.loads(journal_path.read_text(encoding="utf-8"))
        records = value["records"]
        completed = {r["step"] for r in records if r["status"] == "completed"}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return f"cannot read {journal_path} as a deployment journal ({type(error).__name__})"
    missing = [step for step in _REQUIRED_STEPS if step not in completed]
    if missing:
        return f"the journal does not show these steps completed: {', '.join(missing)}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--safety-directory", type=Path, default=None)
    parser.add_argument("--journal-path", type=Path, default=None)
    parser.add_argument("--owner-override", action="store_true")
    arguments = parser.parse_args(argv)
    safety_directory = arguments.safety_directory or manifest_path().parent

    if arguments.journal_path is None and not arguments.owner_override:
        print(
            "REFUSED: give --journal-path (the deployment journal proving recovery-mode "
            "verification) or, as the Owner, --owner-override. The hold was not changed.",
            file=sys.stderr,
        )
        return 2
    if arguments.journal_path is not None:
        problem = verification_problem(arguments.journal_path)
        if problem is not None and not arguments.owner_override:
            print(f"REFUSED: {problem}. The hold was not changed.", file=sys.stderr)
            return 2
    try:
        removed = console_lifecycle.release_maintenance_hold(safety_directory)
    except console_lifecycle.MaintenanceHoldError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1
    print(
        "maintenance hold removed; the autostart wrapper and a FULL-mode console may now start."
        if removed
        else "no maintenance hold was present; nothing changed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
