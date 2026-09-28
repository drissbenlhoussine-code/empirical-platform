"""L1 against real PostgreSQL and a REAL process death: no lineage before the send-capable boundary.

A child process (`tests/integration/_m085_crash_child.py`) runs the production submit handler
over the shared disposable database and terminates with `os._exit` -- no unwinding, no
`finally` -- at the boundary each scenario names. The parent then reconnects through a FRESH
persistence service, reads what the database actually holds, and reconciles as the restarted
process would, with the broker fake still holding the order the scenario describes.

  A  a historical order exists under our derived identity; death DURING the pre-send lookup;
  B  the lookup FOUND the historical order; death before the observation was persisted;
  C  positive control: our POST left; death before the acknowledgement was persisted;
     legitimate recovery attributes OUR order and never resends.

Invariant: without a persisted record that THIS attempt reached the send-capable boundary,
an order found under the identity is observed and never attributed, whatever the broker holds
and however plausible the match. The historical order stays visible; nothing is sent,
cancelled or liquidated to resolve it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.engine import Engine
from tests.integration._m085_support import REPO_ROOT, build_engine, truncate_all
from tests.integration.test_m085_identity_collision_postgres import (
    _authorized_order_as_the_broker_reports_it,
    _Broker,
    _MarketData,
    _Process,
)
from tests.integration.test_m085_temporal_postgres import Clock

from empirical_platform.decision_candidate.paper_execution import (
    PaperExecutionState,
    attempt_may_have_transmitted,
)

pytestmark = pytest.mark.integration

_DEATH = 3  # `_m085_crash_child.DEATH_EXIT_CODE`


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


@pytest.fixture
def world(engine: Engine, tmp_path: Path) -> Iterator[dict[str, Any]]:
    truncate_all(engine)
    clock = Clock()
    broker = _Broker(clock)
    data = _MarketData(clock)
    processes: list[_Process] = []

    def spawn(name: str) -> _Process:
        process = _Process(name, clock, broker, data)
        processes.append(process)
        return process

    try:
        yield {"clock": clock, "broker": broker, "spawn": spawn, "out": tmp_path}
    finally:
        for process in processes:
            process.close()


def _run_child(
    scenario: str, intent_id: str, attempt_id: str, out: Path
) -> subprocess.CompletedProcess[str]:
    # The command is this repository's own test module with test-generated identifiers.
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-B",
            "-m",
            "tests.integration._m085_crash_child",
            scenario,
            intent_id,
            attempt_id,
            str(out),
        ],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _died(result: subprocess.CompletedProcess[str], out: Path, where: str) -> None:
    assert result.returncode == _DEATH, (
        result.returncode,
        result.stdout[-2000:],
        result.stderr[-4000:],
    )
    assert (out / "died-at.txt").read_text(encoding="utf-8") == where


def _restart(world: dict[str, Any], name: str, intent_id: str) -> tuple[_Process, Any]:
    """A new process over the same database; the attempt as the database holds it."""
    process = world["spawn"](name)
    stored = process.paper.execution_attempts.for_intent(intent_id)
    assert stored is not None
    return process, stored


def test_a_death_during_the_pre_send_lookup_never_lends_lineage_to_a_historical_order(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="A")
    a.close()

    result = _run_child("A", intent_id, "ATT-CRASH-A", world["out"])
    _died(result, world["out"], "during-pre-send-identity-lookup")
    assert (world["out"] / "lookup-asked.txt").read_text() == authorization.client_order_id

    b, stored = _restart(world, "b", intent_id)
    assert stored.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert stored.failure_code is None and stored.broker_order_id is None
    # The broker holds the historical order with the authorized terms.
    world["broker"].lookup_view = _authorized_order_as_the_broker_reports_it(
        authorization, broker_order_id="broker-historical", status="filled"
    )
    world["clock"].advance(61)
    recovered = b.reconcile(intent_id)
    assert recovered.broker_order_id is None, (
        f"the historical order was attributed: state={recovered.state.value} "
        f"broker_order_id={recovered.broker_order_id} events={b.events(intent_id)}"
    )
    assert recovered.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in b.events(intent_id)
    assert "RECONCILED" not in b.events(intent_id)
    events = b.paper.paper_execution_events.for_intent(intent_id)
    assert not attempt_may_have_transmitted(stored, events), (
        "a record that died inside the lookup must not count as lineage"
    )
    assert world["broker"].submitted == [] and world["broker"].cancelled == []
    # Still visible and unresolved on the next look; a fresh dispatch sends nothing.
    world["clock"].advance(120)
    assert b.reconcile(intent_id).broker_order_id is None
    assert b.submit(intent_id, attempt_id="ATT-CRASH-A2").dispatched is False
    assert world["broker"].submitted == []


def test_a_death_after_discovery_before_persistence_never_lends_lineage(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="B")
    a.close()

    result = _run_child("B", intent_id, "ATT-CRASH-B", world["out"])
    _died(result, world["out"], "after-discovery-before-persistence")

    b, stored = _restart(world, "b", intent_id)
    assert stored.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert b.paper.broker_acknowledgements.for_attempt(stored.attempt_id) == ()
    assert "IDENTITY_OBSERVED_BEFORE_SEND" not in b.events(intent_id)
    world["broker"].lookup_view = _authorized_order_as_the_broker_reports_it(
        authorization, broker_order_id="broker-historical", status="filled"
    )
    world["clock"].advance(61)
    recovered = b.reconcile(intent_id)
    assert recovered.broker_order_id is None, (
        f"the historical order was attributed: state={recovered.state.value} "
        f"broker_order_id={recovered.broker_order_id} events={b.events(intent_id)}"
    )
    assert recovered.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in b.events(intent_id)
    assert world["broker"].submitted == [] and world["broker"].cancelled == []


def test_our_own_post_then_death_is_recovered_without_resending(world: dict[str, Any]) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="C")
    a.close()

    result = _run_child("C", intent_id, "ATT-CRASH-C", world["out"])
    _died(result, world["out"], "after-post-before-acknowledgement")
    sent = json.loads((world["out"] / "submitted.json").read_text(encoding="utf-8"))
    assert sent == {"client_order_id": authorization.client_order_id, "post_count": 1}

    b, stored = _restart(world, "b", intent_id)
    assert stored.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    events = b.paper.paper_execution_events.for_intent(intent_id)
    assert attempt_may_have_transmitted(stored, events) is True
    # The broker holds exactly the order the child sent.
    world["broker"].lookup_view = _authorized_order_as_the_broker_reports_it(
        authorization, broker_order_id="broker-child-1", status="accepted"
    )
    world["clock"].advance(61)
    recovered = b.reconcile(intent_id)
    assert recovered.broker_order_id == "broker-child-1"
    assert recovered.state is PaperExecutionState.PAPER_ACCEPTED
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" not in b.events(intent_id)
    # Never resent: the parent's fake received nothing, and a new dispatch is refused.
    assert world["broker"].submitted == []
    assert b.submit(intent_id, attempt_id="ATT-CRASH-C2").dispatched is False
    assert world["broker"].submitted == []
