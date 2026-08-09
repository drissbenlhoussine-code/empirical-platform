"""MILESTONE-063 application and entrypoint unit tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.historical_backtest import HistoricalBacktestRun
from empirical_platform.decision_candidate.historical_backtest_repository import (
    HistoricalBacktestRunRepository,
)
from empirical_platform.decision_candidate.robustness_study import (
    HistoricalRobustnessStudy,
    RobustnessDatasetBundle,
)
from empirical_platform.decision_candidate.robustness_study_repository import (
    HistoricalRobustnessStudyRepository,
)
from empirical_platform.entrypoints import get_historical_robustness_study as get_entrypoint
from empirical_platform.entrypoints import run_historical_robustness_study as run_entrypoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, RobustnessStudyId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator
from empirical_platform.usecases.get_historical_robustness_study import (
    GetHistoricalRobustnessStudyHandler,
    GetHistoricalRobustnessStudyQuery,
)
from empirical_platform.usecases.robustness_study_io import (
    historical_robustness_study_payload,
    parse_robustness_dataset_bundle_file,
)
from empirical_platform.usecases.run_historical_robustness_study import (
    RunHistoricalRobustnessStudyHandler,
    build_run_historical_robustness_study_command,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m063_robustness_study"
    / "synthetic_broad_robustness_dataset_bundle.json"
)
_EXPECTED_SHA256 = "ca98478ce6156f41c4535eaa040fd3e161229a71acd771a477ee9648ac3dd506"


def _bundle() -> RobustnessDatasetBundle:
    return parse_robustness_dataset_bundle_file(
        str(_FIXTURE_PATH),
        expected_sha256=_EXPECTED_SHA256,
    )


def _generator() -> DeterministicRuntimeIdentifierGenerator:
    return DeterministicRuntimeIdentifierGenerator(
        [f"95000000-0000-4000-8000-{index:012d}" for index in range(1, 5000)]
    )


@dataclass
class _InMemoryBacktestRepository(HistoricalBacktestRunRepository):
    added: list[HistoricalBacktestRun]

    def get(
        self, identity: DomainIdentity[BacktestRunId]
    ) -> HistoricalBacktestRun:  # pragma: no cover - not exercised here
        for run in self.added:
            if run.identity == identity:
                return run
        raise KeyError(identity)

    def add(self, run: HistoricalBacktestRun) -> None:
        self.added.append(run)


@dataclass
class _InMemoryRobustnessRepository(HistoricalRobustnessStudyRepository):
    studies: dict[DomainIdentity[RobustnessStudyId], HistoricalRobustnessStudy]

    def get(self, identity: DomainIdentity[RobustnessStudyId]) -> HistoricalRobustnessStudy:
        return self.studies[identity]

    def add(self, study: HistoricalRobustnessStudy) -> None:
        self.studies[study.identity] = study


def test_build_command_derives_one_backtest_identity_per_window() -> None:
    command = build_run_historical_robustness_study_command(
        study_governance_id="ROBUST-6501",
        bundle=_bundle(),
        backtest_run_governance_id_base=6500,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        runtime_identifier_generator=_generator(),
    )

    assert str(command.identity.governance_id) == "ROBUST-6501"
    assert str(command.backtest_run_identity_for("W01").governance_id) == "BTRUN-6501"
    assert str(command.backtest_run_identity_for("W10").governance_id) == "BTRUN-6510"


def test_run_handler_persists_backtest_runs_before_the_study() -> None:
    backtests = _InMemoryBacktestRepository(added=[])
    studies = _InMemoryRobustnessRepository(studies={})
    command = build_run_historical_robustness_study_command(
        study_governance_id="ROBUST-6502",
        bundle=_bundle(),
        backtest_run_governance_id_base=6520,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        runtime_identifier_generator=_generator(),
    )

    handler = RunHistoricalRobustnessStudyHandler(
        historical_backtest_run_repository=backtests,
        robustness_study_repository=studies,
    )
    study = handler.handle(command)

    assert len(backtests.added) == 10
    assert study.identity in studies.studies
    assert studies.studies[study.identity].best_window_by_net_pnl.window_id == "W08"


def test_get_handler_returns_the_persisted_study() -> None:
    command = build_run_historical_robustness_study_command(
        study_governance_id="ROBUST-6503",
        bundle=_bundle(),
        backtest_run_governance_id_base=6530,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        runtime_identifier_generator=_generator(),
    )
    study = RunHistoricalRobustnessStudyHandler(
        historical_backtest_run_repository=_InMemoryBacktestRepository(added=[]),
        robustness_study_repository=(repo := _InMemoryRobustnessRepository(studies={})),
    ).handle(command)

    retrieved = GetHistoricalRobustnessStudyHandler(repository=repo).handle(
        GetHistoricalRobustnessStudyQuery(identity=study.identity)
    )
    assert retrieved.identity == study.identity
    assert retrieved.universe_id == "UNIVERSE-6301"


def test_payload_includes_universe_authority_and_regime_breakdown() -> None:
    study = RunHistoricalRobustnessStudyHandler(
        historical_backtest_run_repository=_InMemoryBacktestRepository(added=[]),
        robustness_study_repository=_InMemoryRobustnessRepository(studies={}),
    ).handle(
        build_run_historical_robustness_study_command(
            study_governance_id="ROBUST-6504",
            bundle=_bundle(),
            backtest_run_governance_id_base=6540,
            account_equity=Decimal("100000"),
            risk_percent=Decimal("0.01"),
            runtime_identifier_generator=_generator(),
        )
    )

    payload = historical_robustness_study_payload(study)
    assert payload["universe_id"] == "UNIVERSE-6301"
    assert payload["universe_version"] == "1"
    assert payload["universe_membership_model"] == "FIXED_SYNTHETIC_UNIVERSE"
    assert payload["instrument_universe"] == ["AAPL", "AMZN", "GOOG", "MSFT", "NVDA", "TSLA"]
    assert {entry["regime_label"] for entry in payload["regime_breakdown"]} == {
        "HIGH_VOLATILITY",
        "NORMAL_VOLATILITY",
        "LOW_VOLATILITY",
    }


def test_run_entrypoint_builds_and_returns_study_with_fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backtests = _InMemoryBacktestRepository(added=[])
    studies = _InMemoryRobustnessRepository(studies={})

    @contextmanager
    def _fake_runtime(
        _config: PostgreSQLConfigSnapshot | None = None,
    ) -> Iterator[object]:
        yield type(
            "Runtime",
            (),
            {"historical_backtests": backtests, "robustness_studies": studies},
        )()

    monkeypatch.setattr(run_entrypoint, "postgres_repository_runtime", _fake_runtime)
    study = run_entrypoint.run_run_historical_robustness_study(
        study_governance_id="ROBUST-6505",
        dataset_bundle_file=str(_FIXTURE_PATH),
        expected_dataset_sha256=_EXPECTED_SHA256,
        backtest_run_governance_id_base=6550,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        identifier_generator=_generator(),
    )

    assert len(backtests.added) == 10
    assert studies.studies[study.identity].classification.value == "ROBUSTNESS_EVIDENCE_MIXED"


def test_get_entrypoint_loads_study_with_fake_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    built_study = RunHistoricalRobustnessStudyHandler(
        historical_backtest_run_repository=_InMemoryBacktestRepository(added=[]),
        robustness_study_repository=(repo := _InMemoryRobustnessRepository(studies={})),
    ).handle(
        build_run_historical_robustness_study_command(
            study_governance_id="ROBUST-6506",
            bundle=_bundle(),
            backtest_run_governance_id_base=6560,
            account_equity=Decimal("100000"),
            risk_percent=Decimal("0.01"),
            runtime_identifier_generator=_generator(),
        )
    )

    @contextmanager
    def _fake_runtime(
        _config: PostgreSQLConfigSnapshot | None = None,
    ) -> Iterator[object]:
        yield type("Runtime", (), {"robustness_studies": repo})()

    monkeypatch.setattr(get_entrypoint, "postgres_repository_runtime", _fake_runtime)
    monkeypatch.setattr(
        run_entrypoint,
        "postgres_repository_runtime",
        lambda _config=None: pytest.fail("run entrypoint runtime should not be used in this test"),
    )

    retrieved = get_entrypoint.run_get_historical_robustness_study(
        study_governance_id="ROBUST-6506",
        study_runtime_id=str(built_study.identity.runtime_id),
    )
    assert retrieved.identity == built_study.identity
