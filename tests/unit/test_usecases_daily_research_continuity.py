"""Pure, offline unit tests for MILESTONE-071's usecase layer: the list
and compare handlers (against a small fake repository), the two new
payload serializers, and both new CLI entrypoints' argv handling.

No network, no PostgreSQL anywhere in this file -- the real PostgreSQL
lifecycle is exercised only in
tests/integration/test_m071_daily_research_continuity_lifecycle.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pytest import CaptureFixture, MonkeyPatch

import empirical_platform.entrypoints.compare_daily_research_sessions as compare_entrypoint
import empirical_platform.entrypoints.list_daily_research_sessions as list_entrypoint
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
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.compare_daily_research_sessions import (
    CompareDailyResearchSessionsHandler,
    CompareDailyResearchSessionsQuery,
    SessionComparisonResult,
)
from empirical_platform.usecases.list_daily_research_sessions import (
    ListDailyResearchSessionsHandler,
    ListDailyResearchSessionsQuery,
)
from empirical_platform.usecases.research_session_io import (
    daily_research_session_comparison_payload,
    daily_research_session_list_payload,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _identity(governance_id: str, runtime_id: str) -> DomainIdentity[ResearchSessionId]:
    return DomainIdentity(
        governance_id=ResearchSessionId(governance_id),
        runtime_id=RuntimeIdentifier(runtime_id),
    )


def _stage() -> StageRecord:
    return StageRecord(
        stage_name=StageName.GOVERNANCE_SETUP,
        stage_version=None,
        started_at=_T0,
        completed_at=_T0,
        status=StageStatus.COMPLETED,
        input_authority="test",
        output_identity="OUT-0001",
        error_type=None,
        error_message=None,
    )


def _decision(symbol: str, scan_decision: str) -> ResearchDecisionEntry:
    return ResearchDecisionEntry(
        rank=None,
        instrument_symbol=symbol,
        decision_candidate_governance_id=f"DCAND-{symbol}",
        scan_decision=scan_decision,
        trade_plan_governance_id=None,
        trade_plan_decision=None,
        position_plan_governance_id=None,
    )


def _session(
    governance_id: str,
    runtime_id: str,
    *,
    as_of: datetime = _T0,
    decisions: tuple[ResearchDecisionEntry, ...] = (),
) -> ResearchSession:
    return ResearchSession(
        identity=_identity(governance_id, runtime_id),
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
        status=ResearchSessionStatus.COMPLETED,
        failed_stage=None,
        failure_type=None,
        failure_message=None,
        completed_at=as_of,
        stage_manifest=(_stage(),),
        decisions=decisions,
        candidate_count=len(decisions),
        accepted_trade_plan_count=0,
        rejected_trade_plan_count=0,
        position_plan_count=0,
        backtest_run_governance_id="BTRUN-0001",
        backtest_evaluated_opportunity_count=0,
        backtest_executed_trade_count=0,
        limitations=RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    )


def _summary_from(session: ResearchSession) -> ResearchSessionSummary:
    return ResearchSessionSummary(
        identity=session.identity,
        as_of=session.as_of,
        requested_universe=session.requested_universe,
        status=session.status,
        created_at=session.created_at,
        completed_at=session.completed_at,
        candidate_count=session.candidate_count,
        failed_stage=session.failed_stage,
    )


class _FakeResearchSessionRepository:
    """Minimal fake satisfying the full ResearchSessionRepository
    Protocol -- get/add plus the two new M071 read methods."""

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
        return tuple(_summary_from(s) for s in ordered[:limit])

    def find_most_recent_prior(
        self,
        *,
        universe: tuple[str, ...],
        before_as_of: datetime,
        exclude_runtime_id: object,
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


# --------------------------------------------------------------------------
# ListDailyResearchSessionsQuery validation
# --------------------------------------------------------------------------


def test_list_query_rejects_empty_universe_tuple() -> None:
    with pytest.raises(ValueError, match="universe must be non-empty"):
        ListDailyResearchSessionsQuery(universe=(), limit=10)


def test_list_query_rejects_zero_limit() -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        ListDailyResearchSessionsQuery(universe=None, limit=0)


def test_list_query_rejects_excessive_limit() -> None:
    with pytest.raises(ValueError, match="limit must not exceed"):
        ListDailyResearchSessionsQuery(universe=None, limit=10_000)


def test_list_query_accepts_none_universe() -> None:
    query = ListDailyResearchSessionsQuery(universe=None, limit=5)
    assert query.universe is None


# --------------------------------------------------------------------------
# ListDailyResearchSessionsHandler
# --------------------------------------------------------------------------


def test_list_handler_returns_summaries_from_repository() -> None:
    s1 = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001", as_of=_T0)
    repository = _FakeResearchSessionRepository((s1,))
    handler = ListDailyResearchSessionsHandler(repository=repository)

    result = handler.handle(ListDailyResearchSessionsQuery(universe=None, limit=10))

    assert len(result) == 1
    assert result[0].identity == s1.identity


def test_list_handler_filters_by_universe() -> None:
    from dataclasses import replace

    s1 = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001")
    s2 = replace(
        _session("RESEARCH-0002", "00000000-0000-4000-8000-000000000002"),
        requested_universe=("GOOG",),
    )
    repository = _FakeResearchSessionRepository((s1, s2))
    handler = ListDailyResearchSessionsHandler(repository=repository)

    result = handler.handle(ListDailyResearchSessionsQuery(universe=("AAPL", "MSFT"), limit=10))

    assert len(result) == 1
    assert result[0].identity == s1.identity


# --------------------------------------------------------------------------
# CompareDailyResearchSessionsHandler
# --------------------------------------------------------------------------


def test_compare_handler_no_prior_session() -> None:
    target = _session(
        "RESEARCH-0001",
        "00000000-0000-4000-8000-000000000001",
        as_of=_T0,
        decisions=(_decision("AAPL", "NO_TRADE"),),
    )
    repository = _FakeResearchSessionRepository((target,))
    handler = CompareDailyResearchSessionsHandler(repository=repository)

    result = handler.handle(CompareDailyResearchSessionsQuery(identity=target.identity))

    assert result.baseline is None
    assert len(result.entries) == 1
    assert result.entries[0].outcome.value == "NEW"


def test_compare_handler_finds_prior_session() -> None:
    from datetime import timedelta

    baseline = _session(
        "RESEARCH-0001",
        "00000000-0000-4000-8000-000000000001",
        as_of=_T0,
        decisions=(_decision("AAPL", "NO_TRADE"),),
    )
    target = _session(
        "RESEARCH-0002",
        "00000000-0000-4000-8000-000000000002",
        as_of=_T0 + timedelta(days=1),
        decisions=(_decision("AAPL", "LONG_CANDIDATE"),),
    )
    repository = _FakeResearchSessionRepository((baseline, target))
    handler = CompareDailyResearchSessionsHandler(repository=repository)

    result = handler.handle(CompareDailyResearchSessionsQuery(identity=target.identity))

    assert result.baseline is not None
    assert result.baseline.identity == baseline.identity
    assert result.entries[0].outcome.value == "CHANGED"


# --------------------------------------------------------------------------
# Payload serializers
# --------------------------------------------------------------------------


def test_list_payload_sections() -> None:
    s1 = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001")
    summaries = (_summary_from(s1),)

    payload = daily_research_session_list_payload(summaries)

    assert set(payload) == {"FACT"}
    assert payload["FACT"]["sessions"][0]["session_governance_id"] == "RESEARCH-0001"


def test_comparison_payload_no_baseline() -> None:
    target = _session(
        "RESEARCH-0001",
        "00000000-0000-4000-8000-000000000001",
        decisions=(_decision("AAPL", "NO_TRADE"),),
    )
    result = SessionComparisonResult(
        target=target,
        baseline=None,
        entries=(),
    )

    payload = daily_research_session_comparison_payload(result)

    assert set(payload) == {"FACT", "CONTINUITY", "LIMITATION"}
    assert payload["CONTINUITY"]["baseline_session_governance_id"] is None
    assert "no prior session found" in payload["CONTINUITY"]["note"]
    assert payload["LIMITATION"] == list(RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS)


def test_comparison_payload_with_baseline_and_entries() -> None:
    from empirical_platform.decision_candidate.research_session import (
        SessionComparisonEntry,
        SessionComparisonOutcome,
    )

    baseline = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001")
    target = _session("RESEARCH-0002", "00000000-0000-4000-8000-000000000002")
    entry = SessionComparisonEntry(
        instrument_symbol="AAPL",
        outcome=SessionComparisonOutcome.CHANGED,
        target_scan_decision="LONG_CANDIDATE",
        target_trade_plan_decision=None,
        baseline_scan_decision="NO_TRADE",
        baseline_trade_plan_decision=None,
    )
    result = SessionComparisonResult(target=target, baseline=baseline, entries=(entry,))

    payload = daily_research_session_comparison_payload(result)

    assert payload["CONTINUITY"]["note"] is None
    assert payload["CONTINUITY"]["baseline_session_governance_id"] == "RESEARCH-0001"
    assert len(payload["CONTINUITY"]["changed"]) == 1
    assert payload["CONTINUITY"]["changed"][0]["instrument_symbol"] == "AAPL"
    assert payload["CONTINUITY"]["new"] == []
    assert payload["CONTINUITY"]["dropped"] == []
    assert payload["CONTINUITY"]["unchanged"] == []


# --------------------------------------------------------------------------
# CLI entrypoint argv handling
# --------------------------------------------------------------------------


def test_list_main_rejects_missing_limit(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-list-daily-research"):
        list_entrypoint.main()


def test_list_main_happy_path_prints_payload(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    s1 = _session("RESEARCH-0001", "00000000-0000-4000-8000-000000000001")
    summaries = (_summary_from(s1),)
    captured_kwargs: dict[str, object] = {}

    def _fake_run(**kwargs: object) -> tuple[ResearchSessionSummary, ...]:
        captured_kwargs.update(kwargs)
        return summaries

    monkeypatch.setattr(list_entrypoint, "run_list_daily_research_sessions", _fake_run)
    monkeypatch.setattr("sys.argv", ["prog", "5", "AAPL", "MSFT"])

    list_entrypoint.main()

    assert captured_kwargs["limit"] == 5
    assert captured_kwargs["universe"] == ("AAPL", "MSFT")
    printed = json.loads(capsys.readouterr().out)
    assert printed["FACT"]["sessions"][0]["session_governance_id"] == "RESEARCH-0001"


def test_list_main_no_symbols_means_no_universe_filter(monkeypatch: MonkeyPatch) -> None:
    captured_kwargs: dict[str, object] = {}

    def _fake_run(**kwargs: object) -> tuple[ResearchSessionSummary, ...]:
        captured_kwargs.update(kwargs)
        return ()

    monkeypatch.setattr(list_entrypoint, "run_list_daily_research_sessions", _fake_run)
    monkeypatch.setattr("sys.argv", ["prog", "10"])

    list_entrypoint.main()

    assert captured_kwargs["universe"] is None


def test_compare_main_rejects_wrong_argument_count(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "RESEARCH-0001"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-compare-daily-research"):
        compare_entrypoint.main()


def test_compare_main_prints_payload(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    target = _session(
        "RESEARCH-0002",
        "00000000-0000-4000-8000-000000000002",
        decisions=(_decision("AAPL", "NO_TRADE"),),
    )
    result = SessionComparisonResult(target=target, baseline=None, entries=())
    captured_kwargs: dict[str, object] = {}

    def _fake_run(**kwargs: object) -> SessionComparisonResult:
        captured_kwargs.update(kwargs)
        return result

    monkeypatch.setattr(compare_entrypoint, "run_compare_daily_research_sessions", _fake_run)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "RESEARCH-0002", "00000000-0000-4000-8000-000000000002"],
    )

    compare_entrypoint.main()

    assert captured_kwargs["session_governance_id"] == "RESEARCH-0002"
    assert captured_kwargs["session_runtime_id"] == "00000000-0000-4000-8000-000000000002"
    printed = json.loads(capsys.readouterr().out)
    assert printed["FACT"]["session_governance_id"] == "RESEARCH-0002"
