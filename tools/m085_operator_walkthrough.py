"""MILESTONE-085 -- the operator walkthrough, run against an INSTALLED WHEEL.

    python tools/m085_operator_walkthrough.py

Everything here runs through console scripts from a wheel installed into a
throwaway virtualenv, never from the source tree. That is the point. A walkthrough
executed with `python -m` against `src/` proves the source works, which is not the
question an operator is asking. Packaging defects -- an unregistered entry point, a
module left out of the wheel, a dependency that only ever existed in the dev
environment -- are invisible from the source tree by construction.

EVERY STEP DECLARES ITS EXPECTED EXIT CODE BEFORE IT RUNS. A step that expects a
REFUSAL is as much a pass as one that expects success, and most of what is
valuable about this product is in the refusals. A step whose actual code differs
from its declared one is a failure even if the output looks reasonable.

WRITTEN IN PYTHON, AND WHY THAT MATTERS HERE. MILESTONE-084's equivalent is a bash
script that hardcodes `$VENV/bin/empirical-platform`, `sudo -u postgres` and
`.venv313/bin/python`. Those are POSIX- and layout-specific, which is the same
class of defect as FIND-F-02 and means it cannot run on this machine at all. This
one resolves the console-script directory from `sysconfig`, so it works wherever
the wheel installs.

THE DISPATCH-DEPENDENT STEPS MAY BE BLOCKED, AND SAY SO. If the market is closed
the only available IEX quote is hours old, the preview refuses on freshness, and
the steps that need an authorizable preview cannot run. They are then reported as
BLOCKED with the measured reason rather than skipped quietly, and the freshness
tolerance is NOT widened to manufacture a green run.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "external-review" / "MILESTONE-085"
EVIDENCE = PACKAGE / "operator-walkthrough.md"

SCRATCH = Path(os.environ.get("M085_WALKTHROUGH_DIR", REPO_ROOT.parent / "m085-walkthrough"))
VENV = SCRATCH / "venv"
WORK = SCRATCH / "work"
DATABASE = os.environ.get("M085_WALKTHROUGH_DATABASE", "m085_walkthrough")

#: A CURRENT instant, not a fixed demonstration date. The first run used
#: 2026-06-10 and the preview then refused on three grounds at once -- an expired
#: intent, a passed liquidation deadline and an over-limit cost ceiling -- which is
#: correct behaviour but buries the refusal that actually matters. With a current
#: instant the only refusal left is the real one.
AT = datetime.now(UTC).replace(microsecond=0).isoformat()
OBSERVED = (datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=5)).isoformat()


class PreparationError(RuntimeError):
    """Preparation failed. Abort rather than let every step fail downstream."""


@dataclass
class Step:
    number: int
    title: str
    expected: int | None
    command: list[str]
    actual: int | None = None
    output: str = ""
    note: str = ""
    status: str = "PENDING"


@dataclass
class Walkthrough:
    steps: list[Step] = field(default_factory=list)
    blocked_reason: str | None = None

    def run(self, title: str, expected: int, command: list[str], *, note: str = "") -> Step:
        step = Step(len(self.steps) + 1, title, expected, command, note=note)
        self.steps.append(step)
        if self.blocked_reason is not None:
            step.status = "BLOCKED"
            step.note = self.blocked_reason
            print(f"[{step.number:02d}] BLOCKED  {title}")
            return step
        print(f"[{step.number:02d}] expect {expected}  {title} ... ", end="", flush=True)
        process = subprocess.run(  # noqa: S603 - fixed vector, no shell
            command, cwd=SCRATCH, capture_output=True, text=True, check=False
        )
        step.actual = process.returncode
        step.output = (process.stdout + process.stderr)[-4000:]
        step.status = "PASS" if step.actual == expected else "FAIL"
        print(f"got {step.actual} -> {step.status}", flush=True)
        return step

    def block(self, reason: str) -> None:
        self.blocked_reason = reason
        print(f"\n*** REMAINING DISPATCH-DEPENDENT STEPS BLOCKED: {reason}\n", flush=True)


def script_directory(venv: Path) -> Path:
    """Where this platform installs console scripts. Not hardcoded to `bin`."""
    scheme = sysconfig.get_paths(scheme="venv" if "venv" in sysconfig.get_scheme_names() else None)
    suffix = Path(scheme["scripts"]).name if scheme.get("scripts") else "bin"
    for candidate in (venv / suffix, venv / "Scripts", venv / "bin"):
        if candidate.is_dir():
            return candidate
    raise PreparationError(f"no console-script directory under {venv}")


def configuration(*, leverage: str = "1", kill_switch: str = "DISENGAGED") -> dict[str, object]:
    """The demonstration POLICY. Widened where it is policy, never where it is a gate.

    The entry window, the minimum price, the spread tolerance and the per-trade
    capital are MILESTONE-084 operator policy: they bound what may be PROPOSED.
    They are set here so that one share of a $4.00 asset is proposable at any
    hour, which is what lets the walkthrough reach the M085 steps.

    None of the M085 execution safety gates is touched: leverage stays 1, short
    selling and overnight positions stay forbidden, the account mode stays
    PREPARATION, and the preview is still given a USD 5 ceiling and a 60-second
    quote-freshness tolerance on the command line.
    """
    return {
        "configuration_governance_id": "CFG-WALK85",
        "configuration_version": 1,
        "base_currency": "USD",
        "permitted_markets": ["XNAS"],
        "watchlist": ["AAPL", "MSFT"],
        "prohibited_instruments": ["PENNY"],
        "maximum_deployable_capital": "10000",
        "maximum_capital_per_trade": "5",
        "maximum_percent_per_trade": "20",
        "minimum_cash_reserve": "1000",
        "maximum_simultaneous_positions": 3,
        "maximum_daily_loss": "500",
        "maximum_daily_order_count": 10,
        "minimum_price": "1",
        "maximum_price": "1000",
        "minimum_liquidity_shares": 100000,
        "maximum_spread_percent": "5",
        "maximum_estimated_slippage_percent": "1",
        "maximum_evidence_age_seconds": 86400,
        "maximum_market_data_age_seconds": 60,
        "permitted_session": "REGULAR",
        "earliest_entry_time": "00:01:00",
        "latest_entry_time": "23:58:00",
        "mandatory_liquidation_time": "23:59:00",
        "operator_timezone": "UTC",
        "exchange_calendar_policy": "XNAS-REGULAR-2026",
        "proposal_expiry_seconds": 300,
        "approval_expiry_seconds": 120,
        "default_order_type": "LIMIT",
        "permitted_order_types": ["LIMIT", "MARKET"],
        "limit_price_policy": "ASK",
        "stop_loss_percent": "2",
        "profit_exit_percent": "4",
        "maximum_leverage": leverage,
        "short_selling_permitted": False,
        "overnight_positions_permitted": False,
        "account_mode": "PREPARATION",
        "kill_switch": kill_switch,
    }


def inputs(
    *, ask: str = "4.00", feed: str = "REAL_TIME", volume: int = 50_000_000, symbol: str = "AAPL"
) -> dict[str, object]:
    from decimal import Decimal

    return {
        "quote": {
            "quote_id": "QTE-WALK85",
            "provider_id": "OPERATOR-ASSERTED",
            "symbol": symbol,
            "bid": str(Decimal(ask) - Decimal("0.15")),
            "ask": ask,
            "last_trade": ask,
            "observed_at": OBSERVED,
            "feed_kind": feed,
        },
        "account": {
            "account_snapshot_id": "ACC-WALK85",
            "provider_id": "OPERATOR-ASSERTED",
            "account_reference": "PREP-1",
            "base_currency": "USD",
            "cash_available": "5000",
            "equity_total": "10000",
            "realized_pnl_today": "0",
            "orders_submitted_today": 0,
            "observed_at": OBSERVED,
        },
        "session": {
            "session_id": "SES-WALK85",
            "provider_id": "OPERATOR-ASSERTED",
            "market": "XNAS",
            "status": "OPEN",
            "observed_at": OBSERVED,
        },
        "instrument": {
            "symbol": symbol,
            "market": "XNAS",
            "currency": "USD",
            "is_fractionable": False,
            "lot_size": 1,
        },
        "liquidity": {
            "symbol": symbol,
            "average_daily_volume_shares": volume,
            "observed_at": OBSERVED,
        },
        "cost_estimate": {
            "estimate_id": "CST-WALK85",
            "provider_id": "OPERATOR-ASSERTED",
            "symbol": symbol,
            "commission": "1.00",
            "estimated_slippage_percent": "0.1",
            "observed_at": OBSERVED,
        },
        "positions": [],
        "open_orders": [],
        "evidence_age_seconds": "60",
    }


def prepare() -> Path:
    """Build, install, prove the wheel is what runs, and rebuild the database."""
    print("=== PREPARATION", flush=True)
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)

    wheels = sorted((REPO_ROOT / "dist").glob("*.whl"))
    if not wheels:
        raise PreparationError("no wheel in dist/; run `python -m build` first")
    wheel = wheels[-1]
    print(f"  wheel: {wheel.name}", flush=True)

    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "venv", str(VENV)], check=True, capture_output=True
    )
    scripts = script_directory(VENV)
    interpreter = scripts / ("python.exe" if os.name == "nt" else "python")
    subprocess.run(  # noqa: S603
        [str(interpreter), "-m", "pip", "install", "-q", f"{wheel}[persistence]"],
        check=True,
        capture_output=True,
    )
    proof = subprocess.run(  # noqa: S603
        [
            str(interpreter),
            "-c",
            "import empirical_platform, pathlib, sys\n"
            "location = pathlib.Path(empirical_platform.__file__).resolve()\n"
            "sys.exit('imported from the source tree: ' + str(location))"
            " if 'site-packages' not in str(location) else print(location.parent)",
        ],
        cwd=SCRATCH,
        capture_output=True,
        text=True,
        check=False,
    )
    if proof.returncode != 0:
        raise PreparationError(
            f"the wheel is not what is being exercised: {proof.stdout}{proof.stderr}"
        )
    print(f"  running from {proof.stdout.strip()}", flush=True)

    # A database rebuilt from nothing through the full migration history, so the
    # walkthrough DEMONSTRATES the clean-database mode rather than describing it.
    os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = DATABASE
    import sqlalchemy as sa
    from sqlalchemy import text

    from empirical_platform.shared.config.settings import resolve_foundation_config

    url = resolve_foundation_config().postgresql.sqlalchemy_url()
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    from alembic import command as alembic_command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    alembic_command.upgrade(cfg, "head")
    print("  migrations applied through the full history", flush=True)

    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) "
                "VALUES ('WM-WALK85')"
            )
        )
    engine.dispose()
    print("  M083 watermark inserted (a prerequisite M084 consumes)", flush=True)

    (WORK / "configuration.json").write_text(
        json.dumps(configuration(), indent=2), encoding="utf-8", newline="\n"
    )
    (WORK / "leveraged.json").write_text(
        json.dumps(configuration(leverage="2"), indent=2), encoding="utf-8", newline="\n"
    )
    for name, document in (
        ("inputs.json", inputs()),
        ("inputs-delayed.json", inputs(feed="DELAYED")),
        ("inputs-illiquid.json", inputs(volume=1000)),
        ("inputs-tsla.json", inputs(symbol="TSLA")),
    ):
        (WORK / name).write_text(json.dumps(document, indent=2), encoding="utf-8", newline="\n")
    (WORK / "context.json").write_text(
        json.dumps(
            {
                "evaluation_context_id": "ECX-WALK85",
                "configuration_governance_id": "CFG-WALK85",
                "configuration_version": 1,
                "watermark_governance_id": "WM-WALK85",
                "quote_id": "QTE-WALK85",
                "account_snapshot_id": "ACC-WALK85",
                "session_id": "SES-WALK85",
                "cost_estimate_id": "CST-WALK85",
                "instrument_universe_version": "UNIVERSE-2026-06",
                "strategy_version": "STRATEGY-0001",
                "created_at": AT,
            },
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return scripts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    try:
        scripts = prepare()
    except (PreparationError, subprocess.CalledProcessError) as error:
        print(f"PREPARATION FAILED: {error}", file=sys.stderr)
        return 2

    def cli(name: str) -> str:
        return str(scripts / f"empirical-platform-{name}")

    walk = Walkthrough()
    work = str(WORK)

    # ---- the operator's own path, in the order a human walks it -------------
    walk.run(
        "validate a policy file, touching no database",
        0,
        [cli("validate-trading-configuration"), f"{work}/configuration.json"],
    )
    walk.run(
        "a leveraged policy is refused before it can be stored",
        1,
        [cli("validate-trading-configuration"), f"{work}/leveraged.json"],
    )
    walk.run(
        "verify the paper environment is the pinned paper host",
        0,
        [cli("verify-paper-environment")],
    )
    walk.run(
        "read the paper account, read-only, and store one snapshot",
        0,
        [cli("inspect-paper-account"), "SNP-WALK85"],
    )
    walk.run(
        "store the policy as version 1",
        0,
        [cli("save-trading-configuration"), f"{work}/configuration.json"],
    )
    walk.run(
        "open an evaluation context, binding it to the M083 watermark",
        0,
        [cli("open-evaluation-context"), f"{work}/context.json"],
    )
    walk.run(
        "NO_TRADE 1 of 3 -- a feed that is not real time",
        0,
        [cli("explain-no-trade"), "ECX-WALK85", "AAPL", AT, f"{work}/inputs-delayed.json"],
    )
    walk.run(
        "NO_TRADE 2 of 3 -- liquidity below the configured floor",
        0,
        [cli("explain-no-trade"), "ECX-WALK85", "AAPL", AT, f"{work}/inputs-illiquid.json"],
    )
    walk.run(
        "NO_TRADE 3 of 3 -- an instrument off the watchlist",
        0,
        [cli("explain-no-trade"), "ECX-WALK85", "TSLA", AT, f"{work}/inputs-tsla.json"],
    )
    walk.run(
        "evaluate one instrument and derive a proposal",
        0,
        [
            cli("prepare-trade-proposal"),
            "PRP-WALK85",
            "ECX-WALK85",
            "AAPL",
            AT,
            f"{work}/inputs.json",
        ],
    )
    walk.run(
        "a human approves -- the one command no automation may run",
        0,
        [cli("decide-trade-proposal"), "PRP-WALK85", "DEC-WALK85", "APPROVE", "operator-1", AT],
    )
    walk.run(
        "derive the single order intent the approval permits",
        0,
        [cli("issue-order-intent"), "INT-WALK85", "PRP-WALK85", "IDEM-WALK85", AT],
    )
    walk.run("read the intent back -- NOT_SUBMITTED", 0, [cli("get-order-intent"), "INT-WALK85"])

    # ---- MILESTONE-085 -----------------------------------------------------
    walk.run(
        "the paper execution status of an untouched intent",
        0,
        [cli("paper-execution-status"), "INT-WALK85"],
        note="NOT_DISPATCHED, derived from the absence of an attempt",
    )
    walk.run(
        "dispatch WITHOUT any authorization is refused",
        1,
        [
            cli("submit-authorized-paper-order"),
            "INT-WALK85",
            "ATT-WALK85",
            "SNP-WALK85-2",
            "5",
            "60",
            "AAPL",
        ],
    )
    preview = walk.run(
        "freeze the submission preview against real broker evidence",
        0,
        [
            cli("preview-paper-submission"),
            "INT-WALK85",
            "PVW-WALK85",
            "SNP-WALK85-3",
            "5",
            "60",
            "AAPL",
        ],
    )
    walk.run(
        "authorizing with a WRONG fingerprint is refused",
        1,
        [cli("authorize-paper-submission"), "AUT-WALK85", "PVW-WALK85", "0" * 64, "owner", "300"],
    )

    fingerprint: str | None = None
    authorizable = False
    if preview.status == "PASS":
        for line in preview.output.splitlines():
            if line.startswith("REQUEST FINGERPRINT"):
                fingerprint = line.split(":", 1)[1].strip()
        authorizable = "AUTHORIZABLE." in preview.output
    if not authorizable:
        refusals = [
            line.strip(" -")
            for line in preview.output.splitlines()
            if line.strip().startswith("- ")
        ]
        walk.block(
            "the preview refuses authorization on real broker evidence: " + "; ".join(refusals[:3])
        )

    walk.run(
        "a human authorizes that exact fingerprint",
        0,
        [
            cli("authorize-paper-submission"),
            "AUT-WALK85",
            "PVW-WALK85",
            fingerprint or "0" * 64,
            "owner",
            "300",
        ],
    )
    walk.run(
        "dispatch the one authorized order",
        0,
        [
            cli("submit-authorized-paper-order"),
            "INT-WALK85",
            "ATT-WALK85",
            "SNP-WALK85-4",
            "5",
            "60",
            "AAPL",
        ],
    )
    walk.run(
        "reconcile using the same client order id", 0, [cli("reconcile-paper-order"), "INT-WALK85"]
    )
    walk.run("cancel the acknowledged order", 0, [cli("cancel-paper-order"), "INT-WALK85"])
    walk.run(
        "reconcile again, to a terminal state", 0, [cli("reconcile-paper-order"), "INT-WALK85"]
    )

    # ---- these run whether or not a dispatch happened ----------------------
    walk.blocked_reason = None
    walk.run(
        "the complete audit history behind this intent",
        0,
        [cli("show-paper-execution"), "INT-WALK85"],
    )
    walk.run("the paper dispatch queue", 0, [cli("list-paper-executions")])
    walk.run(
        "engage the execution kill switch",
        0,
        [cli("activate-execution-kill-switch"), "owner", "walkthrough demonstration"],
    )
    walk.run(
        "dispatch is refused while the kill switch is engaged",
        1,
        [
            cli("submit-authorized-paper-order"),
            "INT-WALK85",
            "ATT-WALK85-2",
            "SNP-WALK85-5",
            "5",
            "60",
            "AAPL",
        ],
    )
    walk.run(
        "engaging an already-engaged switch writes nothing",
        0,
        [cli("activate-execution-kill-switch"), "owner", "again"],
    )
    walk.run(
        "lift the execution kill switch",
        0,
        [cli("deactivate-execution-kill-switch"), "owner", "walkthrough complete"],
    )
    walk.run(
        "after a fresh process, the state still comes from the database",
        0,
        [cli("paper-execution-status"), "INT-WALK85"],
        note="a new process, so nothing is carried in memory",
    )
    walk.run(
        "an unknown intent is a refusal, not a traceback",
        1,
        [cli("show-paper-execution"), "NO-SUCH-INTENT"],
    )

    failures = [step for step in walk.steps if step.status == "FAIL"]
    blocked = [step for step in walk.steps if step.status == "BLOCKED"]

    lines = [
        "# MILESTONE-085 — Installed-Wheel Operator Walkthrough",
        "",
        f"Run at `{datetime.now(UTC).isoformat()}` (UTC) against a wheel installed into a",
        "throwaway virtualenv **outside the source tree**. Every command below is an installed",
        "console script; none is `python -m` against `src/`.",
        "",
        f"**{len(walk.steps)} steps. {len(failures)} off their declared exit code. "
        f"{len(blocked)} blocked.**",
        "",
        "Each step declared its expected exit code BEFORE it ran. A step expecting a refusal is",
        "as much a pass as one expecting success.",
        "",
        "| # | Step | Expected | Actual | Status |",
        "|---|---|---|---|---|",
    ]
    for step in walk.steps:
        actual = "-" if step.actual is None else str(step.actual)
        lines.append(
            f"| {step.number:02d} | {step.title} | `{step.expected}` | `{actual}` | "
            f"**{step.status}** |"
        )
    lines.append("")
    if blocked:
        lines.extend(
            [
                "## Blocked steps",
                "",
                f"**Reason:** {blocked[0].note}",
                "",
                "These steps need an authorizable preview, which needs a fresh quote. The",
                "freshness tolerance was NOT widened to manufacture one -- that is the control",
                "this milestone exists to demonstrate, and weakening it to produce a green",
                "walkthrough would make the walkthrough worthless. See",
                "`paper-acceptance-results.md` for the measured numbers.",
                "",
            ]
        )
    if failures:
        lines.extend(["## Steps off their declared exit code", ""])
        for step in failures:
            lines.append(f"### {step.number:02d} — {step.title}")
            lines.append("")
            lines.append(f"Expected `{step.expected}`, got `{step.actual}`.")
            lines.append("")
            lines.append("```")
            lines.append(step.output[-1500:])
            lines.append("```")
            lines.append("")

    PACKAGE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote {EVIDENCE.relative_to(REPO_ROOT)}")
    print(f"{len(walk.steps)} steps, {len(failures)} off expectation, {len(blocked)} blocked")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
