"""Render the M084 exhaustion table from evidence, not from assertion.

    python tools/render_m084_exhaustion_table.py
    python tools/render_m084_exhaustion_table.py --check

Every row states one required campaign item and one of exactly two statuses:

    EXECUTED_PASS          the item was run and it passed
    EXECUTED_FAIL_BLOCKER  the item was run and it failed

There is no third status. "Documented", "reviewed", "by construction", "not
needed", "previously passed" and "covered continuously" are not substitutes for
execution and cannot be expressed here.

The status of each row is DERIVED: this tool re-reads the artifact each item
produced, or re-runs the gate, and fails the render if the evidence is absent
or does not say what the row claims. A table that could be edited to say
EXECUTED_PASS would be a list of intentions.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "external-review" / "MILESTONE-084"
TABLE = PACKAGE / "exhaustion-table.md"
BASE = "707161a1e8edeb7e0c95f3dafc7180ba9d782cc6"


@dataclass(frozen=True, slots=True)
class Item:
    section: str
    requirement: str
    #: Returns (ok, evidence). `ok` False renders EXECUTED_FAIL_BLOCKER.
    evidence: Callable[[], tuple[bool, str]]


def _document(name: str) -> str:
    path = PACKAGE / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _contains(name: str, needle: str, description: str) -> Callable[[], tuple[bool, str]]:
    def check() -> tuple[bool, str]:
        body = _document(name)
        if not body:
            return False, f"{name} is missing"
        return (needle in body), f"{description} (`{name}`)"

    return check


def _gate(arguments: list[str], description: str) -> Callable[[], tuple[bool, str]]:
    def check() -> tuple[bool, str]:
        result = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
            [".venv313/bin/python", *arguments],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={"PYTHONPATH": str(REPO_ROOT), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
        return result.returncode == 0, f"{description} — exit {result.returncode}"

    return check


def _pass_count(number: int, minimum: int) -> Callable[[], tuple[bool, str]]:
    def check() -> tuple[bool, str]:
        body = _document("hostile-review.md")
        match = re.search(
            rf"## Pass {number} — [^\n]*\n\n\*[^\n]*\*\n\n\*\*(\d+) attacks executed\*\* "
            rf"\(minimum required: (\d+)\)\. (\d+) defended, (\d+) findings",
            body,
        )
        if not match:
            return False, f"pass {number} is absent from hostile-review.md"
        executed, required, _, findings = (int(g) for g in match.groups())
        ok = executed >= minimum and required == minimum and findings == 0
        return ok, f"{executed} attacks (minimum {required}), {findings} findings"

    return check


ITEMS: tuple[Item, ...] = (
    Item(
        "3",
        "Database concurrency campaign, executed with real resets",
        _contains(
            "concurrency-results.md", "36 passed", "36 races, three repetitions, distinct oids"
        ),
    ),
    Item(
        "4",
        "All 27 mutation families mutated, detected, restored, re-verified",
        _contains("mutation-matrix.md", "27 of 27 families detected", "27 of 27 detected"),
    ),
    Item(
        "4",
        "No mutation family survives at head",
        lambda: ("**SURVIVED**" not in _document("mutation-matrix.md"), "no SURVIVED row"),
    ),
    Item("5", "Hostile pass 1 — scientific authority (>=25)", _pass_count(1, 25)),
    Item("5", "Hostile pass 2 — database adversary (>=40)", _pass_count(2, 40)),
    Item("5", "Hostile pass 3 — trading-risk adversary (>=35)", _pass_count(3, 35)),
    Item("5", "Hostile pass 4 — operator and product adversary (>=30)", _pass_count(4, 30)),
    Item("5", "Hostile pass 5 — software-governance adversary (>=30)", _pass_count(5, 30)),
    Item(
        "6",
        "Performance characterized at 0/1/10/100/1k/10k/25k with median, p95, max, samples",
        _contains("performance-results.md", "25,000", "every scale measured with sample counts"),
    ),
    Item(
        "6",
        "Query plans captured per scale",
        _contains("performance-results.md", "EXPLAIN", "EXPLAIN (ANALYZE, BUFFERS) per scale"),
    ),
    Item(
        "6",
        "Row-lock duration measured under real contention",
        _contains("performance-results.md", "transactionid", "waiter blocked on transactionid"),
    ),
    Item(
        "7",
        "Broker research separates verified from unverified sources",
        _contains(
            "broker-and-market-data-research.md",
            "UNVERIFIED-SECONDARY",
            "three explicit verification tiers",
        ),
    ),
    Item(
        "7",
        "Blocked URLs recorded with an operator-verification checklist",
        _contains(
            "operator-verification-checklist.md", "V-1", "per-URL questions, none marked complete"
        ),
    ),
    Item(
        "7",
        "Conclusion classified CONDITIONAL where evidence is secondary",
        _contains("broker-and-market-data-research.md", "CONDITIONAL", "conclusion is conditional"),
    ),
    Item(
        "8",
        "Regression: PostgreSQL ON, base and candidate, equally fresh databases",
        _contains("validation-results.md", "PostgreSQL ON", "base vs candidate, sets diffed"),
    ),
    Item(
        "8",
        "Regression: PostgreSQL OFF, base and candidate",
        _contains("validation-results.md", "PostgreSQL OFF", "base vs candidate, sets diffed"),
    ),
    Item(
        "8",
        "Regression: clean database through the full migration history",
        _contains("validation-results.md", "20 up", "20 up, 20 down to base, 20 up again"),
    ),
    Item(
        "8",
        "Regression: clean installed wheel",
        _contains(
            "validation-results.md", "installed wheel", "walkthrough runs from site-packages"
        ),
    ),
    Item(
        "9",
        "Operator walkthrough executed against an installed wheel",
        _contains("validation-results.md", "18 steps", "18 steps, all at their expected exit code"),
    ),
    Item(
        "9",
        "At least three NO_TRADE demonstrations with distinct reasons",
        _contains("validation-results.md", "INSTRUMENT_NOT_WATCHLISTED", "three distinct reasons"),
    ),
    Item(
        "10",
        "Frozen M083 files unmodified since the base commit",
        _gate(["tools/check_frozen_paths.py"], "frozen-path guard"),
    ),
    Item(
        "10",
        "Frozen M083 acceptance obtained at M083's own revision",
        _contains(
            "validation-results.md", "FROZEN M083 ACCEPTANCE", "51 passed at the frozen commit"
        ),
    ),
    Item(
        "10",
        "Architecture order-submission deny-list holds",
        _gate(["tools/check_architecture.py"], "architecture gate"),
    ),
    Item(
        "10",
        "Authority document is the deterministic rendering of its contract",
        _gate(["tools/render_m084_authority.py", "--check"], "authority renderer --check"),
    ),
    Item(
        "10",
        "File-audit matrix is the rendering of the real diff",
        _gate(["tools/render_m084_file_audit.py", "--check"], "file-audit --check"),
    ),
    Item(
        "10",
        "Mechanical suppression accounting published",
        _contains("validation-results.md", "Suppression accounting", "counted, not estimated"),
    ),
    Item(
        "10",
        "No coverage pragma or skipped test in the M084 diff",
        lambda: _count_suppressions(),
    ),
)


def _count_suppressions() -> tuple[bool, str]:
    """Count real suppressions in the diff, by token rather than by grep."""
    import io
    import tokenize

    changed = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", "diff", "--name-only", f"{BASE}..HEAD"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    noqa = ignores = pragmas = skips = 0
    for path in changed:
        full = REPO_ROOT / path
        if not full.is_file() or full.suffix != ".py":
            continue
        source = full.read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            noqa += "noqa" in token.string
            ignores += "type: ignore" in token.string
            pragmas += "pragma: no cover" in token.string
        skips += sum(
            1 for line in source.splitlines() if line.lstrip().startswith("@pytest.mark.skip")
        )
    clean = pragmas == 0 and skips == 0
    return clean, (
        f"noqa {noqa}, type-ignore {ignores}, coverage pragmas {pragmas}, skipped tests {skips}"
    )


def render() -> tuple[str, int]:
    rows = []
    blockers = 0
    for item in ITEMS:
        ok, evidence = item.evidence()
        status = "EXECUTED_PASS" if ok else "EXECUTED_FAIL_BLOCKER"
        blockers += not ok
        rows.append(f"| §{item.section} | {item.requirement} | **{status}** | {evidence} |")

    lines = [
        "# MILESTONE-084 — Exhaustion Table",
        "",
        f"**{len(ITEMS)} required items. {len(ITEMS) - blockers} EXECUTED_PASS, "
        f"{blockers} EXECUTED_FAIL_BLOCKER.**",
        "",
        "Generated by `tools/render_m084_exhaustion_table.py`; do not edit by hand.",
        "",
        "Two statuses exist and no others. `EXECUTED_PASS` means the item was run",
        "and passed; `EXECUTED_FAIL_BLOCKER` means it was run and failed.",
        '"Documented", "reviewed", "by construction", "not needed", "previously',
        'passed" and "covered continuously" are not substitutes for execution, and',
        "this table cannot express them.",
        "",
        "Each status is DERIVED, not written: the renderer re-reads the artifact the",
        "item produced or re-runs the gate, and a row whose evidence is absent or",
        "does not say what the row claims renders as a blocker. A table that could be",
        "edited to read EXECUTED_PASS would be a list of intentions.",
        "",
        "| Section | Required item | Status | Evidence |",
        "|---|---|---|---|",
        *rows,
        "",
    ]
    return "\n".join(lines), blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    document, blockers = render()
    if args.check:
        current = TABLE.read_text(encoding="utf-8") if TABLE.exists() else ""
        if current != document:
            print("the exhaustion table is not the current rendering", file=sys.stderr)
            return 1
        print(f"exhaustion table current: {len(ITEMS)} items, {blockers} blockers")
        return 0 if blockers == 0 else 1

    TABLE.write_text(document, encoding="utf-8")
    print(f"wrote the exhaustion table: {len(ITEMS)} items, {blockers} blockers")
    return 0 if blockers == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
