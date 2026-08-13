"""Pure, offline unit tests for MILESTONE-073's one-command daily
research workflow entrypoint: the random session-id generator, the
default artifact-path helper, argv parsing, and `main()`'s own argv
handling (with the real, network/DB-touching
`run_daily_research_workflow` function monkeypatched out).

The real, network-capable, PostgreSQL-backed acceptance path is
exercised only in
tests/integration/test_m073_daily_research_workflow_lifecycle.py,
gated behind EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS -- mirroring the
established M070 precedent, since this entrypoint composes
RunDailyResearchSessionHandler (which itself has no offline injection
point at the entrypoint layer) unchanged.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import PurePath

import pytest
from pytest import CaptureFixture, MonkeyPatch

import empirical_platform.entrypoints.run_daily_research_workflow as workflow_entrypoint
from empirical_platform.decision_candidate.daily_research_brief import DailyResearchBrief
from empirical_platform.entrypoints.run_daily_research_workflow import (
    _default_artifact_path,
    _parse_args,
    _random_session_governance_id,
    run_daily_research_workflow,
)

# --------------------------------------------------------------------------
# _random_session_governance_id
# --------------------------------------------------------------------------


def test_random_session_governance_id_matches_identifier_pattern() -> None:
    rng = random.Random(1234)  # noqa: S311 -- test-only, not cryptographic
    for _ in range(50):
        governance_id = _random_session_governance_id(rng)
        assert governance_id.startswith("RESEARCH-")
        suffix = governance_id.removeprefix("RESEARCH-")
        assert len(suffix) == 4
        assert suffix.isdigit()


def test_random_session_governance_id_is_reproducible_for_a_seeded_rng() -> None:
    first = _random_session_governance_id(random.Random(42))  # noqa: S311
    second = _random_session_governance_id(random.Random(42))  # noqa: S311
    assert first == second


def test_random_session_governance_id_zero_pads_small_suffixes() -> None:
    class _FixedRng:
        def randint(self, _a: int, _b: int) -> int:
            return 7

    governance_id = _random_session_governance_id(_FixedRng())  # type: ignore[arg-type]
    assert governance_id == "RESEARCH-0007"


# --------------------------------------------------------------------------
# _default_artifact_path
# --------------------------------------------------------------------------


def test_default_artifact_path_includes_governance_id() -> None:
    path = _default_artifact_path("RESEARCH-1234")
    assert PurePath(path).name == "RESEARCH-1234.json"


# --------------------------------------------------------------------------
# _parse_args
# --------------------------------------------------------------------------


def test_parse_args_requires_at_least_one_symbol() -> None:
    with pytest.raises(SystemExit, match="usage: empirical-platform-daily-workflow"):
        _parse_args([])


def test_parse_args_rejects_unknown_flag() -> None:
    with pytest.raises(SystemExit, match="usage: empirical-platform-daily-workflow"):
        _parse_args(["--bogus-flag", "AAPL"])


def test_parse_args_applies_defaults() -> None:
    parsed = _parse_args(["AAPL", "MSFT"])
    assert parsed["symbols"] == ("AAPL", "MSFT")
    assert parsed["as_json"] is False
    assert parsed["as_of_date"] is None
    assert parsed["lookback_days"] == 20
    assert parsed["account_equity"] == Decimal("100000")
    assert parsed["risk_percent"] == Decimal("0.01")
    assert parsed["artifact_path"] is None


def test_parse_args_accepts_all_overrides_in_any_position() -> None:
    parsed = _parse_args(
        [
            "--json",
            "--as-of",
            "2026-08-10",
            "AAPL",
            "--lookback-days",
            "45",
            "--account-equity",
            "50000",
            "MSFT",
            "--risk-percent",
            "0.02",
            "--artifact-path",
            "/tmp/x.json",  # noqa: S108 -- literal test value, never actually written to
            "GOOG",
        ]
    )
    assert parsed["symbols"] == ("AAPL", "MSFT", "GOOG")
    assert parsed["as_json"] is True
    assert parsed["as_of_date"] == "2026-08-10"
    assert parsed["lookback_days"] == 45
    assert parsed["account_equity"] == Decimal("50000")
    assert parsed["risk_percent"] == Decimal("0.02")
    assert parsed["artifact_path"] == "/tmp/x.json"  # noqa: S108


def test_parse_args_rejects_missing_flag_value() -> None:
    with pytest.raises(SystemExit, match="--as-of requires a value"):
        _parse_args(["--as-of"])


def test_parse_args_rejects_non_integer_lookback_days() -> None:
    with pytest.raises(SystemExit, match="--lookback-days must be an integer"):
        _parse_args(["--lookback-days", "not-a-number", "AAPL"])


def test_parse_args_rejects_non_decimal_account_equity() -> None:
    with pytest.raises(SystemExit, match="--account-equity must be a decimal number"):
        _parse_args(["--account-equity", "not-a-decimal", "AAPL"])


def test_parse_args_rejects_non_decimal_risk_percent() -> None:
    with pytest.raises(SystemExit, match="--risk-percent must be a decimal number"):
        _parse_args(["--risk-percent", "not-a-decimal", "AAPL"])


# --------------------------------------------------------------------------
# main() argv handling (run_daily_research_workflow monkeypatched out --
# never touches real network/DB in this file)
# --------------------------------------------------------------------------


def _fake_brief() -> DailyResearchBrief:
    return DailyResearchBrief(
        session_governance_id="RESEARCH-9999",
        session_runtime_id="00000000-0000-4000-8000-000000000001",
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        requested_universe=("AAPL",),
        completion_status="COMPLETED",
        session_warnings=(),
        baseline_session_governance_id=None,
        baseline_as_of=None,
        baseline_note="no prior session found for this universe -- this is the first session",
        entries=(),
        data_source="YAHOO_FINANCE_UNOFFICIAL_CHART_JSON",
        dataset_sha256="0" * 64,
        backtest_run_governance_id=None,
        backtest_evaluated_opportunity_count=None,
        backtest_executed_trade_count=None,
        backtest_note=None,
        limitations=("Research output is not a trading instruction.",),
        campaign_governance_id="CAMP-9999",
        run_governance_id="RUN-9999",
        evidence_package_governance_id="EVID-9999",
        scan_governance_id="SCAN-9999",
        stage_manifest_summary=(),
    )


def test_main_rejects_missing_symbols(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-daily-workflow"):
        workflow_entrypoint.main()


def test_main_happy_path_prints_text_brief(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    brief = _fake_brief()
    captured_kwargs: dict[str, object] = {}

    def _fake_run(**kwargs: object) -> DailyResearchBrief:
        captured_kwargs.update(kwargs)
        return brief

    monkeypatch.setattr(workflow_entrypoint, "run_daily_research_workflow", _fake_run)
    monkeypatch.setattr("sys.argv", ["prog", "AAPL", "MSFT"])

    workflow_entrypoint.main()

    assert captured_kwargs["symbols"] == ("AAPL", "MSFT")
    assert captured_kwargs["as_of_date"] is None
    assert captured_kwargs["lookback_days"] == 20
    out = capsys.readouterr().out
    assert "DAILY RESEARCH BRIEF -- RESEARCH-9999" in out


def test_main_json_flag_prints_valid_json(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    brief = _fake_brief()
    monkeypatch.setattr(workflow_entrypoint, "run_daily_research_workflow", lambda **_: brief)
    monkeypatch.setattr("sys.argv", ["prog", "--json", "AAPL"])

    workflow_entrypoint.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["SESSION"]["session_governance_id"] == "RESEARCH-9999"


# --------------------------------------------------------------------------
# Duplicate-symbol rejection (regression: a duplicate symbol previously
# reached RunDailyResearchSessionHandler's own honest-failure path, whose
# ResearchSession-construction step itself raised an uncaught ValueError
# recording the failure -- a genuine, pre-existing M070 defect, confirmed
# to predate M073 via the unmodified `run-daily-research` entrypoint,
# reproducing identically. This entrypoint now rejects the malformed
# input before ever touching the database or network.)
# --------------------------------------------------------------------------


def test_run_daily_research_workflow_rejects_duplicate_symbol_before_any_io() -> None:
    with pytest.raises(ValueError, match="duplicate symbol"):
        run_daily_research_workflow(
            symbols=("AAPL", "AAPL"),
            as_of_date="2026-01-01",
            lookback_days=20,
            account_equity=Decimal("100000"),
            risk_percent=Decimal("0.01"),
            artifact_path=None,
            config=None,
        )


def test_main_rejects_duplicate_symbol_with_a_clean_message(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "AAPL", "AAPL"])
    with pytest.raises(SystemExit, match="duplicate symbol"):
        workflow_entrypoint.main()
