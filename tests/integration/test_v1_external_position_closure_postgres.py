"""RELEASE v1 -- `ExternalPositionClosure` over REAL PostgreSQL, Store C.

The one new, independent table this release adds on top of the M089 chain (see that
migration's own docstring). Proves the repository's round trip, the at-most-one-per-entry
uniqueness under the database's OWN constraint (not just the fake's Python lock), and the
append-only trigger reused unchanged from the first M089 migration.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m089_support import build_engine_c, store_c_config, truncate_all_c

from empirical_platform.decision_candidate.external_position_closure import (
    ExternalPositionClosure,
    external_position_closure_id,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.external_position_closure_repositories import (  # noqa: E501
    ExternalPositionClosureAlreadyExistsError,
    PostgresExternalPositionClosureRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_position_exit_schema import (
    M089_SCHEMA_HEAD,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
_TABLE = "external_position_closure"


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine_c("head")


@pytest.fixture
def repo(engine: Engine) -> Iterator[PostgresExternalPositionClosureRepository]:
    truncate_all_c(engine)
    service = PostgresPersistenceService(store_c_config("v1-external-closure-test"))
    service.initialize()
    try:
        yield PostgresExternalPositionClosureRepository(service)
    finally:
        service.close()


def _closure(entry: str, *, client_order_id: str = "EXTERNAL-SELL-1") -> ExternalPositionClosure:
    return ExternalPositionClosure(
        closure_id=external_position_closure_id(entry),
        entry_intent_governance_id=entry,
        symbol="AAPL",
        quantity=8,
        broker_order_id="broker-order-1",
        client_order_id=client_order_id,
        filled_avg_price=Decimal("229.50"),
        recorded_by="owner",
        recorded_at=_NOW,
    )


def test_schema_head_matches_this_codes_own_constant(engine: Engine) -> None:
    with engine.begin() as connection:
        rows = connection.execute(text("SELECT version_num FROM public.alembic_version")).all()
    assert [r[0] for r in rows] == [M089_SCHEMA_HEAD]


def test_save_and_for_entry_round_trip(repo: PostgresExternalPositionClosureRepository) -> None:
    closure = _closure("INT-RT-1")
    saved = repo.save(closure)
    assert saved == closure
    assert repo.for_entry("INT-RT-1") == closure
    assert repo.for_entry("INT-NO-SUCH-ENTRY") is None


def test_a_duplicate_entry_is_refused_even_under_a_different_order(
    repo: PostgresExternalPositionClosureRepository,
) -> None:
    repo.save(_closure("INT-DUP-1", client_order_id="EXTERNAL-SELL-1"))
    with pytest.raises(ExternalPositionClosureAlreadyExistsError):
        repo.save(_closure("INT-DUP-1", client_order_id="EXTERNAL-SELL-2"))


def test_the_database_refuses_a_second_row_for_the_same_entry_bypassing_the_repository(
    engine: Engine,
) -> None:
    """The UNIQUE constraint holds even against a raw INSERT that never went through
    `for_entry`'s own pre-check -- the same belt-and-suspenders discipline
    `ApprovedPlanRepository`/`PositionExitAttemptRepository` already prove elsewhere."""
    truncate_all_c(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.external_position_closure (closure_id, "
                "entry_intent_governance_id, symbol, quantity, broker_order_id, "
                "client_order_id, filled_avg_price, recorded_by, recorded_at) VALUES "
                "('XEC-INT-RAW-1', 'INT-RAW-1', 'AAPL', 8, 'b-1', 'c-1', 229.50, 'owner', "
                ":at)"
            ),
            {"at": _NOW},
        )
    with engine.begin() as connection, pytest.raises(sa.exc.IntegrityError):
        connection.execute(
            text(
                "INSERT INTO public.external_position_closure (closure_id, "
                "entry_intent_governance_id, symbol, quantity, broker_order_id, "
                "client_order_id, filled_avg_price, recorded_by, recorded_at) VALUES "
                "('XEC-INT-RAW-1-AGAIN', 'INT-RAW-1', 'AAPL', 8, 'b-2', 'c-2', 229.50, "
                "'owner', :at)"
            ),
            {"at": _NOW},
        )


def test_the_database_refuses_a_row_whose_closure_id_is_not_derived(engine: Engine) -> None:
    truncate_all_c(engine)
    with engine.begin() as connection, pytest.raises(sa.exc.IntegrityError):
        connection.execute(
            text(
                "INSERT INTO public.external_position_closure (closure_id, "
                "entry_intent_governance_id, symbol, quantity, broker_order_id, "
                "client_order_id, filled_avg_price, recorded_by, recorded_at) VALUES "
                "('XEC-WRONG-ID', 'INT-DERIVED-1', 'AAPL', 8, 'b-1', 'c-1', 229.50, "
                "'owner', :at)"
            ),
            {"at": _NOW},
        )


def test_the_database_refuses_updating_a_recorded_closure(
    engine: Engine, repo: PostgresExternalPositionClosureRepository
) -> None:
    repo.save(_closure("INT-IMM-1"))
    with engine.begin() as connection, pytest.raises(sa.exc.DatabaseError):
        connection.execute(
            text(
                "UPDATE public.external_position_closure SET quantity = 99 "
                "WHERE entry_intent_governance_id = 'INT-IMM-1'"
            )
        )


def test_the_database_refuses_deleting_a_recorded_closure(
    engine: Engine, repo: PostgresExternalPositionClosureRepository
) -> None:
    repo.save(_closure("INT-DEL-1"))
    with engine.begin() as connection, pytest.raises(sa.exc.DatabaseError):
        connection.execute(
            text(
                "DELETE FROM public.external_position_closure "
                "WHERE entry_intent_governance_id = 'INT-DEL-1'"
            )
        )
