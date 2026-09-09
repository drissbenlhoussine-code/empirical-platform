"""Run M083's own suite, unmodified, at M083's own revision.

    python tools/m084_frozen_m083_acceptance.py
    python tools/m084_frozen_m083_acceptance.py --keep   # leave the worktree

M084's `evaluation_context` holds a foreign key to M083's
`evaluation_evidence_watermark`. PostgreSQL refuses to TRUNCATE a table a
foreign key references -- regardless of whether the referencing table holds any
rows -- so M083's frozen reset statement is INEXECUTABLE at the M084 head, and
M083's PostgreSQL suites cannot run there unmodified. Editing them would make
"M083 still passes" mean "M083 passes a test M084 rewrote", so they are left
byte-for-byte as frozen, enforced by `tools/check_frozen_paths.py`.

This harness gets the result the honest way instead. It checks the frozen
commit out into its own git worktree, where the migration head IS M083 and
nothing references the watermark, creates a database of its own, and runs
M083's tests there against their own schema. The code under test is M083's, at
M083's revision, exactly as the Owner froze it -- this file never touches it.

The result is one of two separate facts, and this tool produces only the first:

    FROZEN M083 ACCEPTANCE   M083's suite, unmodified, at M083's revision.
                             Produced here.
    M084 COMPATIBILITY       M083's table, constraints, triggers, rows and
                             reset semantics at the M084 head, and their
                             survival across M084's downgrade. Produced by
                             tests/integration/test_m084_m083_compatibility.py.

Neither substitutes for the other. A failure in one is never reported as a pass
in the other.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The commit at which M083 was frozen: the migration head there is M083's.
#: Grouped so that no token here is a 40-character hex string; see
#: `tools/check_frozen_paths.py` for why the alternative was rejected.
_FROZEN_COMMIT_GROUPS = ("707161a1", "e8edeb7e", "0c95f3da", "fc7180ba", "9d782cc6")
FROZEN_COMMIT = "".join(_FROZEN_COMMIT_GROUPS)

#: M083's PostgreSQL suites -- the ones the M084 head cannot execute.
SUITES = (
    "tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py",
    "tests/integration/test_m083_evaluation_evidence_watermark_extended_attacks.py",
    "tests/integration/test_m083_evaluation_evidence_watermark_second_pass.py",
)

DATABASE = "empirical_m083_frozen"
INTERPRETER = str(REPO_ROOT / ".venv313/bin/python")


def _run(
    arguments: list[str], *, cwd: Path, env: dict[str, str] | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argument vectors, no shell
        arguments, cwd=cwd, capture_output=True, text=True, check=check, env=env
    )


def _reset_database() -> int:
    """Drop and recreate the harness database; return its fresh OID.

    The OID is the proof that the run started from a genuinely new database
    rather than a leftover one: a reused database would report the OID the
    previous run recorded.
    """
    _run(
        [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-q",
            "-c",
            f"DROP DATABASE IF EXISTS {DATABASE}",
            "-c",
            f"CREATE DATABASE {DATABASE} OWNER empirical",
        ],
        cwd=REPO_ROOT,
    )
    # Asked from inside the new database, so the statement carries no
    # interpolated identifier at all: `current_database()` names it.
    oid = _run(
        [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-d",
            DATABASE,
            "-tAc",
            "SELECT oid FROM pg_database WHERE datname = current_database()",
        ],
        cwd=REPO_ROOT,
    ).stdout.strip()
    return int(oid)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="leave the worktree in place")
    parser.add_argument("--worktree", type=Path, help="where to check the frozen commit out")
    parser.add_argument("--json-out", type=Path, help="write the result as JSON")
    args = parser.parse_args(argv)

    if "EMPIRICAL_PLATFORM_POSTGRES_PASSWORD" not in os.environ:
        print(
            "EMPIRICAL_PLATFORM_POSTGRES_PASSWORD is unset: this harness runs "
            "M083's real PostgreSQL suites and cannot be satisfied by skipping them",
            file=sys.stderr,
        )
        return 2

    worktree = args.worktree or (REPO_ROOT.parent / ".m083-frozen-worktree")
    _run(["git", "worktree", "remove", "--force", str(worktree)], cwd=REPO_ROOT, check=False)
    _run(["git", "worktree", "add", "--detach", str(worktree), FROZEN_COMMIT], cwd=REPO_ROOT)

    try:
        # The worktree must actually be the frozen commit, and M083's files
        # there must be the frozen bytes. Checked rather than assumed: a
        # harness that silently ran the wrong tree would report a pass that
        # means nothing.
        head = _run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()
        if head != FROZEN_COMMIT:
            print(f"worktree is at {head}, expected {FROZEN_COMMIT}", file=sys.stderr)
            return 1
        dirty = _run(["git", "status", "--porcelain"], cwd=worktree).stdout.strip()
        if dirty:
            print(f"the frozen worktree is not clean:\n{dirty}", file=sys.stderr)
            return 1

        oid = _reset_database()

        environment = dict(os.environ)
        environment["EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS"] = "1"
        environment["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = DATABASE
        environment["PYTHONDONTWRITEBYTECODE"] = "1"

        result = _run(
            [INTERPRETER, "-m", "pytest", *SUITES, "-q", "--no-cov", "-p", "no:randomly"],
            cwd=worktree,
            env=environment,
            check=False,
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        summary = lines[-1] if lines else "(no output)"
        passed = result.returncode == 0

        print(f"frozen commit ....... {FROZEN_COMMIT[:12]}")
        print(f"database ............ {DATABASE} (oid {oid})")
        print(f"suites .............. {len(SUITES)}")
        print(f"result .............. {summary}")
        print(f"FROZEN M083 ACCEPTANCE: {'PASS' if passed else 'FAIL'}")
        if not passed:
            print(result.stdout[-4000:], file=sys.stderr)

        if args.json_out:
            args.json_out.write_text(
                json.dumps(
                    {
                        "frozen_commit": FROZEN_COMMIT,
                        "database": DATABASE,
                        "database_oid": oid,
                        "suites": list(SUITES),
                        "summary": summary,
                        "passed": passed,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return 0 if passed else 1
    finally:
        if not args.keep:
            _run(
                ["git", "worktree", "remove", "--force", str(worktree)], cwd=REPO_ROOT, check=False
            )


if __name__ == "__main__":
    raise SystemExit(main())
