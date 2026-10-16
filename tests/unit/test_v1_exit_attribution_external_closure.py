"""RELEASE v1 EXTERNAL POSITION CLOSURE ATTRIBUTION FIX.

INCIDENT (2026-10-14 / 2026-10-16): the Oct 9 AAPL Paper entry
(`INT-PRP-089-PAPER-20261009T172613Z`) was FILLED, had an `ExternalPositionClosure`
recorded for it on Oct 14 (an Owner manual broker-dashboard sale this platform never
dispatched), and had ZERO `PositionExitAttempt` rows. `AssessPositionExitHandler._competitors()`
decided competition purely from `PositionExitAttempt`, never consulted
`ExternalPositionClosureRepository`, so it wrongly counted the Oct 9 entry as a still-open
competitor for the Oct 16 entry (`INT-PRP-089-PAPER-20261016T153856Z`) opened in the SAME
symbol -- `exit_eligibility` then refused the Oct 16 exit with "another entry in the same
symbol also holds shares (...); attribution is ambiguous", which is why the live
`PositionPlanManager` never dispatched the Oct 16 position's MANDATORY_EXIT.

These tests reproduce that exact shape with pure in-memory fakes -- no broker, no
Postgres, no simulation -- for every dependency `AssessPositionExitHandler` reads, so the
reproduction and the fix are provable in milliseconds. The full Postgres/`PositionPlanManager`
end-to-end proof lives in
`tests/integration/test_v1_exit_attribution_external_closure_postgres.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tests.unit._m085_fakes import an_intent
from tests.unit._v1_fakes import FakeExternalPositionClosures
from tests.unit.test_m087_position_exit_domain import an_attempt

from empirical_platform.decision_candidate.external_position_closure import (
    ExternalPositionClosure,
    external_position_closure_id,
)
from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionState,
)
from empirical_platform.decision_candidate.position_exit import PositionExitState
from empirical_platform.decision_candidate.trade_approval import ApprovedOrderIntent
from empirical_platform.usecases.operator_console_exits import (
    CATEGORY_EXPIRED_UNSUBMITTED,
    CATEGORY_EXTERNALLY_CLOSED,
    CATEGORY_OPEN_POSITION,
    CATEGORY_WORKING_ENTRY,
    ExitRepositories,
    PositionExitConsole,
)
from empirical_platform.usecases.position_exit import AssessPositionExitHandler

_NOW = datetime(2026, 10, 16, 20, 0, tzinfo=UTC)
_OCT9 = "INT-PRP-089-PAPER-20261009T172613Z"
_OCT16 = "INT-PRP-089-PAPER-20261016T153856Z"
_SYMBOL = "AAPL"


# ---------------------------------------------------------------------------
# Pure in-memory fakes -- exactly the methods AssessPositionExitHandler reads
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _FakePosition:
    symbol: str
    quantity: int


class _FakeBroker:
    def __init__(self, *, quantity: int) -> None:
        self._quantity = quantity

    def fetch_position(self, symbol: str) -> _FakePosition | None:
        return (
            None if self._quantity == 0 else _FakePosition(symbol=symbol, quantity=self._quantity)
        )


class _FakeIntents:
    def __init__(self, rows: dict[str, ApprovedOrderIntent]) -> None:
        self._rows = rows

    def get(self, intent_governance_id: str) -> ApprovedOrderIntent | None:
        return self._rows.get(intent_governance_id)


class _FakeEntryAttempts:
    def __init__(self, rows: dict[str, ExecutionAttempt]) -> None:
        self._rows = rows

    def for_intent(self, intent_governance_id: str) -> ExecutionAttempt | None:
        return next(
            (a for a in self._rows.values() if a.intent_governance_id == intent_governance_id),
            None,
        )

    def list_recent(self, limit: int) -> tuple[ExecutionAttempt, ...]:
        return tuple(self._rows.values())[:limit]


class _FakeExitAttempts:
    """No platform exit attempt exists for anyone, unless `active` says otherwise -- the
    EXACT live-incident shape for the Oct 9 entry (externally closed, zero exit attempts)."""

    def __init__(self, active: dict[str, object] | None = None) -> None:
        self._active = dict(active or {})

    def for_entry(self, entry_intent_governance_id: str) -> tuple[object, ...]:
        attempt = self._active.get(entry_intent_governance_id)
        return (attempt,) if attempt is not None else ()

    def active_for_entry(self, entry_intent_governance_id: str) -> object | None:
        return self._active.get(entry_intent_governance_id)


def _filled_attempt(
    *, attempt_id: str, intent_id: str, quantity: int, price: str
) -> ExecutionAttempt:
    return ExecutionAttempt(
        attempt_id=attempt_id,
        intent_governance_id=intent_id,
        authorization_id=f"AUT-{attempt_id}",
        client_order_id=f"m085-{attempt_id}",
        request_fingerprint="a" * 64,
        state=PaperExecutionState.FILLED,
        claimed_at=_NOW - timedelta(days=1),
        submitted_at=_NOW - timedelta(days=1),
        acknowledged_at=_NOW - timedelta(days=1),
        terminal_at=_NOW - timedelta(days=1),
        broker_order_id=f"SIM-{attempt_id}",
        broker_status="filled",
        filled_quantity=Decimal(quantity),
        filled_avg_price=Decimal(price),
        failure_code=None,
        failure_detail=None,
    )


def _closure(entry_intent_governance_id: str, *, recorded_at: datetime) -> ExternalPositionClosure:
    return ExternalPositionClosure(
        closure_id=external_position_closure_id(entry_intent_governance_id),
        entry_intent_governance_id=entry_intent_governance_id,
        symbol=_SYMBOL,
        quantity=1,
        broker_order_id="BRK-EXTERNAL-SELL-1",
        client_order_id="EXTERNAL-SELL-1",
        filled_avg_price=Decimal("229.50"),
        recorded_by="owner",
        recorded_at=recorded_at,
    )


def _handler(
    *, oct9_closed: bool, broker_quantity: int, exit_attempts: _FakeExitAttempts | None = None
) -> AssessPositionExitHandler:
    oct9_intent = an_intent(
        intent_governance_id=_OCT9,
        proposal_governance_id="PRP-089-PAPER-20261009T172613Z",
        decision_governance_id="DEC-OCT9",
        idempotency_key="IDEM-OCT9",
        created_at=_NOW - timedelta(days=7),
        expires_at=_NOW - timedelta(days=7) + timedelta(minutes=30),
        mandatory_liquidation_at=_NOW - timedelta(days=6, hours=18),
    )
    oct16_intent = an_intent(
        intent_governance_id=_OCT16,
        proposal_governance_id="PRP-089-PAPER-20261016T153856Z",
        decision_governance_id="DEC-OCT16",
        idempotency_key="IDEM-OCT16",
        created_at=_NOW - timedelta(hours=6),
        expires_at=_NOW - timedelta(hours=5, minutes=30),
        mandatory_liquidation_at=_NOW + timedelta(hours=2),
    )
    intents = _FakeIntents({_OCT9: oct9_intent, _OCT16: oct16_intent})
    entry_attempts = _FakeEntryAttempts(
        {
            "ATT-OCT9": _filled_attempt(
                attempt_id="ATT-OCT9", intent_id=_OCT9, quantity=1, price="227.40"
            ),
            "ATT-OCT16": _filled_attempt(
                attempt_id="ATT-OCT16", intent_id=_OCT16, quantity=1, price="230.10"
            ),
        }
    )
    closures = FakeExternalPositionClosures()
    if oct9_closed:
        closures.save(_closure(_OCT9, recorded_at=_NOW - timedelta(days=2)))
    broker = _FakeBroker(quantity=broker_quantity)
    return AssessPositionExitHandler(
        intents=intents,
        entry_attempts=entry_attempts,
        exit_attempts=exit_attempts or _FakeExitAttempts(),
        external_closures=closures,
        broker=broker,
    )


# ---------------------------------------------------------------------------
# The live-incident reproduction and its fix
# ---------------------------------------------------------------------------


def test_before_the_fix_shape_a_closed_old_entry_with_no_exit_attempt_still_blocked() -> None:
    """Regression guard for the REAL protection: an old FILLED entry with NO recorded
    external closure and NO platform exit attempt is STILL a genuine, ambiguous competitor
    -- the fix must never let attribution cross entries just because of silence."""
    handler = _handler(oct9_closed=False, broker_quantity=1)
    assessment = handler.handle(_OCT16, at=_NOW)
    assert not assessment.eligible
    assert assessment.snapshot.competing_entry_attempt_ids == ("ATT-OCT9",)
    assert any("ambiguous" in r for r in assessment.refusals), assessment.refusals


def test_the_fix_the_externally_closed_old_entry_no_longer_blocks_the_new_entry() -> None:
    """The actual fix: once the Oct 9 entry's closure is durably recorded, it is excluded
    from `competing_entry_attempt_ids` and the Oct 16 entry assesses as eligible."""
    handler = _handler(oct9_closed=True, broker_quantity=1)
    assessment = handler.handle(_OCT16, at=_NOW)
    assert assessment.eligible, assessment.refusals
    assert assessment.snapshot.competing_entry_attempt_ids == ()
    assert assessment.snapshot.attributable_quantity == 1


def test_the_closed_entry_itself_is_refused_unconditionally_even_if_the_broker_shows_shares() -> (
    None
):
    """Requirement 3: a DIRECT exit request for the Oct 9 entry is refused unconditionally
    once its own closure is recorded -- even though the broker CURRENTLY shows a nonzero
    AAPL position (the Oct 16 entry's own, live, legitimate holding)."""
    handler = _handler(oct9_closed=True, broker_quantity=1)
    assessment = handler.handle(_OCT9, at=_NOW)
    assert not assessment.eligible
    assert assessment.refusals == (
        "this entry's position was already closed externally (closure "
        f"{external_position_closure_id(_OCT9)!r}); it can never be exited again through "
        "this platform",
    )


def test_attribution_never_crosses_entries_once_closed() -> None:
    """Closing the OLD entry can never make the broker's shares look like THEY belong to
    it again -- the NEW entry's own assessment is always judged on its OWN fill/exit
    evidence, never the old entry's."""
    handler = _handler(oct9_closed=True, broker_quantity=1)
    oct16 = handler.handle(_OCT16, at=_NOW)
    assert oct16.snapshot.entry_intent_governance_id == _OCT16
    assert oct16.snapshot.entry_filled_quantity == Decimal(1)
    assert oct16.snapshot.broker_position_quantity == 1
    assert oct16.eligible


def test_a_non_terminal_platform_exit_for_the_old_entry_still_counts_as_a_competitor() -> None:
    """The PositionExitAttempt-based exclusion stays exactly as strict as before: an
    in-flight, non-terminal or unresolved platform exit for the OTHER entry must still
    block -- only a VERIFIED `position_closed` exit (or an external closure) may exclude."""
    unresolved = an_attempt(
        attempt_id="XAT-OCT9",
        entry_intent_governance_id=_OCT9,
        state=PositionExitState.SUBMISSION_UNKNOWN,
    )
    handler = _handler(
        oct9_closed=False,
        broker_quantity=1,
        exit_attempts=_FakeExitAttempts({_OCT9: unresolved}),
    )
    assessment = handler.handle(_OCT16, at=_NOW)
    assert not assessment.eligible
    assert assessment.snapshot.competing_entry_attempt_ids == ("ATT-OCT9",)


# ---------------------------------------------------------------------------
# Visibility: OperatorConsoleExits.category() (now PositionExitConsole.category())
# ---------------------------------------------------------------------------


def _bare_console(external_closures: FakeExternalPositionClosures) -> PositionExitConsole:
    """A `PositionExitConsole` built only well enough to exercise `category()`, which reads
    only `self._external_closures` and its own arguments -- every unrelated dependency is a
    deliberately-unused stand-in."""
    return PositionExitConsole(
        exits=ExitRepositories(
            previews=None,  # type: ignore[arg-type]
            authorizations=None,  # type: ignore[arg-type]
            attempts=None,  # type: ignore[arg-type]
            acknowledgements=None,  # type: ignore[arg-type]
            rounds=None,  # type: ignore[arg-type]
            events=None,  # type: ignore[arg-type]
        ),
        intents=None,  # type: ignore[arg-type]
        entry_attempts=None,  # type: ignore[arg-type]
        external_closures=external_closures,
        configurations=None,  # type: ignore[arg-type]
        kill_switch=None,  # type: ignore[arg-type]
        broker=None,  # type: ignore[arg-type]
        market_data=None,  # type: ignore[arg-type]
        signer=None,  # type: ignore[arg-type]
        time_source=None,  # type: ignore[arg-type]
        clock=lambda: _NOW,
        environment="PAPER",
    )


def test_category_shows_closed_externally_even_with_no_platform_exit_attempt() -> None:
    closures = FakeExternalPositionClosures()
    closures.save(_closure(_OCT9, recorded_at=_NOW - timedelta(days=2)))
    console = _bare_console(closures)
    oct9_intent = an_intent(intent_governance_id=_OCT9)
    oct9_entry = _filled_attempt(attempt_id="ATT-OCT9", intent_id=_OCT9, quantity=1, price="227.40")
    category = console.category(oct9_intent, oct9_entry, None, now=_NOW)
    assert category == CATEGORY_EXTERNALLY_CLOSED


def test_category_without_a_closure_is_unaffected_open_position() -> None:
    console = _bare_console(FakeExternalPositionClosures())
    intent = an_intent(intent_governance_id=_OCT16)
    entry = _filled_attempt(attempt_id="ATT-OCT16", intent_id=_OCT16, quantity=1, price="230.10")
    assert console.category(intent, entry, None, now=_NOW) == CATEGORY_OPEN_POSITION


def test_category_marks_an_expired_never_submitted_intent_distinctly_from_working() -> None:
    expired_intent = an_intent(
        intent_governance_id="INT-EXPIRED",
        created_at=_NOW - timedelta(days=2),
        expires_at=_NOW - timedelta(days=1),
        mandatory_liquidation_at=_NOW - timedelta(hours=12),
    )
    console = _bare_console(FakeExternalPositionClosures())
    assert console.category(expired_intent, None, None, now=_NOW) == CATEGORY_EXPIRED_UNSUBMITTED


def test_category_still_shows_working_for_a_genuinely_fresh_unsubmitted_intent() -> None:
    fresh_intent = an_intent(
        intent_governance_id="INT-FRESH",
        created_at=_NOW - timedelta(minutes=5),
        expires_at=_NOW + timedelta(minutes=55),
        mandatory_liquidation_at=_NOW + timedelta(hours=4),
    )
    console = _bare_console(FakeExternalPositionClosures())
    assert console.category(fresh_intent, None, None, now=_NOW) == CATEGORY_WORKING_ENTRY
