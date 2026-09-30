"""MILESTONE-090 -- the Opportunity Engine's two tables over real PostgreSQL.

Same database Track A/M084's own migrations already live in (current head after this
milestone's own migration); no new Store, no schema-head guard (see
`external-review/MILESTONE-090/scope-and-design.md` Section 4 for why). Every database-level
guard here is exercised directly with a raw statement, exactly mirroring
`test_m087_position_exit_postgres.py`'s own `_refused()` pattern, plus one full round trip
through the real `PostgresOpportunityRepository`/`PostgresOpportunityDecisionRepository`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from tests.integration._m085_support import build_engine, config
from tests.integration._m090_support import truncate_all_m090

from empirical_platform.decision_candidate.opportunity_engine import (
    MarketSessionState,
    OpportunityDecision,
    OpportunityStatus,
    OwnerOpportunityAction,
    RejectionReason,
    TradingOpportunity,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.opportunity_engine_repositories import (  # noqa: E501
    PostgresOpportunityEngineRuntime,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


@pytest.fixture
def world(engine: Engine) -> Iterator[dict[str, object]]:
    truncate_all_m090(engine)
    service = PostgresPersistenceService(config("m090-opportunity-engine"))
    service.initialize()
    runtime = PostgresOpportunityEngineRuntime(service)
    try:
        yield {"engine": engine, "service": service, "runtime": runtime}
    finally:
        service.close()


def _refused(engine: Engine, statement: str, **params: object) -> str:
    with pytest.raises((DBAPIError, IntegrityError)) as error, engine.begin() as connection:
        connection.execute(text(statement), params)
    return str(error.value)


def _a_candidate_opportunity(**overrides: object) -> TradingOpportunity:
    defaults: dict[str, object] = {
        "opportunity_id": "OPP-090-0001",
        "policy_fingerprint": "a" * 64,
        "symbol": "AAPL",
        "generated_at": _NOW,
        "expires_at": _NOW + timedelta(minutes=5),
        "evidence_as_of": _NOW,
        "session": MarketSessionState.REGULAR_SESSION,
        "bid": Decimal("101.00"),
        "ask": Decimal("101.05"),
        "spread_percent": Decimal("0.05"),
        "entry_price": None,
        "stop_price": None,
        "target_price": None,
        "risk_per_share": None,
        "reward_per_share": None,
        "reward_risk_ratio": None,
        "quantity": None,
        "notional": None,
        "maximum_loss": None,
        "mandatory_liquidation_at": None,
        "structure_model_id": "BOUNDED_RANGE_BREAKOUT_HIGHER_LOW_VOLUME",
        "structure_model_version": "1",
        "evidence": ("breakout above range high", "volume above reference average"),
        "quality_score": None,
        "quality_model_id": "SPREAD_LIQUIDITY_TREND_REWARD_RISK_FRESHNESS_WEIGHTED_SUM",
        "quality_model_version": "1",
        "rejection_reasons": (),
        "status": OpportunityStatus.CANDIDATE,
    }
    defaults.update(overrides)
    return TradingOpportunity(**defaults)  # type: ignore[arg-type]


def _actionable_fields() -> dict[str, object]:
    return {
        "entry_price": Decimal("101.50"),
        "stop_price": Decimal("100.10"),
        "target_price": Decimal("104.30"),
        "risk_per_share": Decimal("1.40"),
        "reward_per_share": Decimal("2.80"),
        "reward_risk_ratio": Decimal("2.00"),
        "quantity": 4,
        "notional": Decimal("406.00"),
        "maximum_loss": Decimal("5.60"),
        "mandatory_liquidation_at": _NOW + timedelta(hours=2),
        "quality_score": Decimal("72.5"),
        "status": OpportunityStatus.ACTIONABLE,
    }


def _insert_opportunity(engine: Engine, opportunity: TradingOpportunity) -> None:
    """Insert directly via raw SQL, for the negative-constraint tests below that must attack
    the table without going through the (already-validating) domain object or repository."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.opportunity ("
                "opportunity_id, policy_fingerprint, symbol, generated_at, expires_at, "
                "evidence_as_of, session, bid, ask, spread_percent, entry_price, stop_price, "
                "target_price, risk_per_share, reward_per_share, reward_risk_ratio, quantity, "
                "notional, maximum_loss, mandatory_liquidation_at, structure_model_id, "
                "structure_model_version, evidence, quality_score, quality_model_id, "
                "quality_model_version, rejection_reasons, status"
                ") VALUES ("
                ":opportunity_id, :policy_fingerprint, :symbol, :generated_at, :expires_at, "
                ":evidence_as_of, :session, :bid, :ask, :spread_percent, :entry_price, "
                ":stop_price, :target_price, :risk_per_share, :reward_per_share, "
                ":reward_risk_ratio, :quantity, :notional, :maximum_loss, "
                ":mandatory_liquidation_at, :structure_model_id, :structure_model_version, "
                ":evidence, :quality_score, :quality_model_id, :quality_model_version, "
                ":rejection_reasons, :status)"
            ),
            {
                "opportunity_id": opportunity.opportunity_id,
                "policy_fingerprint": opportunity.policy_fingerprint,
                "symbol": opportunity.symbol,
                "generated_at": opportunity.generated_at,
                "expires_at": opportunity.expires_at,
                "evidence_as_of": opportunity.evidence_as_of,
                "session": opportunity.session.value,
                "bid": opportunity.bid,
                "ask": opportunity.ask,
                "spread_percent": opportunity.spread_percent,
                "entry_price": opportunity.entry_price,
                "stop_price": opportunity.stop_price,
                "target_price": opportunity.target_price,
                "risk_per_share": opportunity.risk_per_share,
                "reward_per_share": opportunity.reward_per_share,
                "reward_risk_ratio": opportunity.reward_risk_ratio,
                "quantity": opportunity.quantity,
                "notional": opportunity.notional,
                "maximum_loss": opportunity.maximum_loss,
                "mandatory_liquidation_at": opportunity.mandatory_liquidation_at,
                "structure_model_id": opportunity.structure_model_id,
                "structure_model_version": opportunity.structure_model_version,
                "evidence": json.dumps(list(opportunity.evidence)),
                "quality_score": opportunity.quality_score,
                "quality_model_id": opportunity.quality_model_id,
                "quality_model_version": opportunity.quality_model_version,
                "rejection_reasons": json.dumps([r.value for r in opportunity.rejection_reasons]),
                "status": opportunity.status.value,
            },
        )


# ---------------------------------------------------------------------------
# Migration / schema shape
# ---------------------------------------------------------------------------


def test_the_migration_creates_both_tables_at_head(engine: Engine) -> None:
    with engine.begin() as connection:
        present = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
        }
    assert {"opportunity", "opportunity_decision"} <= present


# ---------------------------------------------------------------------------
# CHECK constraints
# ---------------------------------------------------------------------------


def test_a_lowercase_symbol_is_refused(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(symbol="AAPL")
    with pytest.raises(ValueError, match="upper-case"):
        _a_candidate_opportunity(symbol="aapl")
    # The domain object itself already refuses this; attack the table directly instead.
    message = _refused(
        engine,
        "INSERT INTO public.opportunity (opportunity_id, policy_fingerprint, symbol, "
        "generated_at, expires_at, evidence_as_of, session, structure_model_id, "
        "structure_model_version, evidence, quality_model_id, quality_model_version, "
        "rejection_reasons, status) VALUES ("
        "'OPP-BAD-1', :fp, 'aapl', :g, :e, :ev, 'REGULAR_SESSION', 'X', '1', '[]', 'X', '1', "
        "'[]', 'CANDIDATE')",
        fp=opportunity.policy_fingerprint,
        g=_NOW,
        e=_NOW + timedelta(minutes=5),
        ev=_NOW,
    )
    assert "ck_opportunity_symbol_upper" in message or "violates" in message


def test_expires_at_must_follow_generated_at(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    message = _refused(
        engine,
        "INSERT INTO public.opportunity (opportunity_id, policy_fingerprint, symbol, "
        "generated_at, expires_at, evidence_as_of, session, structure_model_id, "
        "structure_model_version, evidence, quality_model_id, quality_model_version, "
        "rejection_reasons, status) VALUES ("
        "'OPP-BAD-2', :fp, 'AAPL', :g, :e, :ev, 'REGULAR_SESSION', 'X', '1', '[]', 'X', '1', "
        "'[]', 'CANDIDATE')",
        fp="a" * 64,
        g=_NOW,
        e=_NOW - timedelta(minutes=1),
        ev=_NOW,
    )
    assert "ck_opportunity_expiry_follows" in message or "violates" in message


def test_an_unknown_status_is_refused(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    message = _refused(
        engine,
        "INSERT INTO public.opportunity (opportunity_id, policy_fingerprint, symbol, "
        "generated_at, expires_at, evidence_as_of, session, structure_model_id, "
        "structure_model_version, evidence, quality_model_id, quality_model_version, "
        "rejection_reasons, status) VALUES ("
        "'OPP-BAD-3', :fp, 'AAPL', :g, :e, :ev, 'REGULAR_SESSION', 'X', '1', '[]', 'X', '1', "
        "'[]', 'MAYBE')",
        fp="a" * 64,
        g=_NOW,
        e=_NOW + timedelta(minutes=5),
        ev=_NOW,
    )
    assert "ck_opportunity_status" in message or "violates" in message


def test_actionable_requires_every_hard_field(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    # The domain object itself already refuses ACTIONABLE with no hard fields at construction.
    with pytest.raises(ValueError, match="entry/stop/target/quantity"):
        _a_candidate_opportunity(status=OpportunityStatus.ACTIONABLE)
    # Attack the table directly too: the database must refuse it independently of Python.
    message = _refused(
        engine,
        "INSERT INTO public.opportunity (opportunity_id, policy_fingerprint, symbol, "
        "generated_at, expires_at, evidence_as_of, session, structure_model_id, "
        "structure_model_version, evidence, quality_model_id, quality_model_version, "
        "rejection_reasons, status) VALUES ("
        "'OPP-BAD-4', :fp, 'AAPL', :g, :e, :ev, 'REGULAR_SESSION', 'X', '1', '[]', 'X', '1', "
        "'[]', 'ACTIONABLE')",
        fp="a" * 64,
        g=_NOW,
        e=_NOW + timedelta(minutes=5),
        ev=_NOW,
    )
    assert "ck_opportunity_actionable_fields_present" in message or "violates" in message


def test_actionable_stop_must_be_below_entry(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    fields = _actionable_fields()
    fields["stop_price"] = Decimal("999.00")  # ABOVE entry (101.50)
    # The domain object itself already refuses this at construction.
    with pytest.raises(ValueError, match="cannot carry stop >= entry"):
        _a_candidate_opportunity(**fields)
    # Attack the table directly, bypassing the domain object, to prove the database enforces
    # the SAME rule independently of Python.
    message = _refused(
        engine,
        "INSERT INTO public.opportunity (opportunity_id, policy_fingerprint, symbol, "
        "generated_at, expires_at, evidence_as_of, session, entry_price, stop_price, "
        "target_price, risk_per_share, reward_per_share, reward_risk_ratio, quantity, "
        "notional, maximum_loss, mandatory_liquidation_at, structure_model_id, "
        "structure_model_version, evidence, quality_score, quality_model_id, "
        "quality_model_version, rejection_reasons, status) VALUES ("
        "'OPP-BAD-6', :fp, 'AAPL', :g, :e, :ev, 'REGULAR_SESSION', 101.50, 999.00, 104.30, "
        "1.40, 2.80, 2.00, 4, 406.00, 5.60, :liq, 'X', '1', '[]', 72.5, 'X', '1', '[]', "
        "'ACTIONABLE')",
        fp="a" * 64,
        g=_NOW,
        e=_NOW + timedelta(minutes=5),
        ev=_NOW,
        liq=_NOW + timedelta(hours=2),
    )
    assert "ck_opportunity_actionable_stop_below_entry" in message or "violates" in message


def test_rejected_requires_a_reason(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    message = _refused(
        engine,
        "INSERT INTO public.opportunity (opportunity_id, policy_fingerprint, symbol, "
        "generated_at, expires_at, evidence_as_of, session, structure_model_id, "
        "structure_model_version, evidence, quality_model_id, quality_model_version, "
        "rejection_reasons, status) VALUES ("
        "'OPP-BAD-5', :fp, 'AAPL', :g, :e, :ev, 'REGULAR_SESSION', 'X', '1', '[]', 'X', '1', "
        "'[]', 'REJECTED')",
        fp="a" * 64,
        g=_NOW,
        e=_NOW + timedelta(minutes=5),
        ev=_NOW,
    )
    assert "ck_opportunity_rejected_has_reason" in message or "violates" in message


# ---------------------------------------------------------------------------
# Status transition trigger
# ---------------------------------------------------------------------------


def test_an_allowed_transition_succeeds(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(opportunity_id="OPP-TRANS-1")
    _insert_opportunity(engine, opportunity)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.opportunity SET status = 'EXPIRED' WHERE opportunity_id = "
                "'OPP-TRANS-1'"
            )
        )
    with engine.begin() as connection:
        status = connection.execute(
            text("SELECT status FROM public.opportunity WHERE opportunity_id = 'OPP-TRANS-1'")
        ).scalar_one()
    assert status == "EXPIRED"


def test_a_disallowed_transition_is_refused(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(opportunity_id="OPP-TRANS-2")
    _insert_opportunity(engine, opportunity)
    # CANDIDATE -> OWNER_APPROVED skips ACTIONABLE: not in the allowed transition table.
    message = _refused(
        engine,
        "UPDATE public.opportunity SET status = 'OWNER_APPROVED' WHERE opportunity_id = "
        "'OPP-TRANS-2'",
    )
    assert "not an allowed opportunity status transition" in message or "violates" in message


def test_a_terminal_row_refuses_any_further_update(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(opportunity_id="OPP-TRANS-3")
    _insert_opportunity(engine, opportunity)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.opportunity SET status = 'INVALIDATED' WHERE opportunity_id = "
                "'OPP-TRANS-3'"
            )
        )
    message = _refused(
        engine,
        "UPDATE public.opportunity SET status = 'EXPIRED' WHERE opportunity_id = 'OPP-TRANS-3'",
    )
    assert "is terminal" in message or "violates" in message


def test_identity_and_evidence_columns_are_immutable(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(opportunity_id="OPP-TRANS-4")
    _insert_opportunity(engine, opportunity)
    message = _refused(
        engine,
        "UPDATE public.opportunity SET symbol = 'MSFT' WHERE opportunity_id = 'OPP-TRANS-4'",
    )
    assert "identity and evidence are immutable" in message or "violates" in message


def test_opportunity_rows_cannot_be_deleted(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(opportunity_id="OPP-TRANS-5")
    _insert_opportunity(engine, opportunity)
    message = _refused(
        engine, "DELETE FROM public.opportunity WHERE opportunity_id = 'OPP-TRANS-5'"
    )
    assert "append-only" in message or "violates" in message


# ---------------------------------------------------------------------------
# opportunity_decision: FK, uniqueness, the decided-status guard, append-only
# ---------------------------------------------------------------------------


def test_a_decision_cannot_name_a_nonexistent_opportunity(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    message = _refused(
        engine,
        "INSERT INTO public.opportunity_decision (decision_id, opportunity_id, action, "
        "decided_by, decided_at) VALUES ('DEC-1', 'OPP-NO-SUCH-ROW', 'APPROVE', 'owner', :now)",
        now=_NOW,
    )
    assert "does not exist" in message or "violates" in message


def test_a_decision_requires_the_opportunity_to_already_reflect_the_same_action(
    world: dict[str, object],
) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(opportunity_id="OPP-DEC-1", **_actionable_fields())
    _insert_opportunity(engine, opportunity)
    # Still ACTIONABLE, not yet OWNER_APPROVED: the decision guard must refuse.
    message = _refused(
        engine,
        "INSERT INTO public.opportunity_decision (decision_id, opportunity_id, action, "
        "decided_by, decided_at) VALUES ('DEC-2', 'OPP-DEC-1', 'APPROVE', 'owner', :now)",
        now=_NOW,
    )
    assert "may only be recorded once the opportunity itself reflects" in message or (
        "violates" in message
    )


def test_a_matching_decision_succeeds_once_and_is_unique_per_opportunity(
    world: dict[str, object],
) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(opportunity_id="OPP-DEC-2", **_actionable_fields())
    _insert_opportunity(engine, opportunity)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.opportunity SET status = 'OWNER_APPROVED' WHERE opportunity_id = "
                "'OPP-DEC-2'"
            )
        )
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.opportunity_decision (decision_id, opportunity_id, action, "
                "decided_by, decided_at) VALUES ('DEC-3', 'OPP-DEC-2', 'APPROVE', 'owner', :now)"
            ),
            {"now": _NOW},
        )
    message = _refused(
        engine,
        "INSERT INTO public.opportunity_decision (decision_id, opportunity_id, action, "
        "decided_by, decided_at) VALUES ('DEC-4', 'OPP-DEC-2', 'APPROVE', 'owner', :now)",
        now=_NOW,
    )
    assert "uq_opportunity_decision_one_per_opportunity" in message or "violates" in message


def test_decision_rows_are_append_only(world: dict[str, object]) -> None:
    engine: Engine = world["engine"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(opportunity_id="OPP-DEC-3", **_actionable_fields())
    _insert_opportunity(engine, opportunity)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.opportunity SET status = 'OWNER_IGNORED' WHERE opportunity_id = "
                "'OPP-DEC-3'"
            )
        )
        connection.execute(
            text(
                "INSERT INTO public.opportunity_decision (decision_id, opportunity_id, action, "
                "decided_by, decided_at) VALUES ('DEC-5', 'OPP-DEC-3', 'IGNORE', 'owner', :now)"
            ),
            {"now": _NOW},
        )
    update_message = _refused(
        engine,
        "UPDATE public.opportunity_decision SET decided_by = 'someone-else' "
        "WHERE decision_id = 'DEC-5'",
    )
    assert "append-only" in update_message or "violates" in update_message
    delete_message = _refused(
        engine, "DELETE FROM public.opportunity_decision WHERE decision_id = 'DEC-5'"
    )
    assert "append-only" in delete_message or "violates" in delete_message


# ---------------------------------------------------------------------------
# The full round trip through the real repositories
# ---------------------------------------------------------------------------


def test_the_full_round_trip_through_the_repositories(world: dict[str, object]) -> None:
    runtime: PostgresOpportunityEngineRuntime = world["runtime"]  # type: ignore[assignment]
    # The hard fields are computed and stored from the start (Phase 8-11 already ran); only
    # `status` itself is still CANDIDATE, e.g. pending a final freshness re-check before the
    # usecase layer marks it ACTIONABLE for real -- this is the only shape a CANDIDATE ->
    # ACTIONABLE transition can legally reach, since the CHECK constraint judges the FINAL row
    # image, not the transition path.
    fields = _actionable_fields()
    fields["status"] = OpportunityStatus.CANDIDATE
    candidate = _a_candidate_opportunity(opportunity_id="OPP-ROUNDTRIP-1", **fields)
    saved = runtime.opportunities.save(candidate)
    assert saved == candidate

    fetched = runtime.opportunities.get("OPP-ROUNDTRIP-1")
    assert fetched == candidate

    session_date = _NOW.date().isoformat()
    latest = runtime.opportunities.latest_for_symbol_today("AAPL", session_date=session_date)
    assert latest is not None and latest.opportunity_id == "OPP-ROUNDTRIP-1"

    listed = runtime.opportunities.list_for_session(session_date)
    assert any(o.opportunity_id == "OPP-ROUNDTRIP-1" for o in listed)

    actionable = runtime.opportunities.transition(
        opportunity_id="OPP-ROUNDTRIP-1", target=OpportunityStatus.ACTIONABLE, at=_NOW
    )
    assert actionable.status is OpportunityStatus.ACTIONABLE

    # A genuine CANDIDATE with NO hard fields populated cannot be transitioned to ACTIONABLE:
    # the trigger allows the status move, but the CHECK constraint on the resulting row image
    # refuses it -- the usecase layer must have already written the hard fields before ever
    # marking a row ACTIONABLE for real.
    bare_candidate = _a_candidate_opportunity(opportunity_id="OPP-ROUNDTRIP-1B")
    runtime.opportunities.save(bare_candidate)
    with pytest.raises(Exception) as excinfo:
        runtime.opportunities.transition(
            opportunity_id="OPP-ROUNDTRIP-1B", target=OpportunityStatus.ACTIONABLE, at=_NOW
        )
    underlying = str(excinfo.value.__cause__ or excinfo.value)
    assert "ck_opportunity_actionable_fields_present" in underlying or "violates" in underlying


def test_the_full_round_trip_with_actionable_fields_through_to_owner_approved(
    world: dict[str, object],
) -> None:
    runtime: PostgresOpportunityEngineRuntime = world["runtime"]  # type: ignore[assignment]
    opportunity = _a_candidate_opportunity(opportunity_id="OPP-ROUNDTRIP-3", **_actionable_fields())
    runtime.opportunities.save(opportunity)
    approved = runtime.opportunities.transition(
        opportunity_id="OPP-ROUNDTRIP-3", target=OpportunityStatus.OWNER_APPROVED, at=_NOW
    )
    assert approved.status is OpportunityStatus.OWNER_APPROVED

    decision = OpportunityDecision(
        decision_id="DEC-ROUNDTRIP-1",
        opportunity_id="OPP-ROUNDTRIP-3",
        action=OwnerOpportunityAction.APPROVE,
        decided_by="owner",
        decided_at=_NOW,
    )
    saved_decision = runtime.decisions.save(decision)
    assert saved_decision == decision
    fetched_decision = runtime.decisions.for_opportunity("OPP-ROUNDTRIP-3")
    assert fetched_decision == decision


def test_a_rejected_opportunity_round_trips_with_its_reasons(world: dict[str, object]) -> None:
    runtime: PostgresOpportunityEngineRuntime = world["runtime"]  # type: ignore[assignment]
    rejected = _a_candidate_opportunity(
        opportunity_id="OPP-ROUNDTRIP-4",
        status=OpportunityStatus.REJECTED,
        rejection_reasons=(
            RejectionReason.INSUFFICIENT_LIQUIDITY,
            RejectionReason.QUOTE_STALE_OR_INVALID,
        ),
    )
    saved = runtime.opportunities.save(rejected)
    assert saved.rejection_reasons == rejected.rejection_reasons
    assert saved.status is OpportunityStatus.REJECTED
