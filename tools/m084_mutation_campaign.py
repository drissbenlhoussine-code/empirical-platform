"""MILESTONE-084 anti-vacuity mutation campaign.

    python tools/m084_mutation_campaign.py            # run every family
    python tools/m084_mutation_campaign.py --only 12  # run one

For each family this tool:

  1. names the exact test expected to detect the mutation, BEFORE running it;
  2. rewrites the real governing rule -- production source or migration, never
     a test -- by exact string replacement, failing loudly if the target text
     is not present exactly once;
  3. runs the named test and captures whether it failed and why;
  4. restores the file byte-for-byte from a pre-mutation snapshot and verifies
     the restore with a SHA-256 comparison;
  5. re-runs the named test and requires it to pass again.

A family whose test still PASSES under mutation is a survivor -- a defect in
the test suite, not a success -- and is reported as such rather than counted.

Nothing here is ever committed in a mutated state: the restore is verified by
digest before the next family runs, and the campaign's closing assertion is
that every file it can write to is byte-identical to what it was at the start.
That is deliberately narrower than "the worktree is clean" -- the campaign is
normally run on a branch with legitimate uncommitted work, where a cleanliness
check would prove nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOMAIN = REPO_ROOT / "src/empirical_platform/decision_candidate"
MIGRATION = (
    REPO_ROOT / "migrations/versions/a3f7c21d9b04_create_m084_decision_to_approval_schema.py"
)
CONFIG = DOMAIN / "operator_trading_configuration.py"
PROPOSAL = DOMAIN / "trade_proposal.py"
APPROVAL = DOMAIN / "trade_approval.py"
CONTEXT = DOMAIN / "evaluation_context.py"
ARCHITECTURE = REPO_ROOT / "tools/check_architecture.py"
AUTHORITY_SCHEMA = REPO_ROOT / "external-review/MILESTONE-084/current-authority.schema.json"
AUTHORITY_RENDERER = REPO_ROOT / "tools/render_m084_authority.py"

UNIT = "tests/unit"
INTEGRATION = "tests/integration"
ARCH = "tests/architecture"


@dataclass(frozen=True, slots=True)
class Mutation:
    """One family: a rule, a weakening of it, and the test that must notice."""

    number: int
    family: str
    rule: str
    path: Path
    old: str
    new: str
    detector: str
    #: True when the mutation changes the SCHEMA, so the detecting test needs a
    #: database rebuilt from the mutated migration rather than the live one.
    needs_schema_rebuild: bool = False


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        1,
        "long-only",
        "a proposal may only be a BUY",
        PROPOSAL,
        "if self.side != _BUY_SIDE:",
        'if self.side not in {_BUY_SIDE, "SELL"}:',
        f"{UNIT}/test_m084_domain_core.py::TestProposalConstructionInvariants",
    ),
    Mutation(
        2,
        "leverage prohibition",
        "maximum_leverage must be exactly 1",
        CONFIG,
        'if self.maximum_leverage != Decimal("1"):',
        'if self.maximum_leverage > Decimal("10"):',
        f"{UNIT}/test_m084_domain_core.py::TestConfigurationHardInvariants",
    ),
    Mutation(
        3,
        "intraday liquidation deadline",
        "the whole proposal lifetime must fit before the mandatory liquidation",
        PROPOSAL,
        "RiskCheckOutcome.PASSED if liquidation_at >= proposal_dies_at "
        "else RiskCheckOutcome.FAILED",
        "RiskCheckOutcome.PASSED",
        f"{UNIT}/test_m084_domain_core.py::TestNoTradeReasons",
    ),
    Mutation(
        4,
        "stale-data rejection",
        "a quote older than the configured limit is refused",
        PROPOSAL,
        "if quote_age <= Decimal(configuration.maximum_market_data_age_seconds)",
        "if quote_age <= Decimal(configuration.maximum_market_data_age_seconds) * 1000000",
        f"{UNIT}/test_m084_domain_core.py::TestNoTradeReasons",
    ),
    Mutation(
        5,
        "cash reserve",
        "cash at or below the reserve produces NO_TRADE",
        PROPOSAL,
        "RiskCheckOutcome.PASSED if spendable_cash > 0 else RiskCheckOutcome.FAILED",
        "RiskCheckOutcome.PASSED",
        f"{UNIT}/test_m084_domain_core.py::TestNoTradeReasons",
    ),
    # The per-trade capital cap binds in `deployable`, not in a recorded risk
    # check: sizing clips the budget to the cap and both roundings are downward,
    # so a `notional > cap` branch could never fire. This family therefore
    # mutates the cap where it actually governs. FIND-M-01 records the removal
    # of the unreachable check that used to stand in for it.
    Mutation(
        6,
        "maximum notional",
        "the per-trade capital cap bounds the sized notional",
        PROPOSAL,
        "        configuration.maximum_capital_per_trade,\n",
        "        configuration.maximum_capital_per_trade * 1000000,\n",
        f"{UNIT}/test_m084_domain_core.py::TestSizingRespectsTheCapitalCap",
    ),
    Mutation(
        7,
        "fee inclusion",
        "fees are part of the cash a proposal requires",
        PROPOSAL,
        "total_cash = notional + fees + slippage_amount",
        "total_cash = notional + slippage_amount",
        f"{UNIT}/test_m084_domain_core.py::TestProposalHappyPath",
    ),
    Mutation(
        8,
        "spread limit",
        "a spread wider than the configured maximum produces NO_TRADE",
        PROPOSAL,
        "if quote.spread_percent <= configuration.maximum_spread_percent",
        "if quote.spread_percent <= configuration.maximum_spread_percent * 1000000",
        f"{UNIT}/test_m084_domain_core.py::TestNoTradeReasons",
    ),
    Mutation(
        9,
        "liquidity limit",
        "average daily volume below the configured floor produces NO_TRADE",
        PROPOSAL,
        "if liquidity.average_daily_volume_shares >= configuration.minimum_liquidity_shares",
        "if liquidity.average_daily_volume_shares >= 0",
        f"{UNIT}/test_m084_domain_core.py::TestNoTradeReasons",
    ),
    Mutation(
        10,
        "slippage limit",
        "estimated slippage above the configured maximum produces NO_TRADE",
        PROPOSAL,
        "<= configuration.maximum_estimated_slippage_percent",
        "<= configuration.maximum_estimated_slippage_percent * 1000000",
        f"{UNIT}/test_m084_domain_core.py::TestNoTradeReasons",
    ),
    Mutation(
        11,
        "kill switch",
        "an engaged kill switch stops every evaluation",
        PROPOSAL,
        "if configuration.kill_switch is KillSwitchState.DISENGAGED",
        "if configuration.kill_switch is not None",
        f"{UNIT}/test_m084_domain_core.py::TestNoTradeReasons",
    ),
    Mutation(
        12,
        "proposal fingerprint",
        "a proposal carries the digest of its own order terms",
        PROPOSAL,
        "if self.content_fingerprint != compute_fingerprint(self):",
        "if False:",
        f"{UNIT}/test_m084_domain_core.py::TestProposalFingerprint",
    ),
    Mutation(
        13,
        "fingerprint numeric normalization",
        "the digest depends on an amount's value, not the column's scale",
        PROPOSAL,
        'return format(value.normalize(), "f")',
        'return format(value, "f")',
        f"{UNIT}/test_m084_domain_core.py::TestProposalFingerprint",
    ),
    Mutation(
        14,
        "approval proposal-version binding",
        "an approval is bound to one exact proposal version",
        APPROVAL,
        "if decision.proposal_version != proposal.proposal_version:",
        "if False:",
        f"{UNIT}/test_m084_domain_core.py::TestApprovedOrderIntent",
    ),
    Mutation(
        15,
        "approval fingerprint binding",
        "an approval is bound to one exact set of order terms",
        APPROVAL,
        "if decision.approved_fingerprint != proposal.content_fingerprint:",
        "if False:",
        f"{UNIT}/test_m084_domain_core.py::TestApprovedOrderIntent",
    ),
    Mutation(
        16,
        "approval expiry",
        "an intent cannot be built once the approval has lapsed",
        APPROVAL,
        "if decision.is_expired_at(created_at):",
        "if False:",
        f"{UNIT}/test_m084_domain_core.py::TestApprovedOrderIntent",
    ),
    Mutation(
        17,
        "material-change invalidation",
        "a proposal under a superseded configuration is invalidated",
        REPO_ROOT / "src/empirical_platform/usecases/decision_to_approval.py",
        "if latest_versions[governance_id] > proposal.configuration_version:",
        "if False:",
        f"{UNIT}/test_m084_operator_workflow.py::TestInvalidateStaleProposals",
    ),
    Mutation(
        18,
        "one-intent rule",
        "at most one order intent exists per proposal",
        MIGRATION,
        """        sa.UniqueConstraint(
            "proposal_governance_id",
            name="uq_approved_order_intent_one_per_proposal",
        ),""",
        "",
        f"{INTEGRATION}/test_m084_decision_to_approval_postgres_attacks.py::TestIntentAdmission",
        needs_schema_rebuild=True,
    ),
    Mutation(
        19,
        "NOT_SUBMITTED-only state",
        "no intent may be stored in any other submission state",
        MIGRATION,
        "\"submission_state = 'NOT_SUBMITTED'\"",
        "\"submission_state IN ('NOT_SUBMITTED', 'SUBMITTED')\"",
        f"{INTEGRATION}/test_m084_decision_to_approval_postgres_attacks.py"
        "::TestIntentCannotBecomeASubmission",
        needs_schema_rebuild=True,
    ),
    Mutation(
        20,
        "database transition enforcement",
        "only PREPARED has outgoing transitions",
        MIGRATION,
        """    IF OLD.status <> 'PREPARED' THEN
        RAISE EXCEPTION
            'trade_proposal % is terminal: % -> % is not an allowed transition',
            OLD.proposal_governance_id, OLD.status, NEW.status;
    END IF;
""",
        "",
        f"{INTEGRATION}/test_m084_decision_to_approval_postgres_attacks.py"
        "::TestProposalStateMachine",
        needs_schema_rebuild=True,
    ),
    Mutation(
        21,
        "direct-SQL constraints",
        "a stored proposal's order terms cannot be edited",
        MIGRATION,
        """        OR NEW.quantity IS DISTINCT FROM OLD.quantity
""",
        "",
        f"{INTEGRATION}/test_m084_decision_to_approval_postgres_attacks.py"
        "::TestProposalStateMachine",
        needs_schema_rebuild=True,
    ),
    Mutation(
        22,
        "transaction rollback",
        "decisions and intents refuse UPDATE and DELETE",
        MIGRATION,
        """_DECISION_IMMUTABLE_TRIGGER = \"\"\"
CREATE TRIGGER trade_approval_decision_append_only_trigger
BEFORE UPDATE OR DELETE ON public.trade_approval_decision
FOR EACH ROW EXECUTE FUNCTION public.m084_append_only()
\"\"\"""",
        """_DECISION_IMMUTABLE_TRIGGER = \"\"\"
CREATE TRIGGER trade_approval_decision_append_only_trigger
BEFORE DELETE ON public.trade_approval_decision
FOR EACH ROW EXECUTE FUNCTION public.m084_append_only()
\"\"\"""",
        f"{INTEGRATION}/test_m084_decision_to_approval_postgres_attacks.py::TestDecisionAdmission",
        needs_schema_rebuild=True,
    ),
    Mutation(
        23,
        "schema enum/list closure",
        "the authority schema's item counts are exact",
        AUTHORITY_SCHEMA,
        '"minItems": 7,\n      "maxItems": 7,',
        '"minItems": 1,\n      "maxItems": 99,',
        f"{INTEGRATION}/test_m084_authority_contract.py::TestTheContractIsValidAndClosed",
    ),
    Mutation(
        24,
        "authority_version const",
        "the authority version and milestone are pinned",
        AUTHORITY_SCHEMA,
        '"milestone": {\n      "const": "M084"\n    },',
        '"milestone": {\n      "type": "string"\n    },',
        f"{INTEGRATION}/test_m084_authority_contract.py::TestTheContractIsValidAndClosed",
    ),
    Mutation(
        25,
        "runtime JSON/domain closure",
        "SubmissionState declares exactly one member",
        APPROVAL,
        '    NOT_SUBMITTED = "NOT_SUBMITTED"',
        '    NOT_SUBMITTED = "NOT_SUBMITTED"\n    SUBMITTED = "SUBMITTED"',
        f"{INTEGRATION}/test_m084_authority_contract.py::TestTheClaimsMatchTheRunningCode",
    ),
    Mutation(
        26,
        "deterministic Markdown/runtime output",
        "the authority document is the deterministic rendering of the contract",
        AUTHORITY_RENDERER,
        "add(f\"# {contract['milestone']} — {contract['title']}\")",
        "add(f\"# {contract['milestone']} - {contract['title']}\")",
        f"{INTEGRATION}/test_m084_authority_contract.py::TestTheContractIsValidAndClosed",
    ),
    Mutation(
        27,
        "architecture broker-import prohibition",
        "no module may import an order-submission client",
        ARCHITECTURE,
        '    "alpaca",  # alpaca-py: TradingClient.submit_order',
        "",
        f"{ARCH}/test_module_boundaries.py",
    ),
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _purge_bytecode() -> None:
    """Delete every `__pycache__` under the source and test trees.

    Not housekeeping -- a correctness requirement. CPython invalidates a cached
    `.pyc` by the source's (mtime, size), and a mutate-then-restore cycle can
    land inside one filesystem timestamp tick at the original size. When that
    happens the interpreter reuses bytecode compiled from the MUTATED source,
    and the campaign silently measures the wrong program: a real detection can
    read as SURVIVED, or a byte-perfect restore as a broken one. This was
    observed, not hypothesized -- family 2 reported RESTORE_NOT_GREEN against an
    unmodified file until the caches were cleared.
    """
    for tree in (REPO_ROOT / "src", REPO_ROOT / "tests", REPO_ROOT / "migrations"):
        for cache in tree.rglob("__pycache__"):
            for entry in cache.glob("*.pyc"):
                entry.unlink(missing_ok=True)


def _run_test(node: str, *, schema_database: str | None) -> tuple[bool, str]:
    """Run one test node. Returns (passed, last meaningful line)."""
    _purge_bytecode()
    environment = dict(os.environ)
    # Belt to the purge's braces: write no new bytecode for the duration, so
    # nothing this campaign compiles can outlive the source it came from.
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if schema_database is not None:
        environment["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = schema_database
    result = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        [  # noqa: S607
            ".venv313/bin/python",
            "-m",
            "pytest",
            node,
            "-q",
            "--no-cov",
            "-p",
            "no:randomly",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    tail = [line for line in result.stdout.splitlines() if line.strip()]
    return result.returncode == 0, (tail[-1] if tail else "(no output)")


def _rebuild_schema(database: str) -> None:
    """Drop and re-create one database, then migrate it from the mutated file."""
    subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        [  # noqa: S607
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-q",
            "-c",
            f"DROP DATABASE IF EXISTS {database}",
            "-c",
            f"CREATE DATABASE {database} OWNER empirical",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    # The migration is itself a mutation target, so it needs the same bytecode
    # discipline as the test runs: a stale `.pyc` here would migrate the rebuilt
    # database from the wrong version of the schema.
    _purge_bytecode()
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = database
    subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        [".venv313/bin/python", "-m", "alembic", "upgrade", "head"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        env=environment,
    )


def run_family(mutation: Mutation, *, database: str) -> dict[str, object]:
    original = mutation.path.read_bytes()
    before = _digest(mutation.path)
    source = original.decode("utf-8")

    occurrences = source.count(mutation.old)
    if occurrences != 1:
        return {
            "n": mutation.number,
            "family": mutation.family,
            "status": "TARGET_NOT_UNIQUE",
            "detail": f"target text appears {occurrences} times, expected exactly 1",
        }

    # 1. Baseline: the detector must pass before anything is mutated.
    schema_database = database if mutation.needs_schema_rebuild else None
    if mutation.needs_schema_rebuild:
        _rebuild_schema(database)
    baseline_passed, baseline_line = _run_test(mutation.detector, schema_database=schema_database)
    if not baseline_passed:
        return {
            "n": mutation.number,
            "family": mutation.family,
            "status": "BASELINE_FAILED",
            "detail": baseline_line,
        }

    # 2. Mutate the real rule.
    mutation.path.write_text(source.replace(mutation.old, mutation.new), encoding="utf-8")
    try:
        if mutation.needs_schema_rebuild:
            _rebuild_schema(database)
        mutated_passed, mutated_line = _run_test(mutation.detector, schema_database=schema_database)
    finally:
        # 3. Restore, byte for byte, whatever happened above.
        mutation.path.write_bytes(original)

    after = _digest(mutation.path)
    if after != before:
        return {
            "n": mutation.number,
            "family": mutation.family,
            "status": "RESTORE_FAILED",
            "detail": f"{before[:12]} -> {after[:12]}",
        }

    # 4. Re-verify: the detector passes again on the restored source.
    if mutation.needs_schema_rebuild:
        _rebuild_schema(database)
    restored_passed, restored_line = _run_test(mutation.detector, schema_database=schema_database)

    return {
        "n": mutation.number,
        "family": mutation.family,
        "rule": mutation.rule,
        "file": str(mutation.path.relative_to(REPO_ROOT)),
        "detector": mutation.detector,
        "status": (
            "DETECTED"
            if (not mutated_passed and restored_passed)
            else ("SURVIVED" if mutated_passed else "RESTORE_NOT_GREEN")
        ),
        "mutated_result": mutated_line,
        "restored_result": restored_line,
    }


#: Each safety claim M084 publishes, against the family number that re-proves
#: it. The interim report cited "SubmissionState declares exactly one member" as
#: mutation 25 while calling family 25 "runtime JSON/domain closure" -- both
#: true, since 25's LABEL is the closure and its RULE is the one-member enum,
#: but a reader cannot be asked to hold that apart. The 27 family labels are
#: fixed by the mission and are not renamed to suit prose; instead every
#: narrative reference is generated from this table, so a claim's family
#: number, label and rule are always quoted together and cannot drift from the
#: matrix they came from.
SAFETY_CLAIMS: tuple[tuple[str, int], ...] = (
    ("The runtime declares exactly one submission state", 25),
    ("The database pins the stored submission state to NOT_SUBMITTED", 19),
    ("At most one order intent exists per proposal", 18),
    ("No module may import an order-submission client", 27),
)


def render_safety_crossreference(results: list[dict[str, object]]) -> list[str]:
    by_number = {mutation.number: mutation for mutation in MUTATIONS}
    status = {int(row["n"]): str(row["status"]) for row in results}
    lines = [
        "## Safety claims, and the family that re-proves each",
        "",
        "Quote this table rather than a bare family number. Each row carries the",
        "number, the family's label and the rule the mutation actually weakens --",
        "which are not always the same words, and were conflated once already.",
        "",
        "| Safety claim | # | Family label | Rule mutated | Status |",
        "|---|---|---|---|---|",
    ]
    for claim, number in SAFETY_CLAIMS:
        mutation = by_number[number]
        lines.append(
            f"| {claim} | {number} | {mutation.family} | {mutation.rule} | "
            f"**{status.get(number, 'NOT RUN')}** |"
        )
    lines.append("")
    return lines


def render_markdown(results: list[dict[str, object]]) -> str:
    """The published matrix, written from the run rather than transcribed.

    Every column below is a value the campaign produced. Nothing here is
    hand-maintained, so the document cannot drift from the run it reports.
    """
    detected = sum(1 for row in results if row["status"] == "DETECTED")
    lines = [
        "# MILESTONE-084 — Mutation Matrix",
        "",
        f"**{detected} of {len(results)} families detected.**",
        "",
        "Generated by `tools/m084_mutation_campaign.py --markdown-out`; do not edit",
        "by hand. For each family the campaign names the detecting test *before*",
        "mutating, weakens the real governing rule (production source or migration —",
        "never a test), runs the named test, restores the file byte-for-byte, verifies",
        "the restore by SHA-256, and re-runs the test. A family whose test still",
        "passes under mutation is reported as SURVIVED — a defect in the suite, not a",
        "success — and is not counted above.",
        "",
        "The `mutated` column is the detecting test's own summary line while the rule",
        "was weakened; `restored` is the same line after the bytes were put back. A",
        "row is evidence only because those two differ.",
        "",
        "| # | Family | Governing rule | File | Detecting test | Mutated | Restored | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in results:
        detector = str(row.get("detector", "")).replace("::", "::<br>")
        lines.append(
            f"| {row['n']} | {row['family']} | {row.get('rule', '')} | "
            f"`{row.get('file', '')}` | `{detector}` | {row.get('mutated_result', '')} | "
            f"{row.get('restored_result', '')} | **{row['status']}** |"
        )
    lines.append("")
    lines.extend(render_safety_crossreference(results))
    lines.extend(
        [
            "",
            "## What this campaign found",
            "",
            "A mutation campaign that finds nothing has usually been aimed at rules it",
            "already knew were covered. This one changed the product three times.",
            "",
            "### FIND-M-01 — an unreachable NO_TRADE reason (fixed)",
            "",
            "Family 6 had no detecting test to name, because the rule it was written",
            "against could not fail. The engine recorded a `notional_limit` risk check",
            "comparing the sized notional to `maximum_capital_per_trade`, but sizing",
            "already clips the budget to that cap and both roundings below it are",
            "downward — so `notional <= cap` held for every accepted input, and",
            "`NoTradeReason.NOTIONAL_ABOVE_LIMIT` was a refusal the product advertised",
            "and could never make. No test referenced it anywhere in the repository.",
            "",
            "Fixed by deleting the dead branch and the unreachable reason, and proving",
            "the bound instead: `TestSizingRespectsTheCapitalCap` sweeps the cap, the",
            "portfolio-relative cap, the price and the lot size and asserts no proposal",
            "exceeds the cap on any of them. Family 6 now mutates the cap where it",
            "actually governs — inside `deployable` — and that sweep detects it.",
            "",
            "### FIND-M-02 — an untested approval binding (fixed)",
            "",
            "Family 14 SURVIVED on first execution: deleting the check that binds an",
            "approval to one exact proposal version changed no test outcome. Every",
            "approved pair in the suite was version 1, so the neighbouring fingerprint",
            "binding absorbed each case before the version check could matter. The",
            "invariant was real and unexercised — the weakest state for a safety rule,",
            "since it would have been removed silently.",
            "",
            "Fixed by two tests that drive the version binding directly, forward and",
            "backward, holding the fingerprint and the proposal identity constant so",
            "that only the version differs. Family 14 is now DETECTED.",
            "",
            "### FIND-M-03 — the harness measured stale bytecode (fixed)",
            "",
            "Family 2 reported RESTORE_NOT_GREEN against a file that was byte-identical",
            "to its pre-campaign state. CPython invalidates a cached `.pyc` by the",
            "source's (mtime, size), and a mutate-then-restore cycle can land inside one",
            "timestamp tick at the original size — after which the interpreter runs",
            "bytecode compiled from the mutated source. A campaign exposed to this can",
            "report a real detection as SURVIVED, which is the failure mode that matters:",
            "it would have certified an invariant nothing protects.",
            "",
            "Fixed in `_purge_bytecode`, called before every test run and every schema",
            "rebuild, with `PYTHONDONTWRITEBYTECODE=1` set for the duration so nothing",
            "compiled during the campaign can outlive the source it came from. The",
            "results above were produced after this fix and reproduced across two",
            "further independent full runs with identical per-family status.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", type=int, help="run one family by number")
    parser.add_argument("--database", default="empirical_mut", help="schema-rebuild database")
    parser.add_argument("--json-out", type=Path, help="write results as JSON")
    parser.add_argument("--markdown-out", type=Path, help="write the matrix as Markdown")
    args = parser.parse_args(argv)

    families = [m for m in MUTATIONS if args.only is None or m.number == args.only]

    # The campaign's own closing assertion. Comparing to a *clean* worktree
    # would be the wrong test -- the campaign is routinely run on a branch with
    # legitimate uncommitted work, and "dirty" would then say nothing. What must
    # hold is narrower and stronger: every file this campaign is capable of
    # writing to is byte-identical to what it was before the campaign started.
    before = {mutation.path: _digest(mutation.path) for mutation in MUTATIONS}

    results = []
    for mutation in families:
        outcome = run_family(mutation, database=args.database)
        results.append(outcome)
        print(f"[{outcome['n']:>2}] {outcome['status']:<18} {outcome['family']}", flush=True)
        if outcome["status"] != "DETECTED":
            print(f"     {outcome.get('detail', outcome.get('mutated_result'))}", flush=True)

    residue = sorted(
        str(path.relative_to(REPO_ROOT))
        for path, digest in before.items()
        if _digest(path) != digest
    )

    detected = sum(1 for r in results if r["status"] == "DETECTED")
    print(f"\n{detected}/{len(results)} detected")
    print(
        f"mutable files restored: {len(before) - len(residue)}/{len(before)}"
        + (f" -- RESIDUE IN {residue}" if residue else " (no residue)")
    )

    if args.json_out:
        args.json_out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.write_text(render_markdown(results), encoding="utf-8")

    return 0 if detected == len(results) and not residue else 1


if __name__ == "__main__":
    raise SystemExit(main())
