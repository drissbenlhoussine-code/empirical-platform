"""MILESTONE-076 -- operator-asserted position ledger, pure rule.

Every test targets a specific attack from the M076 mission brief or the
pre-implementation design review. Happy paths are the minority.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.operator_position_ledger import (
    OPERATOR_LEDGER_BANNER,
    LedgerRejectionError,
    LedgerRejectionReason,
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
    derive_position_state,
    validate_appended_event,
)

_T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _ev(
    gid: str,
    kind: str,
    *,
    pos: str = "POS-1",
    symbol: str = "AAPL",
    qty: int = 100,
    price: str = "150",
    day: int = 0,
    plan: str | None = None,
) -> OperatorAssertedPositionEvent:
    return OperatorAssertedPositionEvent(
        governance_id=gid,
        runtime_id=f"RT-{gid}",
        position_governance_id=pos,
        instrument_symbol=symbol,
        kind=OperatorPositionEventKind[kind],
        quantity=qty,
        asserted_price=Decimal(price),
        event_timestamp=_T0 + timedelta(days=day),
        recorded_at=_T0 + timedelta(days=30),
        source_position_plan_governance_id=plan,
    )


# --------------------------------------------------------------------------
# The lifecycle
# --------------------------------------------------------------------------


def test_open_reduce_close_walks_the_full_lifecycle() -> None:
    opened = _ev("E1", "OPENED", qty=100, day=0)
    reduced = _ev("E2", "REDUCED", qty=40, day=2)
    closed = _ev("E3", "CLOSED", qty=0, day=4)

    after_open = derive_position_state(events=(opened,), as_of=_T0 + timedelta(days=1))
    assert after_open.open_positions[0].open_quantity == 100
    assert after_open.total_asserted_open_notional == "15000"

    after_reduce = derive_position_state(events=(opened, reduced), as_of=_T0 + timedelta(days=3))
    assert after_reduce.open_positions[0].open_quantity == 60
    assert after_reduce.total_asserted_open_notional == "9000"

    after_close = derive_position_state(
        events=(opened, reduced, closed), as_of=_T0 + timedelta(days=5)
    )
    assert after_close.open_positions == ()
    assert len(after_close.closed_positions) == 1
    assert after_close.total_open_quantity == 0


def test_a_reduction_landing_exactly_on_zero_closes_the_position() -> None:
    """D03: otherwise a phantom zero-quantity position stays 'open'."""
    events = (_ev("E1", "OPENED", qty=100), _ev("E2", "REDUCED", qty=100, day=1))
    state = derive_position_state(events=events, as_of=_T0 + timedelta(days=2))
    assert state.open_positions == ()
    assert len(state.closed_positions) == 1


# --------------------------------------------------------------------------
# Temporal / as_of
# --------------------------------------------------------------------------


def test_as_of_is_inclusive_at_the_exact_boundary() -> None:
    state = derive_position_state(events=(_ev("E1", "OPENED"),), as_of=_T0)
    assert state.open_positions[0].open_quantity == 100


def test_future_events_are_excluded_from_a_past_as_of() -> None:
    """The row already exists, but a query about the past must not see it."""
    events = (_ev("E1", "OPENED", qty=100), _ev("E2", "CLOSED", qty=0, day=5))
    state = derive_position_state(events=events, as_of=_T0 + timedelta(days=1))
    assert state.open_positions[0].open_quantity == 100
    assert state.excluded_future_event_count == 1
    assert any("after the requested as_of" in x for x in state.limitations)


def test_recorded_at_never_affects_derived_state() -> None:
    """D16: only `event_timestamp` drives the fold."""
    early = _ev("E1", "OPENED")
    late_record = OperatorAssertedPositionEvent(
        governance_id="E1",
        runtime_id="RT-E1",
        position_governance_id="POS-1",
        instrument_symbol="AAPL",
        kind=OperatorPositionEventKind.OPENED,
        quantity=100,
        asserted_price=Decimal("150"),
        event_timestamp=_T0,
        recorded_at=_T0 + timedelta(days=999),
    )
    a = derive_position_state(events=(early,), as_of=_T0 + timedelta(days=1))
    b = derive_position_state(events=(late_record,), as_of=_T0 + timedelta(days=1))
    assert a.open_positions[0].open_quantity == b.open_positions[0].open_quantity


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_result_is_independent_of_input_order() -> None:
    events = (_ev("E1", "OPENED"), _ev("E2", "REDUCED", qty=30, day=1))
    assert derive_position_state(
        events=events, as_of=_T0 + timedelta(days=2)
    ) == derive_position_state(events=tuple(reversed(events)), as_of=_T0 + timedelta(days=2))


def test_timestamp_ties_are_broken_deterministically_by_governance_id() -> None:
    """D04: two events at the identical instant must still order totally."""
    a = _ev("E-AAA", "OPENED", pos="P1", qty=10)
    b = _ev("E-BBB", "REDUCED", pos="P1", qty=4)
    assert a.event_timestamp == b.event_timestamp
    state = derive_position_state(events=(b, a), as_of=_T0 + timedelta(days=1))
    assert state.open_positions[0].open_quantity == 6


def test_multiple_instruments_and_positions_are_kept_separate() -> None:
    events = (
        _ev("E1", "OPENED", pos="P1", symbol="AAPL", qty=10, price="100"),
        _ev("E2", "OPENED", pos="P2", symbol="MSFT", qty=5, price="200"),
    )
    state = derive_position_state(events=events, as_of=_T0 + timedelta(days=1))
    assert [p.instrument_symbol for p in state.open_positions] == ["AAPL", "MSFT"]
    assert state.total_open_quantity == 15
    assert state.total_asserted_open_notional == "2000"


# --------------------------------------------------------------------------
# Impossible transitions
# --------------------------------------------------------------------------


def test_reduction_exceeding_open_quantity_is_rejected() -> None:
    with pytest.raises(LedgerRejectionError) as exc:
        validate_appended_event(
            existing=(_ev("E1", "OPENED", qty=50),),
            candidate=_ev("E2", "REDUCED", qty=51, day=1),
        )
    assert exc.value.reason is LedgerRejectionReason.REDUCTION_EXCEEDS_OPEN_QUANTITY


def test_second_close_is_rejected() -> None:
    existing = (_ev("E1", "OPENED"), _ev("E2", "CLOSED", qty=0, day=1))
    with pytest.raises(LedgerRejectionError) as exc:
        validate_appended_event(existing=existing, candidate=_ev("E3", "CLOSED", qty=0, day=2))
    assert exc.value.reason is LedgerRejectionReason.POSITION_ALREADY_CLOSED


def test_reduce_without_an_open_is_rejected() -> None:
    with pytest.raises(LedgerRejectionError) as exc:
        validate_appended_event(existing=(), candidate=_ev("E1", "REDUCED", qty=5))
    assert exc.value.reason is LedgerRejectionReason.POSITION_NOT_OPEN


def test_reopening_a_closed_key_is_rejected() -> None:
    """D14: a re-entry needs a NEW position id, never a resurrection."""
    existing = (_ev("E1", "OPENED"), _ev("E2", "CLOSED", qty=0, day=1))
    with pytest.raises(LedgerRejectionError) as exc:
        validate_appended_event(existing=existing, candidate=_ev("E3", "OPENED", day=2))
    assert exc.value.reason is LedgerRejectionReason.POSITION_ALREADY_CLOSED


def test_double_open_on_a_live_key_is_rejected() -> None:
    with pytest.raises(LedgerRejectionError) as exc:
        validate_appended_event(
            existing=(_ev("E1", "OPENED"),), candidate=_ev("E2", "OPENED", day=1)
        )
    assert exc.value.reason is LedgerRejectionReason.POSITION_ALREADY_OPEN


def test_backdated_event_that_would_invalidate_a_later_one_is_rejected() -> None:
    """D05, the sharpest hole: validating only against state-at-this-timestamp
    would accept this and silently produce an incoherent ledger."""
    existing = (
        _ev("E1", "OPENED", day=0),
        _ev("E2", "CLOSED", qty=0, day=4),
    )
    with pytest.raises(LedgerRejectionError) as exc:
        validate_appended_event(existing=existing, candidate=_ev("E3", "OPENED", day=2))
    assert exc.value.reason is LedgerRejectionReason.POSITION_ALREADY_OPEN


def test_instrument_mismatch_within_one_position_key_is_rejected() -> None:
    """D08: a reduction must not cite a different instrument than its opening."""
    with pytest.raises(LedgerRejectionError) as exc:
        validate_appended_event(
            existing=(_ev("E1", "OPENED", symbol="AAPL"),),
            candidate=_ev("E2", "REDUCED", symbol="MSFT", qty=10, day=1),
        )
    assert exc.value.reason is LedgerRejectionReason.INSTRUMENT_MISMATCH_FOR_POSITION


def test_duplicate_governance_id_is_rejected() -> None:
    with pytest.raises(LedgerRejectionError) as exc:
        validate_appended_event(
            existing=(_ev("E1", "OPENED"),), candidate=_ev("E1", "REDUCED", qty=5, day=1)
        )
    assert exc.value.reason is LedgerRejectionReason.DUPLICATE_EVENT_GOVERNANCE_ID


@pytest.mark.parametrize("kind", ["OPENED", "REDUCED"])
@pytest.mark.parametrize("qty", [0, -5])
def test_non_positive_quantity_is_rejected_at_construction(kind: str, qty: int) -> None:
    with pytest.raises(LedgerRejectionError) as exc:
        _ev("E1", kind, qty=qty)
    assert exc.value.reason is LedgerRejectionReason.NON_POSITIVE_QUANTITY


# --------------------------------------------------------------------------
# The closing quantity is derived, never supplied
# --------------------------------------------------------------------------


def test_closing_quantity_is_derived_not_taken_from_the_operator() -> None:
    """D02: a supplied close quantity could otherwise disagree with reality."""
    existing = (_ev("E1", "OPENED", qty=100), _ev("E2", "REDUCED", qty=30, day=1))
    derived = validate_appended_event(
        existing=existing,
        candidate=_ev("E3", "CLOSED", qty=999999, day=2),  # nonsense on purpose
    )
    assert derived == 70


# --------------------------------------------------------------------------
# Empty state and honesty
# --------------------------------------------------------------------------


def test_empty_ledger_is_an_explicit_empty_state_not_an_error() -> None:
    state = derive_position_state(events=(), as_of=_T0)
    assert state.open_positions == ()
    assert state.closed_positions == ()
    assert state.total_open_quantity == 0
    assert state.considered_event_count == 0


def test_lineage_is_optional_and_never_changes_the_fold() -> None:
    """A cited plan records motivation only. It must not alter behaviour."""
    without = derive_position_state(events=(_ev("E1", "OPENED"),), as_of=_T0 + timedelta(days=1))
    with_plan = derive_position_state(
        events=(_ev("E1", "OPENED", plan="POS-PLAN-9"),), as_of=_T0 + timedelta(days=1)
    )
    assert without.open_positions == with_plan.open_positions


def test_banner_disclaims_everything_a_reader_might_assume() -> None:
    lowered = OPERATOR_LEDGER_BANNER.lower()
    for clause in (
        "not a broker record",
        "not a verified fill",
        "not an execution",
        "not realized or unrealized p&l",
        "not a market valuation",
        "not a paper-trading claim",
        "not a profitability claim",
        "not advice",
    ):
        assert clause in lowered


def test_module_never_claims_execution_or_live_semantics() -> None:
    """The vocabulary must stay honest: nothing here was executed or filled."""
    from empirical_platform.decision_candidate import operator_position_ledger as module

    names = {member.value for member in OperatorPositionEventKind}
    assert names == {"OPENED", "REDUCED", "CLOSED"}
    for forbidden in ("EXECUTED", "FILLED", "LIVE_", "BROKER_"):
        assert forbidden not in names
    assert "asserted" in module.__doc__.lower()


def test_notional_is_labelled_as_asserted_not_market_value() -> None:
    """D09: this number must never be read as a market value or P&L."""
    state = derive_position_state(
        events=(_ev("E1", "OPENED", qty=3, price="10.5"),), as_of=_T0 + timedelta(days=1)
    )
    assert state.open_positions[0].asserted_open_notional == "31.5"
    assert any("not a market value and not P&L" in x for x in state.limitations)


# --------------------------------------------------------------------------
# Regressions for defects that only integration testing exposed
# --------------------------------------------------------------------------


def test_rejection_error_is_raisable_and_stringifiable() -> None:
    """Regression: `LedgerRejectionError` was a slotted dataclass over
    `Exception`. `@dataclass(slots=True)` rebuilds the class object, which broke
    `super()` resolution and made the error raise `TypeError` when pytest tried
    to render it. It is now a plain exception."""
    error = LedgerRejectionError(
        reason=LedgerRejectionReason.POSITION_NOT_OPEN, detail="nothing open"
    )
    assert isinstance(error, Exception)
    assert str(error) == "POSITION_NOT_OPEN: nothing open"
    assert repr(error)
    with pytest.raises(LedgerRejectionError):
        raise error


def test_money_strings_are_canonical_regardless_of_scale() -> None:
    """Regression: PostgreSQL NUMERIC(20,6) returns Decimal('750.000000'),
    which is == Decimal('750') but str()s differently, so the same position
    rendered from memory and from the database disagreed."""
    from_memory = derive_position_state(
        events=(_ev("E1", "OPENED", qty=3, price="250"),), as_of=_T0 + timedelta(days=1)
    )
    from_database = derive_position_state(
        events=(_ev("E2", "OPENED", qty=3, price="250.000000"),),
        as_of=_T0 + timedelta(days=1),
    )
    assert from_memory.total_asserted_open_notional == "750"
    assert from_memory.total_asserted_open_notional == from_database.total_asserted_open_notional
    assert (
        from_memory.open_positions[0].asserted_entry_price
        == from_database.open_positions[0].asserted_entry_price
    )
    # and fractional values keep their significant digits
    fractional = derive_position_state(
        events=(_ev("E3", "OPENED", qty=2, price="10.25"),), as_of=_T0 + timedelta(days=1)
    )
    assert fractional.total_asserted_open_notional == "20.5"


def test_no_identifier_type_lost_its_prefix() -> None:
    """Regression for a real defect introduced while building M076: appending
    `OperatorPositionEventId` landed between `ResearchSessionId`'s docstring and
    its `prefix = "RESEARCH"`, so ResearchSessionId silently inherited the empty
    base prefix (pattern `^-\\d{4}$`) and the new class stole `RESEARCH`. It
    broke 74 previously-passing tests. This asserts the whole registry, so any
    future append cannot repeat it."""
    import inspect

    from empirical_platform.identifiers import types

    empty = [
        name
        for name, obj in vars(types).items()
        if inspect.isclass(obj)
        and issubclass(obj, types.Identifier)
        and obj is not types.Identifier
        and not obj.prefix
    ]
    assert empty == []
    assert types.ResearchSessionId.prefix == "RESEARCH"
    assert types.OperatorPositionEventId.prefix == "OPEV"
    assert str(types.OperatorPositionEventId("OPEV-7601")) == "OPEV-7601"


# --------------------------------------------------------------------------
# MILESTONE-076 owner correction -- Finding 2: timezone invariant
# --------------------------------------------------------------------------


def test_naive_event_timestamp_is_refused_at_the_domain_boundary() -> None:
    with pytest.raises(LedgerRejectionError) as exc:
        OperatorAssertedPositionEvent(
            governance_id="E1",
            runtime_id="R1",
            position_governance_id="P1",
            instrument_symbol="AAPL",
            kind=OperatorPositionEventKind.OPENED,
            quantity=1,
            asserted_price=Decimal("10"),
            event_timestamp=datetime(2026, 3, 1),  # noqa: DTZ001 - the attack
            recorded_at=_T0,
        )
    assert exc.value.reason is LedgerRejectionReason.NAIVE_TIMESTAMP


def test_naive_recorded_at_is_refused_at_the_domain_boundary() -> None:
    with pytest.raises(LedgerRejectionError) as exc:
        OperatorAssertedPositionEvent(
            governance_id="E1",
            runtime_id="R1",
            position_governance_id="P1",
            instrument_symbol="AAPL",
            kind=OperatorPositionEventKind.OPENED,
            quantity=1,
            asserted_price=Decimal("10"),
            event_timestamp=_T0,
            recorded_at=datetime(2026, 3, 1),  # noqa: DTZ001 - the attack
        )
    assert exc.value.reason is LedgerRejectionReason.NAIVE_TIMESTAMP


def test_naive_as_of_is_refused() -> None:
    with pytest.raises(LedgerRejectionError) as exc:
        derive_position_state(events=(), as_of=datetime(2026, 3, 1))  # noqa: DTZ001
    assert exc.value.reason is LedgerRejectionReason.NAIVE_TIMESTAMP


def test_different_offsets_for_the_same_instant_behave_identically() -> None:
    """A single instant expressed two ways must fold to the same state, and the
    inclusive `as_of` boundary must hold across offsets."""
    utc_moment = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    plus_two = datetime(2026, 3, 5, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    assert utc_moment == plus_two
    event = OperatorAssertedPositionEvent(
        governance_id="E1",
        runtime_id="R1",
        position_governance_id="P1",
        instrument_symbol="AAPL",
        kind=OperatorPositionEventKind.OPENED,
        quantity=8,
        asserted_price=Decimal("10"),
        event_timestamp=plus_two,
        recorded_at=utc_moment,
    )
    assert derive_position_state(events=(event,), as_of=utc_moment).total_open_quantity == 8
    assert derive_position_state(events=(event,), as_of=plus_two).total_open_quantity == 8
    just_before = utc_moment - timedelta(microseconds=1)
    assert derive_position_state(events=(event,), as_of=just_before).total_open_quantity == 0


# --------------------------------------------------------------------------
# MILESTONE-076 owner correction -- Finding 3: price invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize("price", ["0", "-1", "-0.000001"])
def test_non_positive_price_is_a_domain_invariant_not_only_a_db_check(price: str) -> None:
    with pytest.raises(LedgerRejectionError) as exc:
        _ev("E1", "OPENED", price=price)
    assert exc.value.reason is LedgerRejectionReason.NON_POSITIVE_ASSERTED_PRICE


@pytest.mark.parametrize("price", ["1.1234567", "0.00000001", "100.123456789"])
def test_price_beyond_the_persisted_scale_is_refused(price: str) -> None:
    """NUMERIC(20,6) would round these, so an accepted value would reload as a
    different one and break deterministic replay."""
    with pytest.raises(LedgerRejectionError) as exc:
        _ev("E1", "OPENED", price=price)
    assert exc.value.reason is LedgerRejectionReason.ASSERTED_PRICE_PRECISION_EXCEEDED


@pytest.mark.parametrize("price", ["1", "1.5", "0.000001", "123.456789", "99999999999.999999"])
def test_prices_within_the_persisted_scale_are_accepted(price: str) -> None:
    assert _ev("E1", "OPENED", price=price).asserted_price == Decimal(price)


def test_max_precision_survives_the_canonical_money_rendering() -> None:
    state = derive_position_state(
        events=(_ev("E1", "OPENED", qty=1, price="123.456789"),),
        as_of=_T0 + timedelta(days=1),
    )
    assert state.open_positions[0].asserted_entry_price == "123.456789"
    assert state.open_positions[0].asserted_open_notional == "123.456789"
