"""MILESTONE-088 -- Paper Operator Console integration tests.

Categories, matching the mission's Phase 14:
  A. Dual-schema boundary (import isolation; the exact-head guard itself is M085's own,
     reused unchanged and already exhaustively tested there).
  B. Environment isolation (capability firewall; PAPER never touches the simulated adapter).
  C. Owner gate (staged review -> ticket -> confirm, deterministic identity).
  D. Exactly-once (a repeated confirmation does not dispatch twice).
  E. UI (explicit PAPER text, no credential leakage).
  F. Regressions live in the existing M085/M086/M087 suites (run separately; unaffected by
     anything here, since PAPER never composes over Store A or the simulated broker).

Everything here runs against IN-MEMORY fakes (`_m085_fakes.py`, `_m086_fakes.py`) -- no
PostgreSQL, no network. Nothing in this file can reach the real Alpaca paper endpoint.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.unit._m085_fakes import (
    FakeAcknowledgements,
    FakeAttempts,
    FakeAuthorizations,
    FakeBroker,
    FakeClock,
    FakeEvents,
    FakeKillSwitch,
    FakeMarketData,
    FakePreviews,
    FakeReconciliationRounds,
    FakeSnapshots,
    FakeTimeBases,
)
from tests.unit._m086_fakes import (
    MemoryConfigurations,
    MemoryContexts,
    MemoryDecisions,
    MemoryIntents,
    MemoryProposals,
    MemoryWatermarks,
)

from empirical_platform.decision_candidate.paper_execution import PAPER_ENDPOINT_HOST
from empirical_platform.decision_candidate.trade_proposal import TradeProposal
from empirical_platform.entrypoints._paper_operator_console_composition import PAPER_CAPABILITY
from empirical_platform.shared.brokerage.paper_time import SystemPaperTimeSource
from empirical_platform.usecases.operator_console import (
    CAPABILITIES,
    CapabilityRefusedError,
    ConsoleRepositories,
    ExecutionCapability,
    HmacSigner,
    OperatorConsoleService,
)
from empirical_platform.usecases.paper_operator_console import (
    APPROVED_SYMBOL,
    PaperHealthView,
    prepare_paper_candidate,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _now() -> datetime:
    # FakeBroker.fetch_clock() always returns REAL wall-clock time by M085 design (the
    # broker's clock is an independently-measured external fact, never assumed to match a
    # controllable host/test clock) -- so `now` here, and the fake quote's freshness below,
    # must track real time too, or the chronology guard (a REAL M085 safety check, not
    # weakened here) correctly refuses a deadline that looks already passed on the broker's
    # clock.
    return datetime.now(UTC)


@dataclass
class _FreshQuote:
    symbol: str = "AAPL"
    bid: str = "299.63"
    ask: str = "299.70"
    captured_at: datetime = None  # type: ignore[assignment]
    source: str = "alpaca-iex"

    def __post_init__(self) -> None:
        if self.captured_at is None:
            self.captured_at = _now() - timedelta(seconds=5)


@dataclass
class _OpenMarketClock:
    """FakeBroker.fetch_clock() patches only `.timestamp` to real time; `.next_open` and
    `.next_close` stay fixed to the fakes module's own historical constant, so `broker_now`
    looks like it is long past `next_close` once real time has moved on. This clock keeps
    all four fields consistent with real time, so the (real, unweakened) session-open check
    in `usecases.paper_execution` passes on its own honest terms."""

    is_open: bool = True
    timestamp: datetime = None  # type: ignore[assignment]
    next_open: datetime = None  # type: ignore[assignment]
    next_close: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        now = _now()
        if self.timestamp is None:
            self.timestamp = now
        if self.next_open is None:
            self.next_open = now + timedelta(hours=20)
        if self.next_close is None:
            self.next_close = now + timedelta(hours=2)


def _open_broker() -> FakeBroker:
    broker = FakeBroker()
    broker.fetch_clock = _OpenMarketClock  # type: ignore[method-assign]
    return broker


def _paper_repositories() -> ConsoleRepositories:
    attempts = FakeAttempts()
    acknowledgements = FakeAcknowledgements()
    events = FakeEvents()
    return ConsoleRepositories(
        configurations=MemoryConfigurations(),
        contexts=MemoryContexts(),
        proposals=MemoryProposals(),
        decisions=MemoryDecisions(),
        intents=MemoryIntents(),
        time_bases=FakeTimeBases(),
        snapshots=FakeSnapshots(),
        previews=FakePreviews(),
        authorizations=FakeAuthorizations(),
        attempts=attempts,
        acknowledgements=acknowledgements,
        events=events,
        rounds=FakeReconciliationRounds(attempts, acknowledgements, events),
        kill_switch=FakeKillSwitch(),
    )


def _paper_service(
    repositories: ConsoleRepositories, *, broker: FakeBroker, market_data: FakeMarketData
) -> OperatorConsoleService:
    return OperatorConsoleService(
        repositories=repositories,
        broker=broker,  # type: ignore[arg-type]
        market_data=market_data,  # type: ignore[arg-type]
        signer=HmacSigner(b"x" * 32),
        capability=PAPER_CAPABILITY,
        time_source=SystemPaperTimeSource(),
        exits=None,
    )


# ---------------------------------------------------------------------------
# A. Dual-schema boundary / B. Environment isolation
# ---------------------------------------------------------------------------


class TestEnvironmentIsolation:
    def test_paper_composition_never_imports_the_simulated_adapter(self) -> None:
        """Store B's composition has no import of the SIMULATION broker/market-data types,
        and no PostgreSQL config pointing at Store A -- proven from the source, not from
        runtime behaviour that could be coincidentally true."""
        source = (
            _REPO_ROOT
            / "src"
            / "empirical_platform"
            / "entrypoints"
            / "_paper_operator_console_composition.py"
        ).read_text(encoding="utf-8")
        assert "SimulatedPaperBroker" not in source
        assert "SimulatedMarketData" not in source
        assert "resolve_foundation_config" not in source  # Store A's own config resolver
        assert "_operator_console_composition" not in source  # M086/M087's own Store A module
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert "paper_execution_runtime" in imported  # Store B, and only Store B

    def test_the_capability_firewall_accepts_simulation_and_paper_never_live(self) -> None:
        repositories = _paper_repositories()
        broker = FakeBroker()
        market_data = FakeMarketData(quote=_FreshQuote())
        # PAPER, enabled: accepted.
        _paper_service(repositories, broker=broker, market_data=market_data)
        # LIVE can never be composed, even if somehow marked enabled -- there is no
        # CapabilityStatus in this codebase with capability=LIVE and enabled=True; this
        # test constructs the forbidden shape directly rather than trusting one is absent.
        from empirical_platform.usecases.operator_console import CapabilityStatus

        with pytest.raises(CapabilityRefusedError):
            OperatorConsoleService(
                repositories=repositories,
                broker=broker,  # type: ignore[arg-type]
                market_data=market_data,  # type: ignore[arg-type]
                signer=HmacSigner(b"x" * 32),
                capability=CapabilityStatus(ExecutionCapability.LIVE, True, "Live", "no"),
                exits=None,
            )
        # A disabled PAPER (the M086/M087 branches' own reality) is still refused.
        with pytest.raises(CapabilityRefusedError):
            OperatorConsoleService(
                repositories=repositories,
                broker=broker,  # type: ignore[arg-type]
                market_data=market_data,  # type: ignore[arg-type]
                signer=HmacSigner(b"x" * 32),
                capability=CAPABILITIES[1],  # PAPER, enabled=False
                exits=None,
            )

    def test_paper_exit_is_always_none_locked(self) -> None:
        service = _paper_service(
            _paper_repositories(),
            broker=_open_broker(),
            market_data=FakeMarketData(quote=_FreshQuote()),
        )
        assert service.exits is None

    def test_the_shared_capabilities_table_is_untouched_by_this_milestone(self) -> None:
        """M086's own displayed table still says PAPER is locked -- correct for the M086/M087
        branches, where it genuinely is not composed. PAPER_CAPABILITY is declared
        separately, and only carries `enabled=True` where THIS module actually built and
        verified Store B."""
        assert [c.enabled for c in CAPABILITIES] == [True, False, False]
        assert "Locked pending M085 Paper Acceptance" in CAPABILITIES[1].label
        assert PAPER_CAPABILITY.enabled is True
        assert PAPER_CAPABILITY.capability is ExecutionCapability.PAPER
        assert PAPER_CAPABILITY is not CAPABILITIES[1]

    def test_the_safety_view_shows_this_services_own_true_capability(self) -> None:
        repositories = _paper_repositories()
        service = _paper_service(
            repositories, broker=_open_broker(), market_data=FakeMarketData(quote=_FreshQuote())
        )
        view = service.safety("CFG-088-PAPER")
        paper_entry = next(
            c for c in view.capabilities if c.capability is ExecutionCapability.PAPER
        )
        assert paper_entry.enabled is True
        assert paper_entry is PAPER_CAPABILITY
        simulation_entry = next(
            c for c in view.capabilities if c.capability is ExecutionCapability.SIMULATION
        )
        assert simulation_entry is CAPABILITIES[0]  # untouched


# ---------------------------------------------------------------------------
# C. Owner gate / D. Exactly-once
# ---------------------------------------------------------------------------


class TestOwnerGateAndExactlyOnce:
    def _prepared(
        self, repositories: ConsoleRepositories, broker: FakeBroker, market_data: FakeMarketData
    ) -> TradeProposal:
        return prepare_paper_candidate(
            configurations=repositories.configurations,
            contexts=repositories.contexts,
            proposals=repositories.proposals,
            watermarks=MemoryWatermarks(),
            time_bases=repositories.time_bases,
            broker=broker,  # type: ignore[arg-type]
            market_data=market_data,  # type: ignore[arg-type]
            time_source=SystemPaperTimeSource(),
            now=_now(),
        )

    def test_prepare_candidate_writes_only_a_prepared_proposal(self) -> None:
        repositories = _paper_repositories()
        broker, market_data = _open_broker(), FakeMarketData(quote=_FreshQuote())
        proposal = self._prepared(repositories, broker, market_data)
        assert proposal.symbol == APPROVED_SYMBOL
        assert repositories.decisions.for_proposal(proposal.proposal_governance_id) is None
        assert repositories.intents.for_proposal(proposal.proposal_governance_id) is None
        assert len(repositories.attempts.rows) == 0  # nothing dispatched

    def test_prepare_candidate_is_idempotent_by_calendar_day(self) -> None:
        repositories = _paper_repositories()
        broker, market_data = _open_broker(), FakeMarketData(quote=_FreshQuote())
        first = self._prepared(repositories, broker, market_data)
        second = self._prepared(repositories, broker, market_data)
        assert first.proposal_governance_id == second.proposal_governance_id
        assert len(repositories.proposals.rows) == 1

    def test_prepare_candidate_refuses_a_closed_market_never_relaxing_the_bound(self) -> None:
        from empirical_platform.usecases.paper_operator_console import PaperCandidateBlockedError

        repositories = _paper_repositories()
        shut = FakeClock()
        shut.is_open = False  # type: ignore[misc]
        broker = FakeBroker()
        broker.fetch_clock = lambda: shut  # type: ignore[method-assign]
        with pytest.raises(PaperCandidateBlockedError):
            self._prepared(repositories, broker, FakeMarketData(quote=_FreshQuote()))
        assert len(repositories.proposals.rows) == 0

    def test_the_two_stage_gate_shows_the_exact_terms_and_the_same_id_on_confirm(self) -> None:
        """Phase 9: the deterministic client_order_id is derived from the frozen proposal's
        identity/fingerprint at CONFIRM time; the SAME identity is what dispatch addresses,
        proven here by the attempt recorded after confirm carrying the preview's own
        client_order_id, not a fresh one."""
        repositories = _paper_repositories()
        broker, market_data = _open_broker(), FakeMarketData(quote=_FreshQuote())
        proposal = self._prepared(repositories, broker, market_data)
        service = _paper_service(repositories, broker=broker, market_data=market_data)

        card = service.opportunity(proposal.proposal_governance_id)
        assert card.decision_available is True
        confirmation = service.prepare_approval(proposal.proposal_governance_id)
        assert confirmation.terms.symbol == APPROVED_SYMBOL
        assert confirmation.ticket  # a signed, single-use ticket, not a raw proposal id

        outcome = service.confirm_approval(proposal.proposal_governance_id, confirmation.ticket)
        assert outcome.ok is True
        assert outcome.intent_id is not None
        attempts_after_one = dict(repositories.attempts.rows)
        assert len(attempts_after_one) == 1
        assert len(broker.submitted) == 1
        dispatched_client_order_id = broker.submitted[0].client_order_id

        # D. Exactly-once: confirming again with the SAME ticket must not dispatch a second
        # order. The ticket is single-use in spirit; the handler chain is idempotent by
        # derived identity regardless.
        outcome_again = service.confirm_approval(
            proposal.proposal_governance_id, confirmation.ticket
        )
        assert outcome_again.intent_id == outcome.intent_id
        assert dict(repositories.attempts.rows) == attempts_after_one  # no new row
        assert len(broker.submitted) == 1  # never sent twice
        assert broker.submitted[0].client_order_id == dispatched_client_order_id

    def test_a_stale_or_forged_ticket_is_refused_before_anything_is_read_again(self) -> None:
        from empirical_platform.usecases.operator_console import ConsoleRefusalError

        repositories = _paper_repositories()
        broker, market_data = _open_broker(), FakeMarketData(quote=_FreshQuote())
        proposal = self._prepared(repositories, broker, market_data)
        service = _paper_service(repositories, broker=broker, market_data=market_data)
        with pytest.raises(ConsoleRefusalError):
            service.confirm_approval(proposal.proposal_governance_id, "not-a-real-ticket")
        assert len(repositories.attempts.rows) == 0


# ---------------------------------------------------------------------------
# E. UI: explicit text, no credential leakage
# ---------------------------------------------------------------------------


class TestUiIsExplicitAndLeaksNoCredential:
    def test_the_footer_names_paper_explicitly_not_simulation(self) -> None:
        from empirical_platform.entrypoints._operator_console_html import _FOOTER_NOTE

        assert "PAPER" in _FOOTER_NOTE
        assert "paper-api.alpaca.markets" in _FOOTER_NOTE["PAPER"]
        assert "Simulation only" not in _FOOTER_NOTE["PAPER"]
        assert "Simulation only" in _FOOTER_NOTE["SIMULATION"]

    def test_paper_health_page_renders_no_credential_shaped_text(self) -> None:
        from empirical_platform.entrypoints._operator_console_html import paper_health_page

        view = PaperHealthView(
            trading_endpoint=PAPER_ENDPOINT_HOST,
            is_pinned_paper_host=True,
            market_data_endpoint="data.alpaca.markets",
            account_reachable=True,
            account_status="ACTIVE",
            account_reference="ref:deadbeef",
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
            market_is_open=True,
            next_open=None,
            next_close=None,
            symbol=APPROVED_SYMBOL,
            asset_tradable=True,
            asset_status="active",
            position_quantity="0",
            quote_bid="342.43",
            quote_ask="342.48",
            quote_captured_at=None,
            quote_age_seconds="0.2",
            quote_source="alpaca-iex",
        )
        rendered = paper_health_page(view, capability_label="Paper")
        lowered = rendered.lower()
        for forbidden in ("api_key", "apikey", "secret", "bearer", "authorization:", "password"):
            assert forbidden not in lowered
        assert "PAPER" in rendered
        assert (
            "ref:deadbeef" in rendered
        )  # the digest is fine; the raw account id never exists here

    def test_paper_health_view_has_no_field_that_could_hold_a_credential(self) -> None:
        import dataclasses

        forbidden = {"key", "secret", "token", "password", "credential"}
        for field in dataclasses.fields(PaperHealthView):
            lowered = field.name.lower()
            assert not any(word in lowered for word in forbidden), field.name
