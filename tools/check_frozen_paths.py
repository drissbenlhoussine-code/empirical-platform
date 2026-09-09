"""Reject any modification to a frozen milestone's files between base and HEAD.

    python tools/check_frozen_paths.py            # fail on any frozen-path change
    python tools/check_frozen_paths.py --list     # print the governed path set

A frozen milestone's acceptance evidence is only worth something if the code
that produced it is the code that is still there. Once M083 was frozen, its
tests, production modules, migration, authority package and review package
stopped being editable by later work -- including by work that has a good
reason. A later milestone that finds a frozen test failing has three honest
moves: fix its own code, build its own harness, or record a measured
limitation. Editing the frozen test is not among them, because it converts
"M083 still passes" into "M083 passes a test M084 rewrote".

This check exists because that boundary was crossed during M084 and nothing
mechanical objected. It is deliberately a whole-path rule rather than a
semantic one: a reviewer cannot be asked to judge, per diff, whether an edit
"really" changed a frozen milestone's meaning, and the author is the last
person who should be making that call about their own change.

Ownership is derived from the repository, not hand-listed: a path is M083's if
its name carries the milestone number or the primitive that milestone
introduced. Deriving it means a frozen file added later cannot escape the guard
by being absent from a list somebody forgot to update.

`EXEMPT` is empty, and adding to it requires pre-existing repository policy
establishing that path as shared, non-frozen infrastructure -- an author's
judgement that an edit is harmless is not such evidence.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The commit this branch is measured against.
BASE = "707161a1e8edeb7e0c95f3dafc7180ba9d782cc6"

#: Frozen milestones, and the patterns that identify the files each one owns.
#: A path is owned if any pattern matches, so a milestone's ownership survives
#: a file being moved between the governed roots.
FROZEN: dict[str, tuple[str, ...]] = {
    # Patterns for files that name no milestone at all: M083's production and
    # test modules are named after the primitive it introduced, not after its
    # number, and would otherwise fall outside the guard entirely.
    "M083": (
        r"evaluation_evidence_watermark",
        r"^migrations/versions/9e4e647347ad_",
    ),
}

#: A milestone token anywhere in a path: `m083`, `MILESTONE-083`, `MILESTONE_083`.
#: The token boundary matters -- `tools/render_m083_authority.py` carries the
#: number mid-name, and a path-anchored pattern missed it. That gap was caught
#: by the ownership test in tests/architecture/test_frozen_paths.py, which is
#: there precisely because ownership derived from names can skip a category
#: silently.
_MILESTONE_TOKEN = re.compile(r"(?<![a-z0-9])(?:milestone[_-]|m)(\d{3})(?![a-z0-9])", re.IGNORECASE)


def owner_of(path: str) -> str | None:
    """The milestone a path belongs to, or None.

    A path that names several milestones belongs to the HIGHEST one. A later
    milestone routinely writes files *about* an earlier one --
    `tests/integration/test_m084_m083_compatibility.py` and
    `tools/m084_frozen_m083_acceptance.py` are exactly that, and both exist
    because M083 is frozen. Reading them as M083's would freeze M084's own
    replacement coverage the moment it was written, which is backwards: the
    later milestone owns what it authors, however loudly the file names the
    milestone it is protecting.
    """
    numbers = _MILESTONE_TOKEN.findall(path)
    if numbers:
        return f"M{max(numbers)}"
    for milestone, patterns in FROZEN.items():
        if re.search("|".join(patterns), path, re.IGNORECASE):
            return milestone
    return None

#: Paths a frozen pattern matches but that pre-M084 repository policy already
#: established as shared, non-frozen infrastructure. Empty, and it stays empty
#: unless such policy is produced: a milestone's own convenience is not policy.
EXEMPT: frozenset[str] = frozenset()


def owned_paths(tracked: list[str]) -> dict[str, list[str]]:
    """Every tracked path each frozen milestone owns."""
    return {
        milestone: sorted(
            path for path in tracked if owner_of(path) == milestone and path not in EXEMPT
        )
        for milestone in FROZEN
    }


def _git(*arguments: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", *arguments],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def violations() -> dict[str, list[str]]:
    """Frozen paths this branch changed, per milestone.

    Measured against the base commit rather than the working tree, so a change
    that was committed and then reverted in a later commit is correctly not a
    violation -- the frozen file is what it was.
    """
    changed = {line for line in _git("diff", "--name-only", f"{BASE}..HEAD").splitlines() if line}
    tracked = [line for line in _git("ls-files").splitlines() if line]
    return {
        milestone: [path for path in paths if path in changed]
        for milestone, paths in owned_paths(tracked).items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the governed path set")
    args = parser.parse_args(argv)

    tracked = [line for line in _git("ls-files").splitlines() if line]
    owners = owned_paths(tracked)

    if args.list:
        for milestone, paths in owners.items():
            print(f"{milestone}: {len(paths)} governed paths")
            for path in paths:
                print(f"  {path}")
        return 0

    # A pattern set that matches nothing would pass this check silently while
    # governing nothing, which is worse than no check at all.
    empty = [milestone for milestone, paths in owners.items() if not paths]
    if empty:
        print(f"frozen path patterns match no files for: {', '.join(empty)}", file=sys.stderr)
        return 1

    breaches = {m: p for m, p in violations().items() if p}
    if breaches:
        print(
            f"frozen milestone files were modified between {BASE[:12]} and HEAD:", file=sys.stderr
        )
        for milestone, paths in breaches.items():
            for path in paths:
                print(f"  {milestone}  {path}", file=sys.stderr)
        print(
            "\nA frozen milestone's files are not editable by later work. Fix the "
            "later milestone's own code, build a harness it owns, or record a "
            "measured limitation -- and restore these paths byte-for-byte.",
            file=sys.stderr,
        )
        return 1

    total = sum(len(paths) for paths in owners.values())
    print(f"frozen paths unmodified since {BASE[:12]} ({total} governed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
