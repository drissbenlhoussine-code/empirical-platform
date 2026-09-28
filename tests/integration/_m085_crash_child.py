"""The CHILD process of the L1 crash reproduction: dispatch, then die abruptly at one boundary.

Run by `tests/integration/test_m085_pre_send_crash_postgres.py` as
`python -m tests.integration._m085_crash_child <scenario> <intent_id> <attempt_id> <out_dir>`.
The child opens its own persistence service over the shared disposable database, builds the
production submit handler over a CONTROLLED broker fake, and terminates with `os._exit(3)` --
no exception handling, no `finally`, no flush -- at the boundary the scenario names:

  A  during the pre-send identity lookup (a historical order exists at the broker);
  B  after the lookup FOUND the historical order, before the observation is persisted;
  C  positive control: our POST left, before the acknowledgement is persisted.

The parent reads the durable rows afterwards through a fresh service. Nothing here talks to
Alpaca; the broker is the same fake the identity-collision suite uses.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from tests.integration._m085_support import config
from tests.integration.test_m085_identity_collision_postgres import (
    _authorized_order_as_the_broker_reports_it,
    _Broker,
    _MarketData,
)
from tests.integration.test_m085_temporal_postgres import Clock

from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresPaperExecutionRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.paper_execution import (
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)

DEATH_EXIT_CODE = 3


class _DiesOnAppend:
    """The real acknowledgement repository, except that the process dies at the first `append`.

    The PostgreSQL repositories use `__slots__`, so the boundary is placed by delegation rather
    than by patching an instance attribute. Every other call reaches the real repository.
    """

    def __init__(self, repository: object, die: object) -> None:
        self._repository = repository
        self._die = die

    def append(self, acknowledgement: object) -> object:
        self._die()  # type: ignore[operator]
        raise AssertionError("unreachable")

    def __getattr__(self, name: str) -> object:
        return getattr(self._repository, name)


def main(argv: list[str]) -> int:
    scenario, intent_id, attempt_id, out_dir = argv
    out = Path(out_dir)
    clock = Clock()
    broker = _Broker(clock)
    data = _MarketData(clock)
    service = PostgresPersistenceService(config(f"m085-crash-child-{scenario}"))
    service.initialize()
    m084 = PostgresRepositoryRuntime(service)
    paper = PostgresPaperExecutionRuntime(service)
    # One repository object each, so a patched method is the one the handler calls.
    attempts = paper.execution_attempts
    acknowledgements: object = paper.broker_acknowledgements
    events = paper.paper_execution_events
    authorization = paper.execution_authorizations.latest_for_intent(intent_id)
    assert authorization is not None

    def die(where: str) -> None:
        (out / "died-at.txt").write_text(where, encoding="utf-8")
        os._exit(DEATH_EXIT_CODE)  # abrupt: no unwinding, no further writes

    if scenario == "A":

        def lookup_then_die(client_order_id: str) -> tuple[int, object | None, str]:
            (out / "lookup-asked.txt").write_text(client_order_id, encoding="utf-8")
            die("during-pre-send-identity-lookup")
            raise AssertionError("unreachable")

        broker.fetch_order_by_client_order_id = lookup_then_die  # type: ignore[method-assign]
    elif scenario == "B":
        broker.lookup_view = _authorized_order_as_the_broker_reports_it(
            authorization, broker_order_id="broker-historical", status="filled"
        )
        acknowledgements = _DiesOnAppend(
            acknowledgements, lambda: die("after-discovery-before-persistence")
        )
    elif scenario == "C":
        original_submit = broker.submit_order

        def submit_and_record(order: object, *, before_send: object = None) -> object:
            result = original_submit(order, before_send=before_send)  # type: ignore[arg-type]
            (out / "submitted.json").write_text(
                json.dumps(
                    {
                        "client_order_id": getattr(order, "client_order_id", None),
                        "post_count": len(broker.submitted),
                    }
                ),
                encoding="utf-8",
            )
            return result

        broker.submit_order = submit_and_record  # type: ignore[method-assign]
        acknowledgements = _DiesOnAppend(
            acknowledgements, lambda: die("after-post-before-acknowledgement")
        )
    elif scenario == "R":
        # Q-2: a RECONCILIATION round that dies inside its lookup, AFTER the round was begun
        # durably. The parent must find the STARTED round and nothing else for it.
        from empirical_platform.usecases.paper_execution import (
            ReconcilePaperOrderCommand,
            ReconcilePaperOrderHandler,
        )

        def lookup_then_die(client_order_id: str) -> tuple[int, object | None, str]:
            (out / "lookup-asked.txt").write_text(client_order_id, encoding="utf-8")
            die("during-reconciliation-lookup-after-round-begun")
            raise AssertionError("unreachable")

        broker.fetch_order_by_client_order_id = lookup_then_die  # type: ignore[method-assign]
        ReconcilePaperOrderHandler(
            attempts=attempts,
            acknowledgements=acknowledgements,  # type: ignore[arg-type]
            events=events,
            broker=broker,
            authorizations=paper.execution_authorizations,
            previews=paper.submission_previews,
            rounds=paper.reconciliation_rounds,
            time_source=clock,
        ).handle(ReconcilePaperOrderCommand(intent_governance_id=intent_id, at=clock.utc))
        (out / "died-at.txt").write_text("did-not-die", encoding="utf-8")
        return 0
    else:
        raise SystemExit(f"unknown scenario {scenario!r}")

    handler = SubmitAuthorizedPaperOrderHandler(
        intents=m084.approved_order_intents,
        configurations=m084.operator_trading_configurations,
        time_bases=paper.time_bases,
        previews=paper.submission_previews,
        authorizations=paper.execution_authorizations,
        attempts=attempts,
        acknowledgements=acknowledgements,  # type: ignore[arg-type]
        events=events,
        snapshots=paper.paper_account_snapshots,
        broker=broker,
        market_data=data,
        kill_switch=paper.execution_kill_switch,
        time_source=clock,
    )
    handler.handle(
        SubmitAuthorizedPaperOrderCommand(
            intent_governance_id=intent_id,
            attempt_id=attempt_id,
            account_snapshot_id=f"SNP-SEND-{attempt_id}",
            at=clock.utc,
        )
    )
    (out / "died-at.txt").write_text("did-not-die", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
