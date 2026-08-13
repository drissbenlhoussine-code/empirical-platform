"""Pure, offline unit tests for MILESTONE-072's usecase layer: the
`BuildDailyResearchBriefHandler` (against small fake repositories), the
text/JSON renderers, and the CLI entrypoint's argv handling.

No network, no PostgreSQL anywhere in this file -- the real PostgreSQL
lifecycle is exercised only in
tests/integration/test_m072_daily_research_brief_lifecycle.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pytest import CaptureFixture, MonkeyPatch

import empirical_platform.entrypoints.build_daily_research_brief as brief_entrypoint
from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.daily_research_brief import DailyResearchBrief
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.decision_candidate.position_plan import (
    PositionPlan,
    PositionPlanStatus,
    PositionSizing,
)
from empirical_platform.decision_candidate.research_session import (
    RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    ResearchDecisionEntry,
    ResearchSession,
    ResearchSessionStatus,
    ResearchSessionSummary,
    StageName,
    StageRecord,
    StageStatus,
)
from empirical_platform.decision_candidate.strategy import (
    EvaluationMeasurements,
    EvaluationOutcome,
    EvaluationReasonCode,
    TradingDecision,
)
from empirical_platform.decision_candidate.trade_plan import (
    TradePlan,
    TradePlanGeometry,
    TradePlanRejectionReason,
    TradePlanStatus,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    PositionPlanId,
    ResearchSessionId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.build_daily_research_brief import (
    BuildDailyResearchBriefHandler,
    BuildDailyResearchBriefQuery,
)
from empirical_platform.usecases.daily_research_brief_io import (
    render_daily_research_brief_json,
    render_daily_research_brief_text,
)

_T0 = datetime(2026, 1, 10, tzinfo=UTC)

_FORBIDDEN_CLAIM_TERMS = (
    "BUY NOW",
    "SELL NOW",
    "GUARANTEED",
    "WILL PROFIT",
    "SURE THING",
    "RISK FREE",
)


def _session_identity(governance_id: str, runtime_id: str) -> DomainIdentity[ResearchSessionId]:
    return DomainIdentity(
        governance_id=ResearchSessionId(governance_id), runtime_id=RuntimeIdentifier(runtime_id)
    )


def _stage(
    name: StageName = StageName.CANDIDATE_SCAN, *, status: StageStatus = StageStatus.COMPLETED
) -> StageRecord:
    return StageRecord(
        stage_name=name,
        stage_version=None,
        started_at=_T0,
        completed_at=_T0,
        status=status,
        input_authority="test",
        output_identity="OUT-0001" if status is StageStatus.COMPLETED else None,
        error_type=None if status is StageStatus.COMPLETED else "RuntimeError",
        error_message=None if status is StageStatus.COMPLETED else "simulated failure",
    )


def _session(
    governance_id: str,
    runtime_id: str,
    *,
    as_of: datetime = _T0,
    decisions: tuple[ResearchDecisionEntry, ...] = (),
    status: ResearchSessionStatus = ResearchSessionStatus.COMPLETED,
    failed_stage: StageName | None = None,
    failure_message: str | None = None,
) -> ResearchSession:
    return ResearchSession(
        identity=_session_identity(governance_id, runtime_id),
        created_at=as_of,
        as_of=as_of,
        requested_universe=("AAPL", "MSFT"),
        data_source="FAKE_OFFLINE_FIXTURE",
        dataset_id="DATASET-0001",
        dataset_version="1",
        dataset_sha256="0" * 64,
        strategy_id="STRAT",
        strategy_version="1",
        ranking_model_id="RANK",
        ranking_model_version="1",
        risk_policy_id="RISK",
        risk_policy_version="1",
        sizing_policy_id="SIZE",
        sizing_policy_version="1",
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
        scan_governance_id="SCAN-0001",
        status=status,
        failed_stage=failed_stage,
        failure_type="RuntimeError" if failed_stage is not None else None,
        failure_message=failure_message,
        completed_at=as_of if status is ResearchSessionStatus.COMPLETED else None,
        stage_manifest=(
            (_stage(),)
            if failed_stage is None
            else (_stage(failed_stage, status=StageStatus.FAILED),)
        ),
        decisions=decisions,
        candidate_count=len(decisions),
        accepted_trade_plan_count=0,
        rejected_trade_plan_count=0,
        position_plan_count=0,
        backtest_run_governance_id="BTRUN-0001",
        backtest_evaluated_opportunity_count=3,
        backtest_executed_trade_count=1,
        limitations=RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    )


#: Identifier value objects require a `<PREFIX>-\d{4}` shape -- map each
#: test symbol to a stable 4-digit code so governance ids stay valid.
_SYMBOL_CODE: dict[str, str] = {"AAPL": "0001", "MSFT": "0002", "GOOG": "0003"}


def _gid(prefix: str, symbol: str) -> str:
    return f"{prefix}-{_SYMBOL_CODE[symbol]}"


def _decision(
    symbol: str,
    *,
    scan_decision: str,
    trade_plan_decision: str | None = None,
    position_plan_id: str | None = None,
) -> ResearchDecisionEntry:
    return ResearchDecisionEntry(
        rank=1,
        instrument_symbol=symbol,
        decision_candidate_governance_id=_gid("DCAND", symbol),
        scan_decision=scan_decision,
        trade_plan_governance_id=(
            _gid("PLAN", symbol) if trade_plan_decision is not None else None
        ),
        trade_plan_decision=trade_plan_decision,
        position_plan_governance_id=position_plan_id,
    )


def _candidate(
    symbol: str, *, decision: TradingDecision, reasons: tuple[EvaluationReasonCode, ...]
) -> DecisionCandidate:
    return DecisionCandidate(
        identity=DomainIdentity(
            governance_id=DecisionCandidateId(_gid("DCAND", symbol)),
            runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-0000000000c1"),
        ),
        target_evidence_package_id=EvidencePackageId("EVID-0001"),
        instrument=Instrument(symbol),
        interval=BarInterval.ONE_DAY,
        evaluation_timestamp=_T0,
        strategy_id="STRAT",
        strategy_version="1",
        reference_window_size=4,
        outcome=EvaluationOutcome(
            decision=decision,
            reasons=reasons,
            measurements=EvaluationMeasurements(
                current_close=Decimal("100"),
                current_volume=1000,
                reference_high=Decimal("90"),
                reference_average_volume=Decimal("800"),
            ),
        ),
    )


def _approved_trade_plan(symbol: str) -> TradePlan:
    return TradePlan(
        identity=DomainIdentity(
            governance_id=TradePlanId(_gid("PLAN", symbol)),
            runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-00000000000a"),
        ),
        source_scan_id=TradingOpportunityScanId("SCAN-0001"),
        source_decision_candidate_id=DecisionCandidateId(_gid("DCAND", symbol)),
        target_evidence_package_id=EvidencePackageId("EVID-0001"),
        instrument=Instrument(symbol),
        evaluation_cutoff=_T0,
        strategy_id="STRAT",
        strategy_version="1",
        ranking_model_id="RANK",
        ranking_model_version="1",
        policy_id="RISK",
        policy_version="1",
        status=TradePlanStatus.APPROVED_PLAN,
        geometry=TradePlanGeometry(
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            target_price=Decimal("115"),
            risk_per_unit=Decimal("5"),
            reward_per_unit=Decimal("15"),
            reward_risk_ratio=Decimal("3"),
        ),
        reasons=(),
    )


def _rejected_trade_plan(symbol: str, reason: TradePlanRejectionReason) -> TradePlan:
    return TradePlan(
        identity=DomainIdentity(
            governance_id=TradePlanId(_gid("PLAN", symbol)),
            runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-00000000000b"),
        ),
        source_scan_id=TradingOpportunityScanId("SCAN-0001"),
        source_decision_candidate_id=DecisionCandidateId(_gid("DCAND", symbol)),
        target_evidence_package_id=EvidencePackageId("EVID-0001"),
        instrument=Instrument(symbol),
        evaluation_cutoff=_T0,
        strategy_id="STRAT",
        strategy_version="1",
        ranking_model_id="RANK",
        ranking_model_version="1",
        policy_id="RISK",
        policy_version="1",
        status=TradePlanStatus.REJECTED_PLAN,
        geometry=None,
        reasons=(reason,),
    )


def _approved_position_plan(symbol: str) -> PositionPlan:
    return PositionPlan(
        identity=DomainIdentity(
            governance_id=PositionPlanId(_gid("POS", symbol)),
            runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-00000000000c"),
        ),
        source_trade_plan_id=TradePlanId(_gid("PLAN", symbol)),
        instrument=Instrument(symbol),
        policy_id="SIZE",
        policy_version="1",
        policy_maximum_risk_percent=Decimal("0.01"),
        policy_maximum_notional_percent=Decimal("0.25"),
        policy_allow_fractional_shares=False,
        supplied_account_equity=Decimal("50000"),
        supplied_risk_percent=Decimal("0.01"),
        status=PositionPlanStatus.APPROVED_POSITION_PLAN,
        sizing=PositionSizing(
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            risk_per_unit=Decimal("5"),
            allowed_risk_amount=Decimal("500"),
            maximum_notional=Decimal("12500"),
            risk_based_quantity=100,
            capital_based_quantity=125,
            quantity=100,
            position_notional=Decimal("10000"),
            actual_risk=Decimal("500"),
        ),
        reasons=(),
    )


class _FakeResearchSessionRepository:
    def __init__(self, sessions: tuple[ResearchSession, ...]) -> None:
        self._sessions = list(sessions)

    def get(self, identity: object) -> ResearchSession:
        for session in self._sessions:
            if session.identity == identity:
                return session
        raise AssertionError("session not found in fake repository")

    def add(self, session: ResearchSession) -> None:
        self._sessions.append(session)

    def list_recent(
        self, *, universe: tuple[str, ...] | None, limit: int
    ) -> tuple[ResearchSessionSummary, ...]:
        candidates = self._sessions
        if universe is not None:
            wanted = set(universe)
            candidates = [s for s in candidates if set(s.requested_universe) == wanted]
        ordered = sorted(candidates, key=lambda s: (s.as_of, s.created_at), reverse=True)
        return tuple(
            ResearchSessionSummary(
                identity=s.identity,
                as_of=s.as_of,
                requested_universe=s.requested_universe,
                status=s.status,
                created_at=s.created_at,
                completed_at=s.completed_at,
                candidate_count=s.candidate_count,
                failed_stage=s.failed_stage,
            )
            for s in ordered[:limit]
        )

    def find_most_recent_prior(
        self, *, universe: tuple[str, ...], before_as_of: datetime, exclude_runtime_id: object
    ) -> ResearchSession | None:
        wanted = set(universe)
        candidates = [
            s
            for s in self._sessions
            if set(s.requested_universe) == wanted
            and s.as_of < before_as_of
            and s.identity.runtime_id != exclude_runtime_id
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: (s.as_of, s.created_at))


class _FakeDecisionCandidateRepository:
    def __init__(self, candidates: tuple[DecisionCandidate, ...]) -> None:
        self._by_governance_id = {str(c.identity.governance_id): c for c in candidates}

    def get(self, identity: object) -> DecisionCandidate:
        raise AssertionError("not exercised")

    def get_by_governance_id(self, governance_id: DecisionCandidateId) -> DecisionCandidate:
        return self._by_governance_id[str(governance_id)]

    def add(self, candidate: DecisionCandidate) -> None:
        self._by_governance_id[str(candidate.identity.governance_id)] = candidate


class _FakeTradePlanRepository:
    def __init__(self, plans: tuple[TradePlan, ...]) -> None:
        self._by_governance_id = {str(p.identity.governance_id): p for p in plans}

    def get(self, identity: object) -> TradePlan:
        raise AssertionError("not exercised")

    def get_by_governance_id(self, governance_id: TradePlanId) -> TradePlan:
        return self._by_governance_id[str(governance_id)]

    def add(self, plan: TradePlan) -> None:
        self._by_governance_id[str(plan.identity.governance_id)] = plan


class _FakePositionPlanRepository:
    def __init__(self, plans: tuple[PositionPlan, ...]) -> None:
        self._by_governance_id = {str(p.identity.governance_id): p for p in plans}

    def get(self, identity: object) -> PositionPlan:
        raise AssertionError("not exercised")

    def get_by_governance_id(self, governance_id: PositionPlanId) -> PositionPlan:
        return self._by_governance_id[str(governance_id)]

    def add(self, plan: PositionPlan) -> None:
        self._by_governance_id[str(plan.identity.governance_id)] = plan


def _handler(
    *,
    sessions: tuple[ResearchSession, ...],
    candidates: tuple[DecisionCandidate, ...] = (),
    trade_plans: tuple[TradePlan, ...] = (),
    position_plans: tuple[PositionPlan, ...] = (),
) -> BuildDailyResearchBriefHandler:
    return BuildDailyResearchBriefHandler(
        research_session_repository=_FakeResearchSessionRepository(sessions),
        decision_candidate_repository=_FakeDecisionCandidateRepository(candidates),
        trade_plan_repository=_FakeTradePlanRepository(trade_plans),
        position_plan_repository=_FakePositionPlanRepository(position_plans),
    )


# --------------------------------------------------------------------------
# BuildDailyResearchBriefHandler
# --------------------------------------------------------------------------


def test_handler_full_approval_produces_risk_evidence() -> None:
    decisions = (
        _decision(
            "AAPL",
            scan_decision="LONG_CANDIDATE",
            trade_plan_decision="APPROVED_PLAN",
            position_plan_id=_gid("POS", "AAPL"),
        ),
    )
    session = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001", decisions=decisions)
    handler = _handler(
        sessions=(session,),
        candidates=(
            _candidate(
                "AAPL",
                decision=TradingDecision.LONG_CANDIDATE,
                reasons=(
                    EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH,
                    EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE,
                ),
            ),
        ),
        trade_plans=(_approved_trade_plan("AAPL"),),
        position_plans=(_approved_position_plan("AAPL"),),
    )

    brief = handler.handle(BuildDailyResearchBriefQuery(identity=session.identity))

    assert len(brief.entries) == 1
    entry = brief.entries[0]
    assert entry.attention_level.value == "ACTION_CANDIDATE"
    assert entry.rejection_reasons == ()
    assert entry.risk_evidence is not None
    assert entry.risk_evidence.entry_price == "100"
    assert entry.risk_evidence.quantity == 100
    assert entry.risk_evidence.position_notional == "10000"


def test_handler_rejected_trade_plan_surfaces_reason() -> None:
    decisions = (
        _decision("MSFT", scan_decision="LONG_CANDIDATE", trade_plan_decision="REJECTED_PLAN"),
    )
    session = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001", decisions=decisions)
    handler = _handler(
        sessions=(session,),
        candidates=(
            _candidate(
                "MSFT",
                decision=TradingDecision.LONG_CANDIDATE,
                reasons=(
                    EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH,
                    EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE,
                ),
            ),
        ),
        trade_plans=(
            _rejected_trade_plan("MSFT", TradePlanRejectionReason.REWARD_RISK_BELOW_MINIMUM),
        ),
    )

    brief = handler.handle(BuildDailyResearchBriefQuery(identity=session.identity))

    entry = brief.entries[0]
    assert entry.attention_level.value == "REVIEW"
    assert entry.rejection_reasons == ("the reward:risk ratio was below the policy minimum",)
    assert entry.risk_evidence is None


def test_handler_no_trade_surfaces_evaluation_reasons() -> None:
    decisions = (_decision("GOOG", scan_decision="NO_TRADE"),)
    session = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001", decisions=decisions)
    handler = _handler(
        sessions=(session,),
        candidates=(
            _candidate(
                "GOOG",
                decision=TradingDecision.NO_TRADE,
                reasons=(
                    EvaluationReasonCode.PRICE_NOT_ABOVE_REFERENCE_HIGH,
                    EvaluationReasonCode.VOLUME_NOT_ABOVE_REFERENCE_AVERAGE,
                ),
            ),
        ),
    )

    brief = handler.handle(BuildDailyResearchBriefQuery(identity=session.identity))

    entry = brief.entries[0]
    assert entry.attention_level.value == "ROUTINE"
    assert entry.rejection_reasons == (
        "closing price did not clear the reference high",
        "volume did not exceed the reference average",
    )


def test_handler_rejected_position_plan_reason_unavailable_on_completed_session() -> None:
    """MILESTONE-070's own orchestrator only persists
    `position_plan_governance_id` on the APPROVED branch -- a rejected
    position plan's own reason is genuinely unavailable from this
    session's own record on a COMPLETED session."""
    decisions = (
        _decision("AAPL", scan_decision="LONG_CANDIDATE", trade_plan_decision="APPROVED_PLAN"),
    )
    session = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001", decisions=decisions)
    handler = _handler(
        sessions=(session,),
        candidates=(
            _candidate(
                "AAPL",
                decision=TradingDecision.LONG_CANDIDATE,
                reasons=(
                    EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH,
                    EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE,
                ),
            ),
        ),
        trade_plans=(_approved_trade_plan("AAPL"),),
    )

    brief = handler.handle(BuildDailyResearchBriefQuery(identity=session.identity))

    entry = brief.entries[0]
    assert entry.position_plan_status == "REJECTED_POSITION_PLAN"
    assert "unavailable" in entry.rejection_reasons[0]
    assert entry.risk_evidence is None


def test_handler_failed_session_does_not_fabricate_position_plan_status() -> None:
    """On a FAILED session the position-sizing-attempted-for-every
    -approved-plan invariant does not necessarily hold -- the handler
    must not guess."""
    decisions = (
        _decision("AAPL", scan_decision="LONG_CANDIDATE", trade_plan_decision="APPROVED_PLAN"),
    )
    session = _session(
        "RESEARCH-0001",
        "00000000-0000-4000-8000-000000000001",
        decisions=decisions,
        status=ResearchSessionStatus.FAILED,
        failed_stage=StageName.POSITION_SIZING,
        failure_message="simulated failure",
    )
    handler = _handler(
        sessions=(session,),
        candidates=(
            _candidate(
                "AAPL",
                decision=TradingDecision.LONG_CANDIDATE,
                reasons=(
                    EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH,
                    EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE,
                ),
            ),
        ),
        trade_plans=(_approved_trade_plan("AAPL"),),
    )

    brief = handler.handle(BuildDailyResearchBriefQuery(identity=session.identity))

    entry = brief.entries[0]
    assert entry.position_plan_status is None
    assert entry.rejection_reasons == ()
    assert any("FAILED" in w for w in brief.session_warnings)


def test_handler_day_one_sets_baseline_note() -> None:
    decisions = (_decision("AAPL", scan_decision="NO_TRADE"),)
    session = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001", decisions=decisions)
    handler = _handler(
        sessions=(session,),
        candidates=(
            _candidate(
                "AAPL",
                decision=TradingDecision.NO_TRADE,
                reasons=(
                    EvaluationReasonCode.PRICE_NOT_ABOVE_REFERENCE_HIGH,
                    EvaluationReasonCode.VOLUME_NOT_ABOVE_REFERENCE_AVERAGE,
                ),
            ),
        ),
    )

    brief = handler.handle(BuildDailyResearchBriefQuery(identity=session.identity))

    assert brief.baseline_session_governance_id is None
    assert brief.baseline_note is not None
    assert "first session" in brief.baseline_note


def test_handler_finds_prior_session_for_comparison() -> None:
    baseline_decisions = (_decision("AAPL", scan_decision="NO_TRADE"),)
    baseline = _session(
        "RESEARCH-0001",
        "00000000-0000-4000-8000-000000000001",
        as_of=_T0,
        decisions=baseline_decisions,
    )
    target_decisions = (
        _decision("AAPL", scan_decision="LONG_CANDIDATE", trade_plan_decision="REJECTED_PLAN"),
    )
    target = _session(
        "RESEARCH-0002",
        "00000000-0000-4000-8000-000000000002",
        as_of=_T0 + timedelta(days=1),
        decisions=target_decisions,
    )
    handler = _handler(
        sessions=(baseline, target),
        candidates=(
            _candidate(
                "AAPL",
                decision=TradingDecision.LONG_CANDIDATE,
                reasons=(
                    EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH,
                    EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE,
                ),
            ),
        ),
        trade_plans=(_rejected_trade_plan("AAPL", TradePlanRejectionReason.INVALID_STOP_GEOMETRY),),
    )

    brief = handler.handle(BuildDailyResearchBriefQuery(identity=target.identity))

    assert brief.baseline_session_governance_id == "RESEARCH-0001"
    assert brief.entries[0].comparison_outcome.value == "CHANGED"


# --------------------------------------------------------------------------
# Renderer parity / determinism / claim-honesty
# --------------------------------------------------------------------------


def _sample_brief() -> DailyResearchBrief:
    decisions = (
        _decision(
            "AAPL",
            scan_decision="LONG_CANDIDATE",
            trade_plan_decision="APPROVED_PLAN",
            position_plan_id=_gid("POS", "AAPL"),
        ),
        _decision("MSFT", scan_decision="NO_TRADE"),
    )
    session = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001", decisions=decisions)
    handler = _handler(
        sessions=(session,),
        candidates=(
            _candidate(
                "AAPL",
                decision=TradingDecision.LONG_CANDIDATE,
                reasons=(
                    EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH,
                    EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE,
                ),
            ),
            _candidate(
                "MSFT",
                decision=TradingDecision.NO_TRADE,
                reasons=(
                    EvaluationReasonCode.PRICE_NOT_ABOVE_REFERENCE_HIGH,
                    EvaluationReasonCode.VOLUME_NOT_ABOVE_REFERENCE_AVERAGE,
                ),
            ),
        ),
        trade_plans=(_approved_trade_plan("AAPL"),),
        position_plans=(_approved_position_plan("AAPL"),),
    )
    return handler.handle(BuildDailyResearchBriefQuery(identity=session.identity))


def test_rendering_is_deterministic() -> None:
    brief = _sample_brief()
    assert render_daily_research_brief_text(brief) == render_daily_research_brief_text(brief)
    assert render_daily_research_brief_json(brief) == render_daily_research_brief_json(brief)


def test_text_and_json_renderers_agree_on_instrument_set() -> None:
    brief = _sample_brief()
    text = render_daily_research_brief_text(brief)
    payload = render_daily_research_brief_json(brief)

    for symbol in ("AAPL", "MSFT"):
        assert symbol in text
    json_symbols = {e["instrument_symbol"] for e in payload["ATTENTION"]}
    assert "AAPL" in json_symbols


def test_rendered_output_contains_no_forbidden_claim_language() -> None:
    brief = _sample_brief()
    text = render_daily_research_brief_text(brief).upper()
    payload_text = json.dumps(render_daily_research_brief_json(brief)).upper()

    for term in _FORBIDDEN_CLAIM_TERMS:
        assert term not in text
        assert term not in payload_text


def test_rendered_output_carries_claim_honesty_limitations() -> None:
    brief = _sample_brief()
    text = render_daily_research_brief_text(brief)
    for limitation in RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS:
        assert limitation in text


# --------------------------------------------------------------------------
# CLI entrypoint argv handling
# --------------------------------------------------------------------------


def test_main_rejects_odd_positional_count(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "RESEARCH-0001"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-daily-brief"):
        brief_entrypoint.main()


def test_main_default_no_args_requests_no_explicit_session(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    brief = _sample_brief()
    captured_kwargs: dict[str, object] = {}

    def _fake_run(**kwargs: object) -> DailyResearchBrief:
        captured_kwargs.update(kwargs)
        return brief

    monkeypatch.setattr(brief_entrypoint, "run_build_daily_research_brief", _fake_run)
    monkeypatch.setattr("sys.argv", ["prog"])

    brief_entrypoint.main()

    assert captured_kwargs["session_governance_id"] is None
    assert captured_kwargs["session_runtime_id"] is None
    out = capsys.readouterr().out
    assert "DAILY RESEARCH BRIEF" in out


def test_main_explicit_session_selection(monkeypatch: MonkeyPatch) -> None:
    brief = _sample_brief()
    captured_kwargs: dict[str, object] = {}

    def _fake_run(**kwargs: object) -> DailyResearchBrief:
        captured_kwargs.update(kwargs)
        return brief

    monkeypatch.setattr(brief_entrypoint, "run_build_daily_research_brief", _fake_run)
    monkeypatch.setattr(
        "sys.argv", ["prog", "RESEARCH-0001", "00000000-0000-4000-8000-000000000001"]
    )

    brief_entrypoint.main()

    assert captured_kwargs["session_governance_id"] == "RESEARCH-0001"
    assert captured_kwargs["session_runtime_id"] == "00000000-0000-4000-8000-000000000001"


def test_main_json_flag_produces_valid_json(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    brief = _sample_brief()
    monkeypatch.setattr(brief_entrypoint, "run_build_daily_research_brief", lambda **_: brief)
    monkeypatch.setattr("sys.argv", ["prog", "--json"])

    brief_entrypoint.main()

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "SESSION",
        "ATTENTION",
        "NEW",
        "CHANGED",
        "DROPPED",
        "UNCHANGED",
        "REJECTIONS",
        "RISK_AND_EVIDENCE",
        "DATA_QUALITY",
        "HISTORICAL_PORTFOLIO_EVIDENCE",
        "LIMITATIONS",
        "AUDIT",
    }


def test_main_json_flag_combined_with_explicit_session(monkeypatch: MonkeyPatch) -> None:
    brief = _sample_brief()
    captured_kwargs: dict[str, object] = {}

    def _fake_run(**kwargs: object) -> DailyResearchBrief:
        captured_kwargs.update(kwargs)
        return brief

    monkeypatch.setattr(brief_entrypoint, "run_build_daily_research_brief", _fake_run)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--json", "RESEARCH-0001", "00000000-0000-4000-8000-000000000001"],
    )

    brief_entrypoint.main()

    assert captured_kwargs["session_governance_id"] == "RESEARCH-0001"
