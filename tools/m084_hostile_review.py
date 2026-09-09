"""MILESTONE-084 hostile review — five formally separate adversarial passes.

    python tools/m084_hostile_review.py --pass 1
    python tools/m084_hostile_review.py --all --markdown-out <file>

Each pass takes a different adversary's position and attacks from it. An attack
here is a piece of code that RUNS: it tries to do the thing the product says is
impossible, and reports what actually happened. A pass whose attacks are
arguments about the design proves nothing, because an argument cannot fail.

Every attack reports one of:

    DEFENDED  the attack ran and the product refused it, for the stated reason
    FINDING   the attack ran and the product allowed it, or refused it for the
              wrong reason, or the claim it targets is not actually checked
    N/A       the attack could not run here, with the reason recorded

`DEFENDED` requires the refusal to be the SPECIFIC one claimed. An attack that
fails because of an unrelated typo in its own SQL has proved nothing and is a
FINDING against the attack, not a defence of the product -- so every database
attack asserts the message names the rule it was aimed at.

The five passes, and what each refuses to take on trust:

    1  Scientific authority     every published claim, checked against runtime
    2  Database adversary       raw SQL, around the domain layer entirely
    3  Trading-risk adversary   the money rules, from a trader's angle
    4  Operator/product         the human surface, from a tired operator's angle
    5  Software governance      the repository's own rules about itself
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

PACKAGE = REPO_ROOT / "external-review" / "MILESTONE-084"
DATABASE = "empirical_hostile"


@dataclass(slots=True)
class Attack:
    """One executed attack and what actually happened."""

    identifier: str
    target: str
    attempt: str
    verdict: str
    evidence: str


@dataclass(slots=True)
class Pass:
    number: int
    adversary: str
    stance: str
    minimum: int
    attacks: list[Attack] = field(default_factory=list)

    def record(self, identifier: str, target: str, attempt: str) -> Callable[..., None]:
        def done(verdict: str, evidence: str) -> None:
            self.attacks.append(Attack(identifier, target, attempt, verdict, evidence))

        return done

    @property
    def findings(self) -> list[Attack]:
        return [a for a in self.attacks if a.verdict == "FINDING"]


# ---------------------------------------------------------------------------
# infrastructure
# ---------------------------------------------------------------------------


def _psql(*arguments: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["sudo", "-u", "postgres", "psql", *arguments],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def rebuild_database() -> int:
    _psql(
        "-q",
        "-c",
        f"DROP DATABASE IF EXISTS {DATABASE}",
        "-c",
        f"CREATE DATABASE {DATABASE} OWNER empirical",
    )
    environment = dict(os.environ)
    environment["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = DATABASE
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        [".venv313/bin/python", "-m", "alembic", "upgrade", "head"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        env=environment,
    )
    return int(
        _psql(
            "-d", DATABASE, "-tAc", "SELECT oid FROM pg_database WHERE datname = current_database()"
        ).strip()
    )


@contextmanager
def _engine() -> Iterator[Any]:
    import sqlalchemy as sa
    from pydantic import SecretStr

    from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

    config = PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=DATABASE,
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=4,
        max_overflow=4,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m084-hostile",
    )
    engine = sa.create_engine(config.sqlalchemy_url(), pool_size=4, max_overflow=4)
    try:
        yield engine
    finally:
        engine.dispose()


def refused_by(action: Callable[[], object], expected: str) -> tuple[str, str]:
    """Run an attack that must be refused, and check WHY it was refused.

    An attack that fails for an unrelated reason -- a typo in its own SQL, a
    missing column -- has demonstrated nothing about the rule it was aimed at.
    Returning DEFENDED for that would be the single easiest way to build a
    hostile review that finds nothing and means nothing.
    """
    try:
        action()
    except Exception as error:  # noqa: BLE001 - the message is the evidence
        message = str(error).replace("\n", " ")[:400]
        if expected.lower() in message.lower():
            return "DEFENDED", f"refused: ...{expected}..."
        return "FINDING", f"refused for the WRONG reason (expected {expected!r}): {message}"
    return "FINDING", "the attack SUCCEEDED; the rule did not stop it"


def allowed(action: Callable[[], object]) -> tuple[str, str]:
    """Run something that must be permitted. A refusal here is the finding."""
    try:
        action()
    except Exception as error:  # noqa: BLE001 - the message is the evidence
        return "FINDING", f"legitimate action was refused: {str(error)[:300]}"
    return "DEFENDED", "permitted, as it must be"


def render_markdown(passes: list[Pass], oid: int, commit: str) -> str:
    total = sum(len(p.attacks) for p in passes)
    findings = sum(len(p.findings) for p in passes)
    lines = [
        "# MILESTONE-084 — Hostile Review",
        "",
        f"**{total} executed attacks across {len(passes)} passes. {findings} findings.**",
        "",
        f"Starting commit `{commit}`. Database rebuilt through the full migration",
        f"history; `pg_database.oid` {oid}.",
        "",
        "Generated by `tools/m084_hostile_review.py`; do not edit by hand.",
        "",
        "An attack here is code that RUNS. It tries to do the thing the product",
        "says is impossible and reports what actually happened. A pass whose",
        "attacks are arguments about the design proves nothing, because an",
        "argument cannot fail.",
        "",
        "`DEFENDED` requires the refusal to be the SPECIFIC one claimed. An attack",
        "that fails because of an unrelated typo in its own SQL has proved nothing,",
        "so every refusal is checked against the rule it was aimed at — otherwise",
        "the easiest possible hostile review is one that finds nothing and means",
        "nothing.",
        "",
    ]
    for review in passes:
        defended = sum(1 for a in review.attacks if a.verdict == "DEFENDED")
        not_run = sum(1 for a in review.attacks if a.verdict == "N/A")
        lines += [
            f"## Pass {review.number} — {review.adversary}",
            "",
            f"*{review.stance}*",
            "",
            f"**{len(review.attacks)} attacks executed** (minimum required: "
            f"{review.minimum}). {defended} defended, {len(review.findings)} findings"
            + (f", {not_run} not runnable here" if not_run else "")
            + ".",
            "",
            "| # | Target | Attack | Verdict | Evidence |",
            "|---|---|---|---|---|",
        ]
        for attack in review.attacks:
            lines.append(
                f"| {attack.identifier} | {attack.target} | {attack.attempt} | "
                f"**{attack.verdict}** | {attack.evidence} |"
            )
        lines.append("")
        if review.findings:
            lines += ["### Findings from this pass", ""]
            for finding in review.findings:
                lines.append(f"- **{finding.identifier}** — {finding.attempt}: {finding.evidence}")
            lines.append("")
        lines += [
            "**Terminal conclusion.** "
            + (
                f"{len(review.findings)} finding(s) require correction before this pass closes."
                if review.findings
                else "Every attack in this pass was defended for the reason claimed. "
                "This pass closes with no outstanding finding."
            ),
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from tools.m084_hostile_passes import PASS_BUILDERS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass", dest="which", type=int, help="run one pass")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)

    if "EMPIRICAL_PLATFORM_POSTGRES_PASSWORD" not in os.environ:
        print("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD is unset", file=sys.stderr)
        return 2

    commit = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    oid = rebuild_database()
    selected = [n for n in sorted(PASS_BUILDERS) if args.all or n == args.which]
    if not selected:
        print("nothing selected: pass --all or --pass N", file=sys.stderr)
        return 2

    results = []
    with _engine() as engine:
        for number in selected:
            review = PASS_BUILDERS[number](engine)
            results.append(review)
            shortfall = (
                f"  ** BELOW THE REQUIRED MINIMUM of {review.minimum}"
                if len(review.attacks) < review.minimum
                else ""
            )
            print(
                f"Pass {review.number} — {review.adversary}: "
                f"{len(review.attacks)} attacks, {len(review.findings)} findings{shortfall}"
            )
            for finding in review.findings:
                print(f"    FINDING {finding.identifier}: {finding.evidence}")

    if args.markdown_out:
        args.markdown_out.write_text(render_markdown(results, oid, commit), encoding="utf-8")
    if args.json_out:
        args.json_out.write_text(
            json.dumps(
                [
                    {
                        "pass": r.number,
                        "adversary": r.adversary,
                        "minimum": r.minimum,
                        "attacks": [asdict(a) for a in r.attacks],
                    }
                    for r in results
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    findings = sum(len(r.findings) for r in results)
    short = [r for r in results if len(r.attacks) < r.minimum]
    print(f"\n{sum(len(r.attacks) for r in results)} attacks, {findings} findings")
    if short:
        print(f"passes below their required minimum: {[r.number for r in short]}", file=sys.stderr)
    return 0 if findings == 0 and not short else 1


if __name__ == "__main__":
    raise SystemExit(main())
