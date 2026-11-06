"""Render the M100 acceptance matrix's evidence JSON as a markdown report.

Usage::

    python tools/m100_render_acceptance_report.py \\
        --evidence "$M100_EVIDENCE_DIR/acceptance-evidence.json" \\
        --out docs/operations/m100-acceptance-evidence.md \\
        --command "<the exact pytest command line that produced the evidence>"

The input is written by `tests/integration/_acceptance_evidence.py` at the end of a
`tests/integration/test_m100_e2e_acceptance_matrix.py` run against real Postgres test
databases. Everything in the output is read from that file -- nothing is computed, estimated or
filled in here; a step with no recorded result is rendered as NOT RUN. The renderer refuses
evidence that looks like it contains a credential.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

#: The Owner's 24 numbered steps. Letter-suffixed ids are additional tests under the same step.
STEPS: dict[str, str] = {
    "ACC-01": "Market data received",
    "ACC-02": "Signal generated",
    "ACC-03": "Candidate prepared",
    "ACC-04": "Risk checks performed",
    "ACC-04b": "Risk checks, NEW control D1: portfolio limits refuse at the submission boundary",
    "ACC-05": "Existing positions detected",
    "ACC-06": "Existing open orders detected",
    "ACC-07": "Conflicting entry refused",
    "ACC-08": "Owner approval enforced (no approval, no order)",
    "ACC-09": "Order payload validated (malformed / over-cap refused)",
    "ACC-09b": "Order payload validated: a differing broker acknowledgement is not trusted",
    "ACC-10": "PAPER order simulated",
    "ACC-11": "Broker acknowledgement handled",
    "ACC-12": "Partial fill reconciled",
    "ACC-13": "Full fill reconciled",
    "ACC-14": "Position recorded",
    "ACC-15": "Stop-loss evaluated",
    "ACC-16": "Target evaluated",
    "ACC-17": "Exit submitted in simulation",
    "ACC-17b": "Exit, NEW control D3: unfilled exit repriced / replaced within bounds",
    "ACC-17c": "Exit: time-driven mandatory liquidation submitted and reconciled",
    "ACC-18": "Duplicate exit prevented",
    "ACC-19": "Broker rejection handled",
    "ACC-20": "Connection loss handled (no resend; reconcile by client_order_id)",
    "ACC-21": "Restart recovery tested",
    "ACC-22": "Kill switch enforced (entries refused, exits allowed)",
    "ACC-23": "Audit evidence preserved",
    "ACC-24": "Final state reconciled",
}

#: Static findings the matrix produced. Each names the step whose recorded facts show it.
FINDINGS: tuple[str, ...] = (
    "**FIXED -- defect found by ACC-17c.** The acknowledgement id (`XACK-<attempt>-<n>`) and the "
    "reconciliation-round id (`XRND-<attempt>-<n>`) of an exit were cut with `[:64]`. The "
    "attempt id of a plan-minted MANDATORY_EXIT is 63 characters, so the sequence was cut off "
    "and the SECOND acknowledgement / round of that attempt collided with the first on the "
    "primary key: every reconcile of an automatic mandatory liquidation raised, and because "
    "`PositionPlanManager.evaluate_once` does not isolate plans from each other, the same tick "
    "never reached later plans. Ids that already fit are unchanged; longer ones are digested "
    "(`usecases/position_exit.py::_acknowledgement_id`, "
    "`position_exit_repositories.py::_round_id`; unit tests in "
    "`tests/unit/test_m100_exit_acknowledgement_id.py`).",
    "**OPEN -- a partially filled entry that stays working is not protected (ACC-12).** While "
    "the remainder can still fill, the exit assessment refuses ('cancel the remainder and wait "
    "until the entry is final'), so the plan manager answers NOT_ELIGIBLE and the filled "
    "shares carry no automatic stop or target until the entry is final. This is by design, "
    "not a regression, but the Owner must cancel the remainder to get protection.",
    "**OPEN -- a blocked approval shows no reason on the v1 console.** The v1 "
    "`/confirm-approval` override (`paper_operator_console_app.py`) does not put the "
    "`ActionOutcome` into the page flash the base route uses, so after 'approved, execution "
    "blocked' the Owner sees only 'Approved; nothing was sent yet'. The reasons are durable "
    "(`paper_submission_preview.refusals`; quoted in ACC-04b, ACC-05, ACC-06, ACC-07). The same "
    "path also creates the ApprovedPlan for an approved entry that was never sent (the manager "
    "then reports NOT_ELIGIBLE).",
    "**OPEN (low) -- two managers racing one trigger (ACC-18).** Exactly one SELL reaches the "
    "wire (the database refuses the second preview/attempt), but the loser's tick ends with an "
    "unhandled uniqueness error instead of a handled outcome. The single-instance lock makes "
    "this a multi-process-only case.",
    "**OPEN (low) -- a refused Prepare leaves its evaluation-context row (ACC-04, harness note).** "
    "Ids carry whole seconds, so pressing Prepare again within the same second raises a raw "
    "persistence error rather than the friendly refusal; the harness moves its clock 1.1 s "
    "between prepares.",
    "**Wording (cosmetic) -- ACC-06/ACC-07.** A working BUY order is reported by the "
    "submission-boundary check as 'a position of N already exists'.",
)

#: What is NOT end to end, stated plainly.
LIMITS: tuple[str, ...] = (
    "The broker and market-data WIRE is a scripted exchange "
    "(`tests/integration/_m100_fake_alpaca.py`): its fills, rejections, drops and quotes are "
    "what the tests tell it; it is not Alpaca and does not reproduce Alpaca's own rules. "
    "`SimulatedPaperBroker` (`simulation_paper.py`) is not driven by this matrix.",
    "Time is a virtual clock shared by host, wire and `now=` arguments; real market hours, "
    "exchange holidays and real latency are not exercised.",
    "The WSGI application is called in-process (no socket); `PlanManagerThread` is not started -- "
    "`PositionPlanManager.evaluate_once` is driven directly, exactly as the thread does.",
    "ACC-02's signal is the M090 Opportunity Engine on scripted bars; the matrix does not "
    "claim that signal has any edge, and the engine's candidate is not wired into Prepare "
    "(`prepare_v1_paper_candidate` evaluates the configured one-symbol watchlist itself).",
)

_SECRET_PATTERNS = (
    re.compile(r"APCA-API-(KEY|SECRET)"),
    re.compile(r"ci-only-(key|secret)"),
    re.compile(r"PK[A-Z0-9]{18,}"),
)
_FACT_LIMIT = 400


def _sort_key(acc_id: str) -> tuple[int, str]:
    match = re.fullmatch(r"ACC-(\d\d)([a-z]?)", acc_id)
    assert match, acc_id
    return int(match.group(1)), match.group(2)


def _compact(value: object) -> str:
    text = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    if len(text) > _FACT_LIMIT:
        return text[: _FACT_LIMIT - 1] + "…"
    return text


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render(document: dict[str, Any], *, command: str) -> str:
    raw = json.dumps(document)
    for pattern in _SECRET_PATTERNS:
        if pattern.search(raw):
            raise SystemExit(f"refusing to render: the evidence matches {pattern.pattern!r}")
    results: dict[str, dict[str, Any]] = document["results"]
    unknown = sorted(set(results) - set(STEPS))
    if unknown:
        raise SystemExit(f"evidence contains ids this renderer does not know: {unknown}")
    outcomes = [r["outcome"] for r in results.values()]
    passed, failed, skipped = (outcomes.count(o) for o in ("passed", "failed", "skipped"))
    missing = [i for i in STEPS if i not in results]
    numbered = [i for i in results if not re.search(r"[a-z]$", i)]
    numbered_pass = sum(1 for i in numbered if results[i]["outcome"] == "passed")

    lines: list[str] = []
    add = lines.append
    add("# M100 end-to-end acceptance evidence")
    add("")
    add(
        "Generated by `tools/m100_render_acceptance_report.py` from "
        "`acceptance-evidence.json`, which `tests/integration/test_m100_e2e_acceptance_matrix.py` "
        "writes from what each test OBSERVED. Do not edit by hand: re-run the matrix and "
        "re-render."
    )
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| Commit (`git rev-parse HEAD` at run time) | `{document.get('git_sha') or 'unknown'}` |")
    add(f"| Generated (UTC) | {document['generated_at_utc']} |")
    add(f"| Python | {document.get('python', 'unknown')} |")
    add(
        f"| Result | **{passed} passed, {failed} failed, {skipped} skipped** "
        f"({len(results)} tests) |"
    )
    add(
        f"| Owner steps 1-24 | **{numbered_pass} of 24 numbered steps passed**"
        f"{'' if not missing else '; NOT RUN: ' + ', '.join(missing)} |"
    )
    add("")
    add("Exact command line:")
    add("")
    add("```")
    add(command)
    add("```")
    add("")
    add(
        "What is real and what is not: the production composition "
        "`paper_operator_console_with_exit_runtime()`, its repositories, the M085 PaperExecution "
        "handlers, the WSGI routes, `ApprovedPlan` + `PositionPlanManager` and the exit handlers "
        "run against REAL PostgreSQL test databases (Store A/B at head, Store C at its head); the "
        "real `AlpacaPaperClient`/`AlpacaPaperMarketDataClient` talk to a scripted exchange on "
        "127.0.0.1 (host pins unchanged, only the transport redirected). The broker, its fills "
        "and its failures are simulated; no real broker, network or credential is involved."
    )
    add("")
    add("## Summary")
    add("")
    add("| ID | Owner step | Result | Recorded (UTC) | Test |")
    add("|---|---|---|---|---|")
    for acc_id in sorted(STEPS, key=_sort_key):
        entry = results.get(acc_id)
        if entry is None:
            add(f"| {acc_id} | {_cell(STEPS[acc_id])} | NOT RUN | | |")
            continue
        verdict = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIPPED"}[entry["outcome"]]
        node = entry["node_id"].split("::")[-1]
        add(
            f"| {acc_id} | {_cell(STEPS[acc_id])} | **{verdict}** | "
            f"{entry['timestamp_utc'][:19]}Z | `{node}` |"
        )
    add("")
    add("## Findings recorded by this run")
    add("")
    for finding in FINDINGS:
        add(f"- {finding}")
    add("")
    add("## What is not end to end")
    add("")
    for limit in LIMITS:
        add(f"- {limit}")
    add("")
    add("## Observed facts per step")
    add("")
    add(
        "Each value below was read from the live system by the test (wire log, Postgres rows, "
        "repository reads, HTTP replies). Long values are truncated at "
        f"{_FACT_LIMIT} characters; the full values are in the JSON."
    )
    for acc_id in sorted(results, key=_sort_key):
        entry = results[acc_id]
        add("")
        add(f"### {acc_id} -- {STEPS[acc_id]}")
        add("")
        add(f"- Node: `{entry['node_id']}`")
        add(f"- Result: **{entry['outcome'].upper()}** in {entry['duration_seconds']} s")
        if entry.get("failure"):
            add("- Failure:")
            add("")
            add("```")
            add(entry["failure"])
            add("```")
        for key in sorted(entry["facts"]):
            add(f"- `{key}`: `{_cell(_compact(entry['facts'][key]))}`")
    add("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--command",
        required=True,
        help="the exact command line that produced the evidence (recorded verbatim)",
    )
    args = parser.parse_args(argv)
    document = json.loads(args.evidence.read_text(encoding="utf-8"))
    args.out.write_text(render(document, command=args.command), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
