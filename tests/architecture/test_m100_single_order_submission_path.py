"""M100 final audit: the ONLY call site of a broker `submit_order` is the guarded dispatch.

Every entry-limit rule (daily loss / order count / position count / exposure, kill switch,
authorization) is enforced by `SubmitAuthorizedPaperOrderHandler` inside `before_send`. A second
caller of `.submit_order(` anywhere in the shipped code would be a way around those limits, so a
new one must fail this test and be reviewed by a human instead of slipping in.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALLOWED = {"src/empirical_platform/usecases/paper_execution.py"}
SEARCH_ROOTS = ("src", "tools", "scripts", "deploy")


def _call_sites() -> dict[str, list[str]]:
    sites: dict[str, list[str]] = {}
    for root in SEARCH_ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ps1", ".sh"} or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            hits = [
                f"{number}: {line.strip()}"
                for number, line in enumerate(text.splitlines(), start=1)
                if re.search(r"\.submit_order\(", line) and not line.lstrip().startswith("#")
            ]
            if hits:
                sites[path.relative_to(REPO).as_posix()] = hits
    return sites


def test_only_the_guarded_dispatch_calls_submit_order() -> None:
    assert set(_call_sites()) == ALLOWED, _call_sites()


def test_the_guarded_dispatch_always_passes_before_send() -> None:
    text = (REPO / "src/empirical_platform/usecases/paper_execution.py").read_text(encoding="utf-8")
    calls = [line for line in text.splitlines() if ".submit_order(" in line]
    assert calls and all("before_send=before_send" in line for line in calls), calls


def test_exit_orders_can_only_be_sells() -> None:
    text = (REPO / "src/empirical_platform/decision_candidate/position_exit.py").read_text(
        encoding="utf-8"
    )
    # The exit request's broker side is a literal; the client sends exactly that value.
    match = re.search(
        r"def broker_side\(self\) -> str:\s+(?:\"\"\"[^\"]*\"\"\"\s+)?return \"sell\"", text
    )
    assert match, "PositionExitRequest.broker_side must be the literal 'sell'"
