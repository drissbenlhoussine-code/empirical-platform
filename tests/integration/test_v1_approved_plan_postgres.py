"""RELEASE v1 -- `ApprovedPlan` over REAL PostgreSQL: the exactly-once exit-trigger claim
proven under real concurrent connections, not just the in-memory fake's own lock.

Same database (Store A) M090 already uses, migration `b9f2c4d6a8e1` stacked on M090's head.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import alembic_config, build_engine, config, postgres_enabled

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    ExitTriggerKind,
    derive_system_identity,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.approved_plan_repositories import (  # noqa: E501
    V1_APPROVED_PLAN_SCHEMA_HEAD,
    ApprovedPlanAlreadyExistsError,
    ApprovedPlanSchemaHeadError,
    PostgresApprovedPlanRepository,
    require_exact_v1_approved_plan_schema_head,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
_TABLE = "approved_plan"


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    yield from build_engine("head")


@pytest.fixture
def repo(engine: Engine) -> Iterator[PostgresApprovedPlanRepository]:
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE public.{_TABLE}"))
    service = PostgresPersistenceService(config("v1-approved-plan-test"))
    service.initialize()
    try:
        yield PostgresApprovedPlanRepository(service)
    finally:
        service.close()


def _plan(plan_id: str, *, entry: str, stop: Decimal, target: Decimal) -> ApprovedPlan:
    owner = f"OWN-{plan_id}"
    return ApprovedPlan(
        plan_id=plan_id,
        candidate_id="CAND-1",
        entry_intent_governance_id=entry,
        symbol="AAPL",
        approved_quantity=Decimal("5"),
        stop_price=stop,
        target_price=target,
        mandatory_liquidation_at=_NOW + timedelta(hours=2),
        owner_approval_id=owner,
        system_identity=derive_system_identity(plan_id=plan_id, owner_approval_id=owner),
        created_at=_NOW,
    )


def test_schema_head_matches_this_codes_own_constant(engine: Engine) -> None:
    with engine.begin() as connection:
        rows = connection.execute(text("SELECT version_num FROM public.alembic_version")).all()
    assert [r[0] for r in rows] == [V1_APPROVED_PLAN_SCHEMA_HEAD]


def test_the_schema_head_guard_passes_at_the_real_head(
    repo: PostgresApprovedPlanRepository, engine: Engine
) -> None:
    service = PostgresPersistenceService(config("v1-guard-check"))
    service.initialize()
    try:
        assert require_exact_v1_approved_plan_schema_head(service) == V1_APPROVED_PLAN_SCHEMA_HEAD
    finally:
        service.close()


def test_the_schema_head_guard_refuses_an_older_database(engine: Engine) -> None:
    """Downgrades the SHARED module engine to M090's head (one revision behind this
    table) just long enough to prove the guard refuses it, then restores it to this
    table's own head in a `finally` -- the module's `engine` fixture is reused by every
    other test in this file and must be left exactly as it found it."""
    cfg = alembic_config()
    alembic_command.downgrade(cfg, "a2b4c6d8e0f2")
    try:
        service = PostgresPersistenceService(config("v1-guard-refusal"))
        service.initialize()
        try:
            with pytest.raises(ApprovedPlanSchemaHeadError):
                require_exact_v1_approved_plan_schema_head(service)
        finally:
            service.close()
    finally:
        alembic_command.upgrade(cfg, V1_APPROVED_PLAN_SCHEMA_HEAD)


def test_save_get_and_round_trip(repo: PostgresApprovedPlanRepository) -> None:
    plan = _plan("PLAN-RT-1", entry="INT-RT-1", stop=Decimal("95"), target=Decimal("110"))
    saved = repo.save(plan)
    assert saved == plan
    assert repo.get("PLAN-RT-1") == plan
    assert repo.for_entry("INT-RT-1") == plan
    assert repo.get("NO-SUCH-PLAN") is None


def test_a_duplicate_plan_id_is_refused(repo: PostgresApprovedPlanRepository) -> None:
    plan = _plan("PLAN-DUP-1", entry="INT-DUP-1", stop=Decimal("95"), target=Decimal("110"))
    repo.save(plan)
    with pytest.raises(ApprovedPlanAlreadyExistsError):
        repo.save(plan)


def test_a_duplicate_entry_is_refused_even_under_a_new_plan_id(
    repo: PostgresApprovedPlanRepository,
) -> None:
    repo.save(_plan("PLAN-A", entry="INT-SAME", stop=Decimal("95"), target=Decimal("110")))
    with pytest.raises(ApprovedPlanAlreadyExistsError):
        repo.save(_plan("PLAN-B", entry="INT-SAME", stop=Decimal("90"), target=Decimal("100")))


def test_list_unclaimed_and_list_claimed_partition_correctly(
    repo: PostgresApprovedPlanRepository,
) -> None:
    a = repo.save(_plan("PLAN-U-1", entry="INT-U-1", stop=Decimal("95"), target=Decimal("110")))
    repo.save(_plan("PLAN-U-2", entry="INT-U-2", stop=Decimal("95"), target=Decimal("110")))
    assert {p.plan_id for p in repo.list_unclaimed(10)} == {"PLAN-U-1", "PLAN-U-2"}
    assert repo.list_claimed(10) == ()

    claimed = repo.claim_exit_trigger(a.plan_id, kind=ExitTriggerKind.STOP, claimed_at=_NOW)
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.STOP
    assert {p.plan_id for p in repo.list_unclaimed(10)} == {"PLAN-U-2"}
    assert {p.plan_id for p in repo.list_claimed(10)} == {"PLAN-U-1"}


def test_claiming_an_already_claimed_plan_returns_none_not_an_error(
    repo: PostgresApprovedPlanRepository,
) -> None:
    plan = repo.save(_plan("PLAN-C-1", entry="INT-C-1", stop=Decimal("95"), target=Decimal("110")))
    first = repo.claim_exit_trigger(plan.plan_id, kind=ExitTriggerKind.STOP, claimed_at=_NOW)
    assert first is not None
    second = repo.claim_exit_trigger(
        plan.plan_id, kind=ExitTriggerKind.TARGET, claimed_at=_NOW + timedelta(seconds=1)
    )
    assert second is None
    # The stored kind is still the FIRST winner's, never overwritten by the loser.
    assert repo.get(plan.plan_id).triggered_exit_kind is ExitTriggerKind.STOP  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# THE core exactly-once proof: real concurrent Postgres connections racing the
# SAME conditional UPDATE, not threads sharing one Python-level lock.
# ---------------------------------------------------------------------------


def test_many_real_connections_racing_the_same_claim_exactly_one_wins(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE public.{_TABLE}"))
    setup_service = PostgresPersistenceService(config("v1-race-setup"))
    setup_service.initialize()
    try:
        plan = PostgresApprovedPlanRepository(setup_service).save(
            _plan("PLAN-RACE-1", entry="INT-RACE-1", stop=Decimal("95"), target=Decimal("110"))
        )
    finally:
        setup_service.close()

    workers = 8
    barrier = threading.Barrier(workers)
    results: list[ApprovedPlan | None] = []
    lock = threading.Lock()

    def worker(kind: ExitTriggerKind) -> None:
        service = PostgresPersistenceService(config("v1-race-worker"))
        service.initialize()
        try:
            repo = PostgresApprovedPlanRepository(service)
            barrier.wait(timeout=10)
            outcome = repo.claim_exit_trigger(plan.plan_id, kind=kind, claimed_at=_NOW)
            with lock:
                results.append(outcome)
        finally:
            service.close()

    kinds = [ExitTriggerKind.STOP, ExitTriggerKind.TARGET, ExitTriggerKind.MANDATORY_EXIT] * 3
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(worker, kinds[:workers]))

    winners = [r for r in results if r is not None]
    assert len(winners) == 1, f"exactly one claim must win; got {len(winners)}: {winners}"

    verify_service = PostgresPersistenceService(config("v1-race-verify"))
    verify_service.initialize()
    try:
        final = PostgresApprovedPlanRepository(verify_service).get(plan.plan_id)
    finally:
        verify_service.close()
    assert final is not None and final.triggered_exit_kind == winners[0].triggered_exit_kind


# ---------------------------------------------------------------------------
# The database's OWN triggers, independent of the repository's conditional UPDATE.
# ---------------------------------------------------------------------------


def test_the_database_itself_refuses_a_second_claim_bypassing_the_where_clause(
    engine: Engine,
) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE public.{_TABLE}"))
    service = PostgresPersistenceService(config("v1-trigger-check"))
    service.initialize()
    try:
        repo = PostgresApprovedPlanRepository(service)
        plan = repo.save(
            _plan("PLAN-TRIG-1", entry="INT-TRIG-1", stop=Decimal("95"), target=Decimal("110"))
        )
        repo.claim_exit_trigger(plan.plan_id, kind=ExitTriggerKind.STOP, claimed_at=_NOW)
    finally:
        service.close()

    with engine.begin() as connection, pytest.raises(sa.exc.DatabaseError):
        connection.execute(
            text(
                "UPDATE public.approved_plan SET triggered_exit_kind = 'TARGET' WHERE plan_id = :p"
            ),
            {"p": "PLAN-TRIG-1"},
        )


def test_the_database_refuses_changing_an_immutable_column(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE public.{_TABLE}"))
    service = PostgresPersistenceService(config("v1-immutable-check"))
    service.initialize()
    try:
        PostgresApprovedPlanRepository(service).save(
            _plan("PLAN-IMM-1", entry="INT-IMM-1", stop=Decimal("95"), target=Decimal("110"))
        )
    finally:
        service.close()

    with engine.begin() as connection, pytest.raises(sa.exc.DatabaseError):
        connection.execute(
            text("UPDATE public.approved_plan SET symbol = 'MSFT' WHERE plan_id = :p"),
            {"p": "PLAN-IMM-1"},
        )


def test_the_database_refuses_deleting_a_plan(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE public.{_TABLE}"))
    service = PostgresPersistenceService(config("v1-delete-check"))
    service.initialize()
    try:
        PostgresApprovedPlanRepository(service).save(
            _plan("PLAN-DEL-1", entry="INT-DEL-1", stop=Decimal("95"), target=Decimal("110"))
        )
    finally:
        service.close()

    with engine.begin() as connection, pytest.raises(sa.exc.DatabaseError):
        connection.execute(
            text("DELETE FROM public.approved_plan WHERE plan_id = :p"), {"p": "PLAN-DEL-1"}
        )
