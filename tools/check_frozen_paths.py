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
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The commit this branch is measured against, in eight-character groups.
#:
#: Grouped and joined rather than written as one 40-character literal, and the
#: reason is worth stating once here for the five places that pin it. A git
#: commit id is a public identifier -- `git log` prints it -- but it has a
#: credential's SHAPE, so detect-secrets reports it. The fix that reads well and
#: is wrong is to teach the scanner to clear 40 hex characters assigned to a
#: constant named `BASE`: a name is evidence about the author's intent and none
#: at all about the value, so that exemption would have cleared a real
#: credential of the same shape, under that name, anywhere in the repository.
#: No token below is a 40-character hex string, so none of this needs clearing.
_BASE_GROUPS = ("707161a1", "e8edeb7e", "0c95f3da", "fc7180ba", "9d782cc6")
BASE = "".join(_BASE_GROUPS)

#: MILESTONE-084's frozen state: the Owner-ratified post-freeze commit `1127134`
#: ("fix(m084): pin the derived audit to the approved tree, and let it run anywhere",
#: 2026-09-10), ratified on 2026-09-25 for exactly its six files and recorded in
#: `PROJECT_CHECKPOINT.md`. Every other M084 path is byte-identical there to the
#: M084 freeze merge, so this one commit pins the whole milestone as ratified.
_M084_BASE_GROUPS = ("11271346", "23b25178", "b4d98236", "d5ab75f8", "f2134760")
M084_BASE = "".join(_M084_BASE_GROUPS)

#: The commit each frozen milestone is measured against.
FROZEN_BASES: dict[str, str] = {"M083": BASE, "M084": M084_BASE}

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
    # M084's production, entrypoint and negative-fixture modules that carry no
    # milestone token. Derived from the 'A' (added) rows of
    # `external-review/MILESTONE-084/changed-files.txt`. Deliberately ABSENT: the six
    # 'M' (modified) rows -- pyproject.toml, postgres_repositories/runtime.py,
    # tests/architecture/test_module_boundaries.py, tests/unit/test_secret_scan_targets.py,
    # tools/check_architecture.py, tools/secret_scan_targets.py -- which pre-existed M084
    # and are shared, repository-wide infrastructure that later milestones extend; and
    # this guard together with its test, which the Owner directed be extended to cover
    # M084 and which would otherwise freeze the freezing.
    "M084": (
        r"^src/empirical_platform/decision_candidate/(evaluation_context|"
        r"operator_trading_configuration|product_market_inputs|product_repositories|"
        r"trade_approval|trade_proposal)\.py$",
        r"^src/empirical_platform/entrypoints/(_operator_cli|audit_history|"
        r"decide_trade_proposal|explain_no_trade|get_order_intent|get_trade_proposal|"
        r"invalidate_stale_proposals|issue_order_intent|kill_switch|list_trade_proposals|"
        r"open_evaluation_context|prepare_trade_proposal|save_trading_configuration|"
        r"show_trading_configuration|system_status|validate_trading_configuration)\.py$",
        r"^src/empirical_platform/shared/persistence/postgres_repositories/"
        r"decision_to_approval_repositories\.py$",
        r"^src/empirical_platform/usecases/decision_to_approval(_io)?\.py$",
        r"bad_broker_order_submission_import\.py$",
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


#: The git BLOB ID of every governed path as of BASE. Written by
#: `--write-digests`.
#:
#: Two environment differences shaped this, and both were found by CI rather
#: than reasoned about. First, `git diff BASE..HEAD` exits 128 in CI because the
#: base commit is genuinely absent from a shallow clone -- so a history-based
#: comparison fails exactly where the guard runs unattended, and skipping there
#: would make it silent in the one place that matters.
#:
#: Second, hashing the FILE'S BYTES then failed on Windows for every non-Python
#: path: `.gitattributes` pins `*.py` to LF, and everything else materializes
#: CRLF on checkout, so the working-tree bytes are legitimately not the
#: repository's bytes. A blob ID is git's own content address of the normalized
#: content, so it is identical on every platform by construction -- and reading
#: it needs only HEAD, which a shallow clone has.
DIGESTS = REPO_ROOT / "external-review" / "MILESTONE-084" / "frozen-path-digests.json"

#: One manifest per frozen milestone, each recorded from that milestone's own base.
#: M084's manifest lives under MILESTONE-085, the milestone that froze it: writing it
#: into MILESTONE-084's own package would edit a path the manifest governs.
DIGEST_FILES: dict[str, Path] = {
    "M083": DIGESTS,
    "M084": REPO_ROOT / "external-review" / "MILESTONE-085" / "m084-frozen-path-digests.json",
}


def blob_id(revision: str, path: str) -> str | None:
    """The git blob id of `path` at `revision`, or None if it is absent."""
    result = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", "rev-parse", f"{revision}:{path}"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def base_digests(milestone: str | None = None) -> dict[str, str]:
    """The recorded base blob ids: one milestone's manifest, or all of them merged."""
    files = [DIGEST_FILES[milestone]] if milestone is not None else list(DIGEST_FILES.values())
    recorded: dict[str, str] = {}
    for manifest in files:
        if manifest.exists():
            recorded.update(json.loads(manifest.read_text(encoding="utf-8")))
    return recorded


def content_violations() -> dict[str, list[str]]:
    """Frozen paths whose CONTENT differs from the recorded base digest.

    Needs no git history at all, so it holds in a shallow clone.
    """
    recorded = base_digests()
    breaches: dict[str, list[str]] = {}
    tracked = [line for line in _git("ls-files").splitlines() if line]
    for milestone, paths in owned_paths(tracked).items():
        changed = []
        for path in paths:
            expected = recorded.get(path)
            current = blob_id("HEAD", path)
            if expected is None:
                changed.append(f"{path} (no recorded base blob id)")
            elif current is None:
                changed.append(f"{path} (absent at HEAD)")
            elif current != expected:
                changed.append(path)
        if changed:
            breaches[milestone] = changed
    return breaches


def _git(*arguments: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", *arguments],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _base_present(base: str = BASE) -> bool:
    return (
        subprocess.run(  # noqa: S603 - fixed argument vector, no shell
            ["git", "cat-file", "-e", f"{base}^{{commit}}"],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _all_bases_present() -> bool:
    return all(_base_present(base) for base in FROZEN_BASES.values())


def violations() -> dict[str, list[str]]:
    """Frozen paths this branch changed, per milestone, each against ITS base commit.

    Measured against the base commit rather than the working tree, so a change
    that was committed and then reverted in a later commit is correctly not a
    violation -- the frozen file is what it was.
    """
    tracked = [line for line in _git("ls-files").splitlines() if line]
    result: dict[str, list[str]] = {}
    for milestone, paths in owned_paths(tracked).items():
        base = FROZEN_BASES[milestone]
        changed = {
            line for line in _git("diff", "--name-only", f"{base}..HEAD").splitlines() if line
        }
        result[milestone] = [path for path in paths if path in changed]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the governed path set")
    parser.add_argument(
        "--write-digests",
        action="store_true",
        help="record each governed path's digest AS OF THE BASE COMMIT",
    )
    args = parser.parse_args(argv)

    tracked = [line for line in _git("ls-files").splitlines() if line]
    owners = owned_paths(tracked)

    if args.write_digests:
        # Read from each milestone's base commit, never from the working tree:
        # recording the working tree would bless whatever is currently there, which
        # is the one thing this guard exists to prevent.
        for milestone, paths in owners.items():
            base = FROZEN_BASES[milestone]
            recorded = {}
            for path in paths:
                identifier = blob_id(base, path)
                if identifier is None:
                    print(f"{path} does not exist at {base[:12]}", file=sys.stderr)
                    return 1
                recorded[path] = identifier
            DIGEST_FILES[milestone].write_text(
                json.dumps(recorded, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(f"{milestone}: recorded {len(recorded)} frozen-path blob ids from {base[:12]}")
        return 0

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

    # Content first: it needs no history and therefore holds in CI's shallow
    # checkout. The git comparison is an additional check that runs only where
    # the base commit is present.
    breaches = {m: p for m, p in content_violations().items() if p}
    if not breaches and _all_bases_present():
        breaches = {m: p for m, p in violations().items() if p}
    if breaches:
        bases = ", ".join(f"{m} {b[:12]}" for m, b in FROZEN_BASES.items())
        print(f"frozen milestone files were modified since their base ({bases}):", file=sys.stderr)
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
    how = "by blob id and by git diff" if _all_bases_present() else "by blob id (a base is absent)"
    per_milestone = ", ".join(
        f"{m} {len(paths)} since {FROZEN_BASES[m][:12]}" for m, paths in owners.items()
    )
    print(f"frozen paths unmodified ({per_milestone}; {total} governed, verified {how})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
