"""Pure, offline unit tests for MILESTONE-070's usecase-layer command
builder, derived-governance-id helper, date-arithmetic helper, and the
`research_session_report_payload` JSON serializer.

No network, no PostgreSQL anywhere in this file -- the full orchestration
`handle()` pipeline itself is exercised only in the PostgreSQL acceptance
suite (`tests/integration/test_m070_daily_research_session_lifecycle.py`),
since it is inherently DB-dependent (mission Phase 17 draws the same
offline/online line at the repository boundary, not below it).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pytest import CaptureFixture, MonkeyPatch

import empirical_platform.entrypoints.get_daily_research_session as get_entrypoint
import empirical_platform.entrypoints.run_daily_research_session as run_entrypoint
from empirical_platform.decision_candidate.market_data_acquisition import FakeMarketDataSource
from empirical_platform.decision_candidate.research_session import (
    RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    ResearchDecisionEntry,
    ResearchSession,
    ResearchSessionStatus,
    StageName,
    StageRecord,
    StageStatus,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId
from empirical_platform.shared.identifiers import RuntimeIdentifier, UuidRuntimeIdentifierGenerator
from empirical_platform.usecases.get_daily_research_session import (
    GetDailyResearchSessionHandler,
    GetDailyResearchSessionQuery,
)
from empirical_platform.usecases.research_session_io import research_session_report_payload
from empirical_platform.usecases.run_daily_research_session import (
    _days_before,
    _derived_governance_id,
    build_run_daily_research_session_command,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _identity() -> DomainIdentity[ResearchSessionId]:
    return DomainIdentity(
        governance_id=ResearchSessionId("RESEARCH-0001"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000001"),
    )


def _stage(
    name: StageName, status: StageStatus, *, started_at: datetime = _T0, failed: bool = False
) -> StageRecord:
    return StageRecord(
        stage_name=name,
        stage_version=None,
        started_at=started_at,
        completed_at=started_at if status is not StageStatus.PENDING else None,
        status=status,
        input_authority="test",
        output_identity=None if failed else "OUT-0001",
        error_type="ValueError" if failed else None,
        error_message="boom" if failed else None,
    )


def _completed_session(**overrides: object) -> ResearchSession:
    defaults: dict[str, object] = dict(
        identity=_identity(),
        created_at=_T0,
        as_of=_T0,
        requested_universe=("AAPL",),
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
        completed_at=_T0,
        stage_manifest=(_stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),),
        decisions=(),
        candidate_count=0,
        accepted_trade_plan_count=0,
        rejected_trade_plan_count=0,
        position_plan_count=0,
        backtest_run_governance_id="BTRUN-0001",
        backtest_evaluated_opportunity_count=0,
        backtest_executed_trade_count=0,
        limitations=RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    )
    defaults.update(overrides)
    return ResearchSession(**defaults)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# build_run_daily_research_session_command
# --------------------------------------------------------------------------


def test_build_command_derives_a_fresh_runtime_identity() -> None:
    generator = UuidRuntimeIdentifierGenerator()
    source = FakeMarketDataSource({}, clock=_FixedClock(_T0))
    command = build_run_daily_research_session_command(
        session_governance_id="RESEARCH-1234",
        as_of=_T0,
        universe=("AAPL", "MSFT"),
        lookback_days=20,
        artifact_path="artifact.json",
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        source=source,
        runtime_identifier_generator=generator,
    )
    assert str(command.identity.governance_id) == "RESEARCH-1234"
    assert command.as_of == _T0
    assert command.universe == ("AAPL", "MSFT")
    assert command.lookback_days == 20
    assert command.reference_window_size == 5


def test_build_command_two_calls_produce_different_runtime_ids() -> None:
    generator = UuidRuntimeIdentifierGenerator()
    source = FakeMarketDataSource({}, clock=_FixedClock(_T0))
    first = build_run_daily_research_session_command(
        session_governance_id="RESEARCH-1234",
        as_of=_T0,
        universe=("AAPL",),
        lookback_days=20,
        artifact_path="a.json",
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        source=source,
        runtime_identifier_generator=generator,
    )
    second = build_run_daily_research_session_command(
        session_governance_id="RESEARCH-1234",
        as_of=_T0,
        universe=("AAPL",),
        lookback_days=20,
        artifact_path="b.json",
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        source=source,
        runtime_identifier_generator=generator,
    )
    assert first.identity.runtime_id != second.identity.runtime_id


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


# --------------------------------------------------------------------------
# _days_before
# --------------------------------------------------------------------------


def test_days_before_subtracts_calendar_days() -> None:
    assert _days_before(date(2026, 1, 20), 5) == date(2026, 1, 15)


def test_days_before_crosses_month_boundary() -> None:
    assert _days_before(date(2026, 2, 3), 5) == date(2026, 1, 29)


def test_days_before_zero_days_is_identity() -> None:
    assert _days_before(date(2026, 1, 20), 0) == date(2026, 1, 20)


# --------------------------------------------------------------------------
# _derived_governance_id
# --------------------------------------------------------------------------


def test_derived_governance_id_is_deterministic_for_same_inputs() -> None:
    first = _derived_governance_id("DCAND", "11111111-1111-4111-8111-111111111111", 0)
    second = _derived_governance_id("DCAND", "11111111-1111-4111-8111-111111111111", 0)
    assert first == second


def test_derived_governance_id_differs_across_offsets() -> None:
    session_id = "11111111-1111-4111-8111-111111111111"
    minted = {_derived_governance_id("DCAND", session_id, offset) for offset in range(5)}
    assert len(minted) == 5


def test_derived_governance_id_differs_across_sessions() -> None:
    a = _derived_governance_id("DCAND", "11111111-1111-4111-8111-111111111111", 0)
    b = _derived_governance_id("DCAND", "22222222-2222-4222-8222-222222222222", 0)
    assert a != b


def test_derived_governance_id_matches_four_digit_prefix_shape() -> None:
    value = _derived_governance_id("DCAND", "11111111-1111-4111-8111-111111111111", 0)
    assert value.startswith("DCAND-")
    suffix = value.removeprefix("DCAND-")
    assert len(suffix) == 4
    assert suffix.isdigit()


# --------------------------------------------------------------------------
# research_session_report_payload
# --------------------------------------------------------------------------


def test_payload_completed_session_sections() -> None:
    decision = ResearchDecisionEntry(
        rank=1,
        instrument_symbol="AAPL",
        decision_candidate_governance_id="DCAND-0001",
        scan_decision="LONG_CANDIDATE",
        trade_plan_governance_id="PLAN-0001",
        trade_plan_decision="APPROVED_PLAN",
        position_plan_governance_id="POS-0001",
    )
    session = _completed_session(
        decisions=(decision,),
        candidate_count=1,
        accepted_trade_plan_count=1,
        position_plan_count=1,
        stage_manifest=(
            _stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),
            _stage(StageName.DATA_ACQUISITION, StageStatus.COMPLETED),
        ),
    )
    payload = research_session_report_payload(session)

    assert set(payload) == {"FACT", "HISTORICAL_EVIDENCE", "DIAGNOSTIC", "LIMITATION"}

    fact = payload["FACT"]
    assert fact["session_governance_id"] == "RESEARCH-0001"
    assert fact["completion_status"] == "COMPLETED"
    assert fact["requested_universe"] == ["AAPL"]
    assert fact["decisions"] == [
        {
            "rank": 1,
            "instrument_symbol": "AAPL",
            "decision_candidate_governance_id": "DCAND-0001",
            "scan_decision": "LONG_CANDIDATE",
            "trade_plan_governance_id": "PLAN-0001",
            "trade_plan_decision": "APPROVED_PLAN",
            "position_plan_governance_id": "POS-0001",
        }
    ]

    historical_evidence = payload["HISTORICAL_EVIDENCE"]
    assert historical_evidence["backtest_run_governance_id"] == "BTRUN-0001"
    assert historical_evidence["note"] is not None
    assert "not a claim about the live candidates" in historical_evidence["note"]

    diagnostic = payload["DIAGNOSTIC"]
    assert diagnostic["failed_stage"] is None
    assert diagnostic["failure_message"] is None
    assert [s["stage_name"] for s in diagnostic["stage_manifest"]] == [
        "GOVERNANCE_SETUP",
        "DATA_ACQUISITION",
    ]

    assert payload["LIMITATION"] == list(RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS)


def test_payload_failed_session_diagnostic_section() -> None:
    session = _completed_session(
        status=ResearchSessionStatus.FAILED,
        dataset_id=None,
        dataset_version=None,
        dataset_sha256=None,
        strategy_id=None,
        strategy_version=None,
        ranking_model_id=None,
        ranking_model_version=None,
        risk_policy_id=None,
        risk_policy_version=None,
        sizing_policy_id=None,
        sizing_policy_version=None,
        scan_governance_id=None,
        failed_stage=StageName.DATA_ACQUISITION,
        failure_type="ValueError",
        failure_message="boom",
        stage_manifest=(
            _stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),
            _stage(StageName.DATA_ACQUISITION, StageStatus.FAILED, failed=True),
        ),
        backtest_run_governance_id=None,
        backtest_evaluated_opportunity_count=None,
        backtest_executed_trade_count=None,
    )
    payload = research_session_report_payload(session)

    fact = payload["FACT"]
    assert fact["completion_status"] == "FAILED"

    historical_evidence = payload["HISTORICAL_EVIDENCE"]
    assert historical_evidence["backtest_run_governance_id"] is None
    assert historical_evidence["note"] is None

    diagnostic = payload["DIAGNOSTIC"]
    assert diagnostic["failed_stage"] == "DATA_ACQUISITION"
    assert diagnostic["failure_type"] == "ValueError"
    assert diagnostic["failure_message"] == "boom"
    failed_stage_entry = diagnostic["stage_manifest"][1]
    assert failed_stage_entry["status"] == "FAILED"
    assert failed_stage_entry["error_type"] == "ValueError"


def test_payload_timestamps_are_iso_formatted_strings() -> None:
    session = _completed_session()
    payload = research_session_report_payload(session)
    fact = payload["FACT"]
    assert isinstance(fact["created_at"], str)
    assert isinstance(fact["as_of"], str)
    assert isinstance(fact["completed_at"], str)


def test_days_before_returns_a_date_not_datetime() -> None:
    result = _days_before(date(2026, 1, 20), 3)
    assert type(result) is date


# --------------------------------------------------------------------------
# GetDailyResearchSessionHandler (trivial, single-method fake repository)
# --------------------------------------------------------------------------


class _FakeResearchSessionRepository:
    def __init__(self, session: ResearchSession) -> None:
        self._session = session
        self.requested_identity: object | None = None

    def get(self, identity: object) -> ResearchSession:
        self.requested_identity = identity
        return self._session

    def add(self, session: object) -> None:
        raise NotImplementedError


def test_get_daily_research_session_handler_delegates_to_repository() -> None:
    session = _completed_session()
    repository = _FakeResearchSessionRepository(session)
    handler = GetDailyResearchSessionHandler(repository=repository)

    result = handler.handle(GetDailyResearchSessionQuery(identity=session.identity))

    assert result is session
    assert repository.requested_identity is session.identity


# --------------------------------------------------------------------------
# CLI entrypoint argv handling (`main()`), with the DB/network-touching
# inner function monkeypatched out -- these tests exercise only the
# argv-parsing, output-formatting, and exit-code logic that is genuinely
# unit-testable without PostgreSQL or network access.
# --------------------------------------------------------------------------


def test_run_daily_research_main_rejects_too_few_arguments(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "RESEARCH-0001", "2026-01-01"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-run-daily-research"):
        run_entrypoint.main()


def test_run_daily_research_main_happy_path_prints_payload_and_exits_zero(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    session = _completed_session()
    captured_kwargs: dict[str, object] = {}

    def _fake_run(**kwargs: object) -> ResearchSession:
        captured_kwargs.update(kwargs)
        return session

    monkeypatch.setattr(run_entrypoint, "run_run_daily_research_session", _fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "RESEARCH-0001",
            "2026-01-01",
            "20",
            "artifact.json",
            "100000",
            "0.01",
            "AAPL",
            "MSFT",
        ],
    )
    run_entrypoint.main()

    assert captured_kwargs["session_governance_id"] == "RESEARCH-0001"
    assert captured_kwargs["as_of_date"] == "2026-01-01"
    assert captured_kwargs["lookback_days"] == 20
    assert captured_kwargs["universe"] == ("AAPL", "MSFT")

    printed = json.loads(capsys.readouterr().out)
    assert printed["FACT"]["completion_status"] == "COMPLETED"


def test_run_daily_research_main_nonzero_exit_when_session_not_completed(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    session = _completed_session(
        status=ResearchSessionStatus.FAILED,
        dataset_id=None,
        dataset_version=None,
        dataset_sha256=None,
        strategy_id=None,
        strategy_version=None,
        ranking_model_id=None,
        ranking_model_version=None,
        risk_policy_id=None,
        risk_policy_version=None,
        sizing_policy_id=None,
        sizing_policy_version=None,
        scan_governance_id=None,
        failed_stage=StageName.DATA_ACQUISITION,
        failure_type="ValueError",
        failure_message="boom",
        stage_manifest=(
            _stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),
            _stage(StageName.DATA_ACQUISITION, StageStatus.FAILED, failed=True),
        ),
        backtest_run_governance_id=None,
        backtest_evaluated_opportunity_count=None,
        backtest_executed_trade_count=None,
    )
    monkeypatch.setattr(run_entrypoint, "run_run_daily_research_session", lambda **_kwargs: session)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "RESEARCH-0001", "2026-01-01", "20", "artifact.json", "100000", "0.01", "AAPL"],
    )
    with pytest.raises(SystemExit) as exc_info:
        run_entrypoint.main()
    assert exc_info.value.code == 1


def test_get_daily_research_main_rejects_wrong_argument_count(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "RESEARCH-0001"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-daily-research"):
        get_entrypoint.main()


def test_get_daily_research_main_prints_payload(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    session = _completed_session()
    captured_kwargs: dict[str, object] = {}

    def _fake_get(**kwargs: object) -> ResearchSession:
        captured_kwargs.update(kwargs)
        return session

    monkeypatch.setattr(get_entrypoint, "run_get_daily_research_session", _fake_get)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "RESEARCH-0001", "00000000-0000-4000-8000-000000000001"],
    )
    get_entrypoint.main()

    assert captured_kwargs["session_governance_id"] == "RESEARCH-0001"
    assert captured_kwargs["session_runtime_id"] == "00000000-0000-4000-8000-000000000001"
    printed = json.loads(capsys.readouterr().out)
    assert printed["FACT"]["completion_status"] == "COMPLETED"
