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
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import build_engine, config, postgres_enabled

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    ExitTriggerKind,
    derive_legacy_system_identity,
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
    """An older revision stamp fails closed without destructive downgrade.

    The shared TEST database is restored to its exact original stamp in finally.
    A separate risk-contract integration test proves the real additive upgrade.
    """
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = :revision"),
            {"revision": "a2b4c6d8" + "e0f2"},
        )
    try:
        service = PostgresPersistenceService(config("v1-guard-refusal"))
        service.initialize()
        try:
            with pytest.raises(ApprovedPlanSchemaHeadError):
                require_exact_v1_approved_plan_schema_head(service)
        finally:
            service.close()
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :head"),
                {"head": V1_APPROVED_PLAN_SCHEMA_HEAD},
            )


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


def test_claiming_a_stop_or_target_persists_the_quote_evidence_that_drove_it(
    repo: PostgresApprovedPlanRepository,
) -> None:
    """FORENSIC AUDIT FOLLOW-UP (2026-10-20 early-STOP incident): proves the real
    PostgreSQL round trip for migration f3a7c9e2b164's four new columns, not just the
    in-memory fake."""
    plan = repo.save(
        _plan("PLAN-EVIDENCE-1", entry="INT-EVIDENCE-1", stop=Decimal("95"), target=Decimal("110"))
    )
    claimed = repo.claim_exit_trigger(
        plan.plan_id,
        kind=ExitTriggerKind.STOP,
        claimed_at=_NOW,
        quote_bid=Decimal("94.50"),
        quote_ask=Decimal("94.60"),
        quote_captured_at=_NOW - timedelta(seconds=1),
        quote_source="alpaca-iex",
    )
    assert claimed is not None
    assert claimed.triggered_exit_quote_bid == Decimal("94.50")
    assert claimed.triggered_exit_quote_ask == Decimal("94.60")
    assert claimed.triggered_exit_quote_captured_at == _NOW - timedelta(seconds=1)
    assert claimed.triggered_exit_quote_source == "alpaca-iex"

    reloaded = repo.get(plan.plan_id)
    assert reloaded is not None
    assert reloaded.triggered_exit_quote_bid == Decimal("94.50")
    assert reloaded.triggered_exit_quote_source == "alpaca-iex"


def test_claiming_without_quote_evidence_remains_valid(
    repo: PostgresApprovedPlanRepository,
) -> None:
    """NOT required -- a direct claim with no quote in scope (restart-recovery resumption,
    a concurrency race, MANDATORY_EXIT) is exactly as valid as before this migration."""
    plan = repo.save(
        _plan(
            "PLAN-NO-EVIDENCE-1",
            entry="INT-NO-EVIDENCE-1",
            stop=Decimal("95"),
            target=Decimal("110"),
        )
    )
    claimed = repo.claim_exit_trigger(
        plan.plan_id, kind=ExitTriggerKind.MANDATORY_EXIT, claimed_at=_NOW
    )
    assert claimed is not None
    assert claimed.triggered_exit_quote_bid is None
    assert claimed.triggered_exit_quote_ask is None
    assert claimed.triggered_exit_quote_captured_at is None
    assert claimed.triggered_exit_quote_source is None


def test_the_database_refuses_a_mandatory_exit_claim_carrying_quote_evidence(
    engine: Engine,
) -> None:
    """The database's OWN guard (not just `ApprovedPlan.__post_init__`) refuses a
    MANDATORY_EXIT claim that tries to carry quote evidence -- a time-based trigger never
    consults a quote, so it must never be able to assert that one drove it."""
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE public.{_TABLE}"))
    with engine.begin() as connection, pytest.raises(sa.exc.DatabaseError):
        connection.execute(
            text(
                "INSERT INTO public.approved_plan (plan_id, candidate_id, "
                "entry_intent_governance_id, symbol, approved_quantity, stop_price, "
                "target_price, mandatory_liquidation_at, owner_approval_id, system_identity, "
                "created_at, triggered_exit_kind, triggered_exit_at, triggered_exit_quote_bid, "
                "triggered_exit_quote_ask, triggered_exit_quote_captured_at, "
                "triggered_exit_quote_source) "
                "VALUES ('PLAN-BAD-EVIDENCE', 'CAND-1', 'INT-BAD-EVIDENCE', 'AAPL', 5, 95, 110, "
                ":deadline, 'OWN-1', :identity, :now, 'MANDATORY_EXIT', :now, 94.50, 94.60, "
                ":now, 'alpaca-iex')"
            ),
            {
                "deadline": _NOW + timedelta(hours=2),
                "identity": derive_system_identity(
                    plan_id="PLAN-BAD-EVIDENCE", owner_approval_id="OWN-1"
                ),
                "now": _NOW,
            },
        )


def test_the_database_refuses_partial_quote_evidence(engine: Engine) -> None:
    """The quote-evidence columns are all-or-nothing at the database layer too."""
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE public.{_TABLE}"))
    service = PostgresPersistenceService(config("v1-partial-evidence-check"))
    service.initialize()
    try:
        repo = PostgresApprovedPlanRepository(service)
        repo.save(
            _plan(
                "PLAN-PARTIAL-1", entry="INT-PARTIAL-1", stop=Decimal("95"), target=Decimal("110")
            )
        )
    finally:
        service.close()

    with engine.begin() as connection, pytest.raises(sa.exc.DatabaseError):
        connection.execute(
            text(
                "UPDATE public.approved_plan SET triggered_exit_kind = 'STOP', "
                "triggered_exit_at = :now, triggered_exit_quote_bid = 94.50 "
                "WHERE plan_id = :p"
            ),
            {"p": "PLAN-PARTIAL-1", "now": _NOW},
        )


def test_the_database_refuses_changing_quote_evidence_after_it_is_claimed(
    engine: Engine,
) -> None:
    """Append-only, matching `triggered_exit_kind` itself: once a STOP/TARGET claim has
    recorded its quote evidence, that evidence can never be altered."""
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE public.{_TABLE}"))
    service = PostgresPersistenceService(config("v1-evidence-immutable-check"))
    service.initialize()
    try:
        repo = PostgresApprovedPlanRepository(service)
        plan = repo.save(
            _plan(
                "PLAN-EVIDENCE-IMM-1",
                entry="INT-EVIDENCE-IMM-1",
                stop=Decimal("95"),
                target=Decimal("110"),
            )
        )
        repo.claim_exit_trigger(
            plan.plan_id,
            kind=ExitTriggerKind.STOP,
            claimed_at=_NOW,
            quote_bid=Decimal("94.50"),
            quote_ask=Decimal("94.60"),
            quote_captured_at=_NOW,
            quote_source="alpaca-iex",
        )
    finally:
        service.close()

    with engine.begin() as connection, pytest.raises(sa.exc.DatabaseError):
        connection.execute(
            text("UPDATE public.approved_plan SET triggered_exit_quote_bid = 1 WHERE plan_id = :p"),
            {"p": "PLAN-EVIDENCE-IMM-1"},
        )


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


# ---------------------------------------------------------------------------
# RELEASE v1 LEGACY APPROVED PLAN IDENTITY COMPATIBILITY: the REAL Postgres read path
# (not just the pure-domain `reconstruct_approved_plan` unit tests) correctly loads a row
# whose `system_identity` predates the hash-based rewrite -- written directly by raw SQL
# here (never through `repo.save()`, which always writes the current format, proving a row
# like this can only arise from history, never from a save going through this release).
# ---------------------------------------------------------------------------

_REAL_PLAN_ID = "PLAN-INT-PRP-089-PAPER-20261009T172613Z"
_REAL_OWNER_APPROVAL_ID = "DEC-PRP-089-PAPER-20261009T172613Z"
_REAL_ENTRY_INTENT_ID = "INT-PRP-089-PAPER-20261009T172613Z"


def _insert_legacy_row(engine: Engine, **overrides: object) -> None:
    system_identity = overrides.pop(
        "system_identity",
        derive_legacy_system_identity(
            plan_id=_REAL_PLAN_ID, owner_approval_id=_REAL_OWNER_APPROVAL_ID
        ),
    )
    fields: dict[str, object] = {
        "plan_id": _REAL_PLAN_ID,
        "candidate_id": "PRP-089-PAPER-20261009T172613Z",
        "entry_intent_governance_id": _REAL_ENTRY_INTENT_ID,
        "symbol": "AAPL",
        "approved_quantity": Decimal("1"),
        "stop_price": Decimal("331.70"),
        "target_price": Decimal("341.75"),
        "mandatory_liquidation_at": _NOW - timedelta(hours=1),
        "owner_approval_id": _REAL_OWNER_APPROVAL_ID,
        "system_identity": system_identity,
        "created_at": _NOW - timedelta(days=4),
    }
    fields.update(overrides)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.approved_plan (plan_id, candidate_id, "
                "entry_intent_governance_id, symbol, approved_quantity, stop_price, "
                "target_price, mandatory_liquidation_at, owner_approval_id, system_identity, "
                "created_at, triggered_exit_kind, triggered_exit_at) "
                "VALUES (:plan_id, :candidate_id, :entry_intent_governance_id, :symbol, "
                ":approved_quantity, :stop_price, :target_price, :mandatory_liquidation_at, "
                ":owner_approval_id, :system_identity, :created_at, NULL, NULL)"
            ),
            fields,
        )


def test_a_real_legacy_identity_row_loads_correctly_through_get_and_for_entry(
    engine: Engine, repo: PostgresApprovedPlanRepository
) -> None:
    legacy_identity = derive_legacy_system_identity(
        plan_id=_REAL_PLAN_ID, owner_approval_id=_REAL_OWNER_APPROVAL_ID
    )
    _insert_legacy_row(engine)

    by_id = repo.get(_REAL_PLAN_ID)
    assert by_id is not None
    assert by_id.system_identity == legacy_identity
    assert by_id.plan_id == _REAL_PLAN_ID
    assert by_id.owner_approval_id == _REAL_OWNER_APPROVAL_ID

    by_entry = repo.for_entry(_REAL_ENTRY_INTENT_ID)
    assert by_entry is not None
    assert by_entry.system_identity == legacy_identity


def test_a_real_legacy_identity_row_appears_in_list_unclaimed(
    engine: Engine, repo: PostgresApprovedPlanRepository
) -> None:
    _insert_legacy_row(engine)
    unclaimed = repo.list_unclaimed(limit=10)
    assert len(unclaimed) == 1
    assert unclaimed[0].plan_id == _REAL_PLAN_ID


def test_claiming_a_legacy_plans_exit_trigger_preserves_its_identity(
    engine: Engine, repo: PostgresApprovedPlanRepository
) -> None:
    """8. The one controlled mutation a plan ever undergoes (the exit-trigger claim) must
    not disturb a legacy row's preserved, historical identity."""
    legacy_identity = derive_legacy_system_identity(
        plan_id=_REAL_PLAN_ID, owner_approval_id=_REAL_OWNER_APPROVAL_ID
    )
    _insert_legacy_row(engine)
    claimed = repo.claim_exit_trigger(
        _REAL_PLAN_ID, kind=ExitTriggerKind.MANDATORY_EXIT, claimed_at=_NOW
    )
    assert claimed is not None
    assert claimed.is_claimed
    assert claimed.system_identity == legacy_identity

    reloaded = repo.get(_REAL_PLAN_ID)
    assert reloaded is not None
    assert reloaded.triggered_exit_kind is ExitTriggerKind.MANDATORY_EXIT
    assert reloaded.system_identity == legacy_identity


def test_a_forged_legacy_identity_row_is_refused_on_read(
    engine: Engine, repo: PostgresApprovedPlanRepository
) -> None:
    """7. A row whose `system_identity` matches NEITHER formula -- however it got into the
    database -- fails closed on read, exactly as before this compatibility fix existed."""
    _insert_legacy_row(engine, system_identity="freeform-forged-value")
    with pytest.raises(ValueError, match="matches neither"):
        repo.get(_REAL_PLAN_ID)
