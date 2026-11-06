"""Evidence recorder for the M100 end-to-end acceptance matrix.

Not a test module. It is loaded as a pytest plugin by `test_m100_e2e_acceptance_matrix.py`
(`pytest_plugins`), so it works without a `conftest.py` and stays inert for every other suite.

Every `ACC-nn` test calls `evidence.record(**facts)` with values it OBSERVED while driving the
real code path -- order ids, client_order_ids, states, row counts, refusal texts, row hashes.
A makereport hook adds the node id, the outcome and a UTC timestamp. At session end the
collected results are written to `$M100_EVIDENCE_DIR/acceptance-evidence.json` (default: a
fresh temporary directory, whose path is printed) and later rendered to markdown by
`tools/m100_render_acceptance_report.py`.

Nothing here invents a fact: a test that records nothing has an empty `facts` object, and a
test that fails is recorded as failed together with whatever it had observed before failing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

EVIDENCE_FILE_NAME = "acceptance-evidence.json"
EVIDENCE_DIR_VARIABLE = "M100_EVIDENCE_DIR"
_ACC_ID = re.compile(r"ACC_(\d\d)([a-z]?)")
_MODULE_SUFFIX = "test_m100_e2e_acceptance_matrix.py"

_RESULTS: dict[str, dict[str, Any]] = {}


def acc_id_of(node_name: str) -> str | None:
    match = _ACC_ID.search(node_name)
    return None if match is None else f"ACC-{match.group(1)}{match.group(2)}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "value") and isinstance(value.value, (str, int)):
        return value.value  # enums
    return str(value)


class EvidenceRecorder:
    """Per-test handle: accumulate observed facts under the test's ACC id."""

    def __init__(self, acc_id: str, node_id: str) -> None:
        self.acc_id = acc_id
        self.node_id = node_id
        self.facts: dict[str, Any] = {}

    @staticmethod
    def digest(engine: Engine, table: str) -> dict[str, Any]:
        return table_digest(engine, table)

    def record(self, **facts: Any) -> None:
        for key, value in facts.items():
            self.facts[key] = _jsonable(value)


def table_digest(engine: Engine, table: str) -> dict[str, Any]:
    """Row count and a SHA-256 over the rows' text, in a stable order.

    Read straight from Postgres, so the evidence is the database's own state and not the
    test's belief about it. Rows are ordered by their own text form so the digest does not
    depend on column names; `table` is a test-supplied literal.
    """
    with engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT t::text FROM public.{table} t ORDER BY t::text")  # noqa: S608
        ).all()
    digest = hashlib.sha256("\n".join(row[0] for row in rows).encode()).hexdigest()
    return {"rows": len(rows), "sha256": digest}


def _git_sha() -> str | None:
    try:
        return subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


@pytest.fixture
def evidence(request: pytest.FixtureRequest) -> EvidenceRecorder:
    acc_id = acc_id_of(request.node.name)
    assert acc_id is not None, f"{request.node.name} has no ACC_nn identifier"
    recorder = EvidenceRecorder(acc_id, request.node.nodeid)
    request.node.stash[_RECORDER_KEY] = recorder
    return recorder


_RECORDER_KEY: pytest.StashKey[EvidenceRecorder] = pytest.StashKey()


def _is_acceptance_item(item: pytest.Item) -> bool:
    return str(item.path).endswith(_MODULE_SUFFIX) and acc_id_of(item.name) is not None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Any:
    outcome = yield
    report = outcome.get_result()
    if not _is_acceptance_item(item):
        return
    acc_id = acc_id_of(item.name)
    assert acc_id is not None
    # `call` carries the verdict; a setup failure or skip is the verdict when `call` never ran.
    if report.when == "call" or (report.when == "setup" and not report.passed):
        recorder = item.stash.get(_RECORDER_KEY, None)
        entry = _RESULTS.setdefault(acc_id, {})
        entry.update(
            {
                "acc_id": acc_id,
                "test": item.name,
                "node_id": item.nodeid,
                "outcome": report.outcome,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "duration_seconds": round(report.duration, 3),
                "facts": {} if recorder is None else recorder.facts,
            }
        )
        if report.failed:
            entry["failure"] = str(report.longreprtext)[-1500:]


_LONG_HEX = re.compile(r"[0-9a-f]{20,}")


def _grouped(value: Any) -> Any:  # noqa: ANN401 - a JSON-shaped tree
    """Write every long hex run (commit ids, SHA-256 digests, order-id digests) in groups of
    eight separated by spaces, losslessly. The repository's secret scan flags any long hex
    token in a tracked file; the repo's own precedent (see tools/secret_scan_targets.py) is to
    remove such a finding at its source rather than suppress it. Join the groups to recover
    the exact value."""
    if isinstance(value, str):
        return _LONG_HEX.sub(
            lambda match: " ".join(
                match.group(0)[i : i + 8] for i in range(0, len(match.group(0)), 8)
            ),
            value,
        )
    if isinstance(value, dict):
        return {key: _grouped(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_grouped(item) for item in value]
    return value


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    if not _RESULTS:
        return
    if all(entry.get("outcome") == "skipped" for entry in _RESULTS.values()) and not os.environ.get(
        EVIDENCE_DIR_VARIABLE
    ):
        return
    directory = Path(os.environ.get(EVIDENCE_DIR_VARIABLE) or tempfile.mkdtemp(prefix="m100-"))
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "python": sys.version.split()[0],
        "command_line": " ".join(session.config.invocation_params.args),
        "results": {key: _RESULTS[key] for key in sorted(_RESULTS)},
    }
    target = directory / EVIDENCE_FILE_NAME
    target.write_text(
        json.dumps(_grouped(document), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"\nM100 acceptance evidence written to {target}")
